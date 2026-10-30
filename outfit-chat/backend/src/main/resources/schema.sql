-- 聊天记录表（SpringBoot 主后端持久化）
-- 说明：
--   * FastAPI 侧的 chat_history/<sessionId> 文件是大模型的"上下文记忆"，继续由 AI 服务管理；
--   * 本表是面向用户的"聊天记录存档"，由 SpringBoot 落库，两者职责不同、互不替代。
CREATE TABLE IF NOT EXISTS chat_message (
    id          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    session_id  VARCHAR(64)  NOT NULL                COMMENT '会话ID（与 FastAPI 侧一致）',
    user_id     BIGINT       NOT NULL DEFAULT 0      COMMENT '用户ID（当前无登录体系，先落库保存）',
    role        VARCHAR(16)  NOT NULL                COMMENT '消息角色：user=用户提问 / assistant=AI回答',
    content     MEDIUMTEXT   NOT NULL                COMMENT '消息内容',
    create_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_session (session_id, id),
    KEY idx_user (user_id, id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT ='用户聊天记录';
