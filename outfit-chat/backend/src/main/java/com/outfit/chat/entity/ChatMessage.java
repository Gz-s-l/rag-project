package com.outfit.chat.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import java.time.LocalDateTime;

/**
 * 用户聊天记录实体，对应 MySQL 表 chat_message（见 resources/schema.sql）。
 *
 * <p>职责说明：</p>
 * <ul>
 *   <li>FastAPI 侧 chat_history/&lt;sessionId&gt; 文件 = 大模型的"上下文记忆"（AI 服务自管）；</li>
 *   <li>本表 = 面向用户的"聊天记录存档"（SpringBoot 落库），两者职责不同、互不替代。</li>
 * </ul>
 */
@TableName("chat_message")
public class ChatMessage {

    /** 自增主键 */
    @TableId(type = IdType.AUTO)
    private Long id;

    /** 会话ID（与 FastAPI 侧 sessionId 一致） */
    private String sessionId;

    /** 用户ID（当前无登录体系，先落库保存） */
    private Long userId;

    /** 消息角色：user = 用户提问 / assistant = AI 回答 */
    private String role;

    /** 消息内容 */
    private String content;

    /** 创建时间 */
    private LocalDateTime createTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getSessionId() { return sessionId; }
    public void setSessionId(String sessionId) { this.sessionId = sessionId; }
    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }
    public String getRole() { return role; }
    public void setRole(String role) { this.role = role; }
    public String getContent() { return content; }
    public void setContent(String content) { this.content = content; }
    public LocalDateTime getCreateTime() { return createTime; }
    public void setCreateTime(LocalDateTime createTime) { this.createTime = createTime; }
}
