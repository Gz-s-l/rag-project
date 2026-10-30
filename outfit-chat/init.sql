-- =====================================================================
-- 数据库初始化脚本（MySQL 容器首次启动时自动执行）
-- 挂载位置：docker-compose.yml 中 ./init.sql → /docker-entrypoint-initdb.d/01-init.sql
--
-- 说明：
--   * 只有 MySQL 数据卷为空的"首次启动"才会执行；后续重启不会重复执行；
--   * 本脚本同时被 SpringBoot 的 schema.sql 覆盖（IF NOT EXISTS 幂等），
--     所以即使跳过本脚本，应用自己也能建表；
--   * FastAPI 侧的 chat_history 文件是模型上下文记忆，不落 MySQL，两者职责不同。
-- =====================================================================

CREATE DATABASE IF NOT EXISTS `outfit_chat`
    DEFAULT CHARACTER SET utf8mb4
    COLLATE utf8mb4_general_ci;

USE `outfit_chat`;

CREATE TABLE IF NOT EXISTS `chat_message`
(
    `id`          BIGINT      NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `session_id`  VARCHAR(64) NOT NULL COMMENT '会话ID（与 FastAPI 侧一致）',
    `user_id`     BIGINT      NOT NULL DEFAULT 0 COMMENT '用户ID（当前无登录体系）',
    `role`        VARCHAR(16) NOT NULL COMMENT '消息角色：user=用户提问 / assistant=AI回答',
    `content`     MEDIUMTEXT  NOT NULL COMMENT '消息内容',
    `create_time` DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_session` (`session_id`, `id`),
    KEY `idx_user` (`user_id`, `id`)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_general_ci COMMENT ='用户聊天记录';
