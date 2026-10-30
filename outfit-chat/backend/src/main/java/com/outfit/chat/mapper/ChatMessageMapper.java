package com.outfit.chat.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.outfit.chat.entity.ChatMessage;

/**
 * 聊天记录 Mapper。
 *
 * <p>基础的 insert / selectList / delete 都由 MyBatis-Plus 的 BaseMapper 提供，
 * 本项目查询条件简单（按 sessionId），直接用 LambdaQueryWrapper 即可，无需手写 XML。</p>
 */
public interface ChatMessageMapper extends BaseMapper<ChatMessage> {
}
