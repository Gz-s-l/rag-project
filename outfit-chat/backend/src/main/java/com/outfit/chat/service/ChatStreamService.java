package com.outfit.chat.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.outfit.chat.config.AiServiceProperties;
import com.outfit.chat.entity.ChatMessage;
import com.outfit.chat.mapper.ChatMessageMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.util.UriUtils;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 聊天核心服务：SSE 流转发 + 聊天记录持久化。
 *
 * <p>数据流：</p>
 * <pre>
 * 浏览器(EventSource) → GET /api/chat/stream → SseEmitter ← 订阅 ← WebClient
 *                                              ↑ 转发帧         ↑ POST /api/chat/stream
 *                                          逐帧原样转发      FastAPI（RAG+大模型）
 * </pre>
 *
 * <p>持久化策略：</p>
 * <ul>
 *   <li>用户提问：收到请求后<b>立即落库</b>（哪怕后面流失败，提问也留档）；</li>
 *   <li>AI 回答：等 FastAPI 发来 done 帧（带完整答案）后落库；
 *       若流中途异常结束，则把已累计的 delta 拼接后落库，保证内容不丢；</li>
 *   <li>落库只做一次，用 AtomicBoolean 防重。</li>
 * </ul>
 */
@Service
public class ChatStreamService {

    private static final Logger log = LoggerFactory.getLogger(ChatStreamService.class);

    private final WebClientConfigHolder holder;
    private final ChatMessageMapper chatMessageMapper;
    private final ObjectMapper objectMapper = new ObjectMapper();

    /** WebClient 与配置的持有者（构造注入打包，避免 Service 里散落字段） */
    record WebClientConfigHolder(org.springframework.web.reactive.function.client.WebClient webClient,
                                 AiServiceProperties props) {
    }

    public ChatStreamService(org.springframework.web.reactive.function.client.WebClient aiWebClient,
                             AiServiceProperties props,
                             ChatMessageMapper chatMessageMapper) {
        this.holder = new WebClientConfigHolder(aiWebClient, props);
        this.chatMessageMapper = chatMessageMapper;
    }

    /**
     * 流式对话：调 FastAPI 的 SSE 接口，逐帧转发给前端，并持久化聊天记录。
     *
     * <p>转发原则：FastAPI 的 data 帧内容<b>原样透传</b>，不做任何字段增删改，
     * 前端拿到的帧格式与直连 FastAPI 完全一致。</p>
     *
     * @param sessionId 会话ID（已通过控制器白名单校验）
     * @param question  用户问题
     * @param userId    用户ID
     * @return SseEmitter，Spring MVC 负责以 text/event-stream 写回客户端
     */
    public SseEmitter stream(String sessionId, String question, Long userId) {
        // 0L = 不设超时，SSE 长连接由上游（FastAPI 断开 / 客户端断开 / 读空闲超时）来终止
        SseEmitter emitter = new SseEmitter(0L);

        // 1. 用户提问先落库（同步写，本地 MySQL 单条 insert 毫秒级）
        saveMessage(sessionId, userId, "user", question);

        // 2. 订阅 FastAPI 的 SSE 流
        StringBuilder answerBuf = new StringBuilder();
        AtomicBoolean assistantSaved = new AtomicBoolean(false);

        Flux<ServerSentEvent<String>> flux = holder.webClient().post()
                .uri(holder.props().chatPath())
                .accept(MediaType.TEXT_EVENT_STREAM)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "sessionId", sessionId,
                        "question", question,
                        "userId", userId
                ))
                .retrieve()
                .bodyToFlux(new ParameterizedTypeReference<ServerSentEvent<String>>() {
                });

        Disposable subscription = flux.subscribe(
                // ---- 每收到一帧 ----
                sse -> {
                    String data = sse.data();
                    if (data == null || data.isBlank()) {
                        return; // 心跳/注释帧，跳过
                    }
                    try {
                        JsonNode node = objectMapper.readTree(data);
                        String type = node.path("type").asText("");
                        switch (type) {
                            case "delta" -> answerBuf.append(node.path("content").asText(""));
                            case "done" -> {
                                // done 帧带完整答案，以此为准落库（比拼 delta 更可靠）
                                String full = node.path("content").asText("");
                                String content = full.isBlank() ? answerBuf.toString() : full;
                                if (assistantSaved.compareAndSet(false, true)) {
                                    saveMessage(sessionId, userId, "assistant", content);
                                }
                            }
                            case "error" -> log.warn("AI 服务返回 error 帧，sessionId={}，msg={}",
                                    sessionId, node.path("message").asText(""));
                            default -> { /* meta 等帧只转发，不处理 */ }
                        }
                        // 原样转发给前端（data: <原JSON>\n\n）
                        emitter.send(SseEmitter.event().data(data));
                    } catch (Exception e) {
                        log.error("转发 SSE 帧失败，sessionId={}", sessionId, e);
                    }
                },
                // ---- 上游异常 ----
                err -> {
                    log.error("调用 FastAPI SSE 失败，sessionId={}", sessionId, err);
                    if (assistantSaved.compareAndSet(false, true) && answerBuf.length() > 0) {
                        // 流中途断掉：把已生成的部分存档，用户刷新历史能看到半截回答
                        saveMessage(sessionId, userId, "assistant", answerBuf.toString());
                    }
                    try {
                        // 给前端补一帧标准 error（与 FastAPI 帧结构一致）
                        String msg = err.getMessage() == null ? "AI 服务连接失败" : err.getMessage();
                        emitter.send(SseEmitter.event().data(objectMapper.writeValueAsString(
                                Map.of("type", "error", "message", msg))));
                    } catch (Exception ignore) {
                        // 客户端多半已断开
                    }
                    emitter.completeWithError(err);
                },
                // ---- 流正常结束 ----
                () -> {
                    if (assistantSaved.compareAndSet(false, true) && answerBuf.length() > 0) {
                        // 没等到 done 帧就正常收尾的兜底（理论上少见）
                        saveMessage(sessionId, userId, "assistant", answerBuf.toString());
                    }
                    emitter.complete();
                });

        // 3. 客户端断开时取消上游订阅，避免白白消耗模型 tokens
        emitter.onCompletion(subscription::dispose);
        emitter.onTimeout(() -> {
            subscription.dispose();
            log.warn("SSE 超时，sessionId={}", sessionId);
        });
        emitter.onError(t -> subscription.dispose());

        return emitter;
    }

    /**
     * 查询某会话的聊天历史（从 MySQL 读，不经过 AI 服务）。
     *
     * @param sessionId 会话ID
     * @return 按时间正序的消息列表
     */
    public java.util.List<ChatMessage> listHistory(String sessionId) {
        return chatMessageMapper.selectList(new LambdaQueryWrapper<ChatMessage>()
                .eq(ChatMessage::getSessionId, sessionId)
                .orderByAsc(ChatMessage::getId));
    }

    /**
     * 清空某会话的聊天记录。
     *
     * <p>两处都要清：</p>
     * <ol>
     *   <li>MySQL 存档（本表）；</li>
     *   <li>FastAPI 的上下文记忆文件（转发 DELETE，让大模型忘掉这个会话）。</li>
     * </ol>
     *
     * @param sessionId 会话ID
     * @return MySQL 删除的行数
     */
    public int clearHistory(String sessionId) {
        int deleted = chatMessageMapper.delete(new LambdaQueryWrapper<ChatMessage>()
                .eq(ChatMessage::getSessionId, sessionId));
        try {
            holder.webClient().delete()
                    .uri("/api/chat/history/{sessionId}", UriUtils.encodePathSegment(sessionId, StandardCharsets.UTF_8))
                    .retrieve()
                    .toBodilessEntity()
                    .block();
        } catch (Exception e) {
            // MySQL 已清干净即可，AI 侧清不掉只影响下一轮记忆，不阻塞用户操作
            log.warn("清除 FastAPI 侧会话记忆失败（不影响 MySQL 存档），sessionId={}", sessionId, e);
        }
        return deleted;
    }

    private void saveMessage(String sessionId, Long userId, String role, String content) {
        if (content == null || content.isBlank()) {
            return;
        }
        ChatMessage m = new ChatMessage();
        m.setSessionId(sessionId);
        m.setUserId(userId);
        m.setRole(role);
        m.setContent(content);
        try {
            chatMessageMapper.insert(m);
            log.debug("聊天记录已落库：sessionId={}，role={}，len={}", sessionId, role, content.length());
        } catch (Exception e) {
            // 落库失败不阻断对话：聊天可用性优先，丢档问题留给日志告警
            log.error("聊天记录落库失败：sessionId={}，role={}", sessionId, role, e);
        }
    }
}
