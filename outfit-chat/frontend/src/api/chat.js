/**
 * 聊天接口封装（对接 SpringBoot 主后端，开发期走 vite 代理，同源相对路径即可）
 *
 * 后端接口：
 *   GET    /api/chat/stream?sessionId=&question=&userId=   SSE 流式对话
 *   GET    /api/chat/history/{sessionId}                   查聊天历史（MySQL）
 *   DELETE /api/chat/history/{sessionId}                   清聊天历史（MySQL + AI 侧记忆）
 *
 * SSE 帧格式（与 FastAPI 一致，data 后是 JSON）：
 *   {"type":"meta",  "sessionId":"...","userId":1,"question":"..."}
 *   {"type":"delta", "content":"根据"}          ← N 帧，逐字
 *   {"type":"done",  "sessionId":"...","content":"完整答案","deltaCount":40}
 *   {"type":"error", "message":"..."}
 */

/**
 * 构造 SSE 流式对话地址（EventSource 只支持 GET）
 * @param {string} sessionId 会话ID
 * @param {string} question  用户问题
 * @param {number} userId    用户ID
 * @returns {string} 编码好的 EventSource URL
 */
export function sseUrl(sessionId, question, userId) {
  return (
    `/api/chat/stream?sessionId=${encodeURIComponent(sessionId)}` +
    `&question=${encodeURIComponent(question)}` +
    `&userId=${encodeURIComponent(userId)}`
  )
}

/**
 * 查询某会话的聊天历史
 * @param {string} sessionId
 * @returns {Promise<Array<{id,sessionId,userId,role,content,createTime}>>} 时间正序
 */
export async function fetchHistory(sessionId) {
  const res = await fetch(`/api/chat/history/${encodeURIComponent(sessionId)}`)
  const body = await res.json()
  if (body.code !== 0) {
    throw new Error(body.message || '查询历史失败')
  }
  return body.data || []
}

/**
 * 清空某会话的聊天历史（MySQL 存档 + AI 侧上下文记忆）
 * @param {string} sessionId
 * @returns {Promise<number>} 删除的记录条数
 */
export async function clearHistory(sessionId) {
  const res = await fetch(`/api/chat/history/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  })
  const body = await res.json()
  if (body.code !== 0) {
    throw new Error(body.message || '清空失败')
  }
  return body.data?.deleted ?? 0
}
