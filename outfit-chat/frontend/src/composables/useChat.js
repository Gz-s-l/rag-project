import { ref } from 'vue'
import { sseUrl, fetchHistory, clearHistory } from '../api/chat.js'

/**
 * 聊天逻辑组合式函数（状态 + SSE 流控制，界面层只管渲染）
 *
 * 消息结构：{ role: 'user'|'assistant', content: string, streaming?: boolean, error?: boolean }
 */
export function useChat() {
  /** 消息列表（时间正序） */
  const messages = ref([])

  /** 是否正在流式接收中 */
  const streaming = ref(false)

  /** 当前会话ID（换会话即换上下文） */
  const sessionId = ref(localStorage.getItem('outfit_session_id') || newId())

  /** 用户ID（当前无登录体系，存 localStorage 供用户自改） */
  const userId = ref(Number(localStorage.getItem('outfit_user_id')) || 1001)

  /** 当前打开的 EventSource，stop() 用 */
  let source = null

  function newId() {
    // 会话ID规则：字母/数字/下划线/中划线，1~64（后端白名单校验，保持一致）
    return 'web_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
  }

  /**
   * 发送问题并流式接收回答。
   * 流程：本地先画一条 user 消息 → EventSource 建连 →
   *       delta 帧往最后一条 assistant 消息追加 → done/error 收尾。
   * @param {string} question
   */
  function send(question) {
    const q = (question || '').trim()
    if (!q || streaming.value) return

    // 本地乐观渲染：提问立刻上屏（落库由后端负责，不需要等 done）
    messages.value.push({ role: 'user', content: q })
    const reply = { role: 'assistant', content: '', streaming: true }
    messages.value.push(reply)

    streaming.value = true
    // 注意：GET 带 query 是 EventSource 的唯一姿势，与后端契约一致
    source = new EventSource(sseUrl(sessionId.value, q, userId.value))

    source.onmessage = (e) => {
      let frame
      try {
        frame = JSON.parse(e.data)
      } catch {
        return // 非 JSON 帧（心跳等）忽略
      }
      switch (frame.type) {
        case 'delta':
          reply.content += frame.content || ''
          break
        case 'done':
          // 以后端 done 帧的完整答案为准，避免丢字
          if (frame.content) reply.content = frame.content
          finish()
          break
        case 'error':
          reply.content = reply.content || ''
          reply.error = true
          reply.content += (reply.content ? '\n\n' : '') + '⚠ 出错了：' + (frame.message || '未知错误')
          finish()
          break
        default:
          break // meta 等帧无需处理
      }
    }

    source.onerror = () => {
      // EventSource 断开（完成/网络断/后端关连接都会走这里）
      if (streaming.value) {
        if (!reply.content) {
          reply.error = true
          reply.content = '⚠ 连接中断，请重试'
        }
        finish()
      }
    }
  }

  /** 收尾：关流、去掉流式标记 */
  function finish() {
    if (source) {
      source.close()
      source = null
    }
    messages.value.forEach((m) => (m.streaming = false))
    streaming.value = false
  }

  /** 手动停止接收（不等 done 帧） */
  function stop() {
    if (!streaming.value) return
    finish()
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant' && !last.content) {
      last.error = true
      last.content = '⚠ 已手动停止'
    }
  }

  /**
   * 切换会话：换 ID、拉历史（MySQL 存档，按时间正序）。
   * @param {string} [targetId] 不传则新建会话
   */
  async function switchSession(targetId) {
    stop()
    sessionId.value = targetId || newId()
    localStorage.setItem('outfit_session_id', sessionId.value)
    messages.value = []
    try {
      const history = await fetchHistory(sessionId.value)
      messages.value = history.map((m) => ({ role: m.role, content: m.content }))
    } catch (e) {
      messages.value = [{ role: 'assistant', content: '⚠ 历史加载失败：' + e.message, error: true }]
    }
  }

  /** 清空当前会话历史（后端双清：MySQL + AI 上下文） */
  async function clearCurrent() {
    stop()
    await clearHistory(sessionId.value)
    messages.value = []
  }

  function setUserId(v) {
    userId.value = Number(v) || 1001
    localStorage.setItem('outfit_user_id', String(userId.value))
  }

  return { messages, streaming, sessionId, userId, send, stop, switchSession, clearCurrent, setUserId }
}
