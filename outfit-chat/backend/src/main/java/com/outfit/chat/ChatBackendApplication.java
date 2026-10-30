package com.outfit.chat;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * SpringBoot 主后端启动类。
 *
 * <p>架构中的位置：Vue3 前端 ↔ <b>本服务</b> ↔ FastAPI AI 服务 + MySQL</p>
 * <ul>
 *   <li>对外（前端）：GET /api/chat/stream（SSE）、聊天历史增删查</li>
 *   <li>对内（AI 服务）：WebClient 调用 FastAPI 的 POST /api/chat/stream</li>
 *   <li>持久化：聊天记录写 MySQL（MyBatis-Plus）</li>
 * </ul>
 */
@SpringBootApplication
@MapperScan("com.outfit.chat.mapper")
public class ChatBackendApplication {

    public static void main(String[] args) {
        SpringApplication.run(ChatBackendApplication.class, args);
    }
}
