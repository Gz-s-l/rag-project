package com.outfit.chat.dto;

import com.outfit.chat.entity.ChatMessage;

import java.time.LocalDateTime;

/**
 * 聊天历史记录 VO（返回给前端的视图对象）。
 *
 * <p>接口：GET /api/chat/history/{sessionId}</p>
 *
 * @param id         消息ID
 * @param sessionId  会话ID
 * @param userId     用户ID
 * @param role       消息角色：user / assistant
 * @param content    消息内容
 * @param createTime 创建时间（yyyy-MM-dd HH:mm:ss）
 */
public record ChatMessageVO(
        Long id,
        String sessionId,
        Long userId,
        String role,
        String content,
        LocalDateTime createTime) {

    public static ChatMessageVO from(ChatMessage m) {
        return new ChatMessageVO(m.getId(), m.getSessionId(), m.getUserId(),
                m.getRole(), m.getContent(), m.getCreateTime());
    }
}
