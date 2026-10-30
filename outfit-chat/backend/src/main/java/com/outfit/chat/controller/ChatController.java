package com.outfit.chat.controller;

import com.outfit.chat.dto.ApiResponse;
import com.outfit.chat.dto.ChatMessageVO;
import com.outfit.chat.entity.ChatMessage;
import com.outfit.chat.service.ChatStreamService;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * 聊天接口（本服务对前端暴露的全部入口）。
 *
 * <p>接口清单：</p>
 * <table border="1">
 *   <tr><th>方法</th><th>路径</th><th>说明</th></tr>
 *   <tr><td>GET</td><td>/api/chat/stream?sessionId=&amp;question=&amp;userId=</td>
 *       <td>SSE 流式对话（<b>EventSource 专用</b>），帧格式与 FastAPI 完全一致</td></tr>
 *   <tr><td>POST</td><td>/api/chat/stream</td><td>同上，JSON 入参版（curl / 后续扩展用）</td></tr>
 *   <tr><td>GET</td><td>/api/chat/history/{sessionId}</td><td>查聊天历史（MySQL）</td></tr>
 *   <tr><td>DELETE</td><td>/api/chat/history/{sessionId}</td><td>清历史（MySQL + FastAPI 上下文记忆）</td></tr>
 * </table>
 */
@RestController
@RequestMapping("/api/chat")
public class ChatController {

    /** sessionId 白名单：与 FastAPI 侧规则一致（文件名安全，防路径穿越） */
    private static final Pattern SESSION_ID_PATTERN = Pattern.compile("^[A-Za-z0-9_-]{1,64}$");

    private final ChatStreamService chatStreamService;

    public ChatController(ChatStreamService chatStreamService) {
        this.chatStreamService = chatStreamService;
    }

    /**
     * SSE 流式对话（GET 版，EventSource 只支持 GET，前端模块四对接这个）。
     *
     * <p>入参（query string）：</p>
     * <ul>
     *   <li>sessionId：会话ID，必填，规则 ^[A-Za-z0-9_-]{1,64}$</li>
     *   <li>question：用户问题，必填</li>
     *   <li>userId：用户ID，必填（当前无登录体系，前端传什么就存什么）</li>
     * </ul>
     *
     * <p>出参（text/event-stream，逐帧）：</p>
     * <pre>
     * data: {"type":"meta","sessionId":"...","userId":1,"question":"..."}
     * data: {"type":"delta","content":"根据"}       ← N 帧，逐字
     * data: {"type":"done","sessionId":"...","content":"完整答案","deltaCount":6}
     * data: {"type":"error","message":"..."}        ← 仅出错时
     * </pre>
     */
    @GetMapping(value = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter streamByGet(@RequestParam String sessionId,
                                  @RequestParam String question,
                                  @RequestParam(required = false, defaultValue = "0") Long userId) {
        validate(sessionId, question);
        return chatStreamService.stream(sessionId, question, userId);
    }

    /**
     * SSE 流式对话（POST 版，JSON 入参，便于 curl 调试）。
     *
     * <p>入参（JSON body）：{"sessionId":"s1","question":"...","userId":1}</p>
     * <p>出参：同 GET 版。</p>
     */
    @PostMapping(value = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter streamByPost(@RequestBody StreamRequest req) {
        validate(req.sessionId(), req.question());
        return chatStreamService.stream(req.sessionId(), req.question(),
                req.userId() == null ? 0L : req.userId());
    }

    /**
     * 查询聊天历史（MySQL 存档，按时间正序）。
     *
     * <p>入参：路径 sessionId。</p>
     * <p>出参：{code:0, message:"success", data:[{id,sessionId,userId,role,content,createTime}...]}，
     * role: user=用户提问，assistant=AI 回答。</p>
     */
    @GetMapping("/history/{sessionId}")
    public ApiResponse<List<ChatMessageVO>> history(@PathVariable String sessionId) {
        validateSession(sessionId);
        List<ChatMessageVO> list = chatStreamService.listHistory(sessionId).stream()
                .map(ChatMessageVO::from)
                .collect(Collectors.toList());
        return ApiResponse.okList(list);
    }

    /**
     * 清空聊天历史：MySQL 存档 + 转发 DELETE 给 FastAPI（清大模型上下文记忆）。
     *
     * <p>入参：路径 sessionId。</p>
     * <p>出参：{code:0, message:"success", data:{"deleted":n}}，n 为 MySQL 删除行数。</p>
     */
    @DeleteMapping("/history/{sessionId}")
    public ApiResponse<java.util.Map<String, Object>> clearHistory(@PathVariable String sessionId) {
        validateSession(sessionId);
        int deleted = chatStreamService.clearHistory(sessionId);
        return ApiResponse.ok(java.util.Map.of("deleted", deleted));
    }

    // ------------------------------------------------------------------
    // 参数校验
    // ------------------------------------------------------------------

    private void validate(String sessionId, String question) {
        validateSession(sessionId);
        if (question == null || question.isBlank()) {
            throw new IllegalArgumentException("question 不能为空");
        }
    }

    private void validateSession(String sessionId) {
        if (sessionId == null || !SESSION_ID_PATTERN.matcher(sessionId).matches()) {
            throw new IllegalArgumentException("sessionId 只允许字母/数字/下划线/中划线，长度 1~64");
        }
    }

    /** POST /stream 的入参体 */
    public record StreamRequest(String sessionId, String question, Long userId) {
    }
}
