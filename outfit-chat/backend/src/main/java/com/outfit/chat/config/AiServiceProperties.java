package com.outfit.chat.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * FastAPI AI 服务的连接配置。
 *
 * <p>对应 application.yml 里的 ai.service 前缀；Docker 部署时只需把
 * base-url 改成 http://ai-service:8000，代码不用动。</p>
 *
 * @param baseUrl          AI 服务根地址，如 http://127.0.0.1:8000
 * @param chatPath         SSE 流式对话接口路径（与 FastAPI 契约一致，禁止改动）
 * @param connectTimeoutMs 建立连接超时（毫秒）
 * @param responseTimeoutMs SSE 流最长空闲时间（毫秒），即等模型吐出首字的耐心上限
 */
@ConfigurationProperties(prefix = "ai.service")
public record AiServiceProperties(
        String baseUrl,
        String chatPath,
        long connectTimeoutMs,
        long responseTimeoutMs) {

    public AiServiceProperties {
        if (chatPath == null || chatPath.isBlank()) {
            chatPath = "/api/chat/stream";
        }
        if (connectTimeoutMs <= 0) {
            connectTimeoutMs = 5000;
        }
        if (responseTimeoutMs <= 0) {
            responseTimeoutMs = 120_000;
        }
    }
}
