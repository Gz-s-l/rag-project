<script setup>
/**
 * 聊天主界面（唯一页面）
 *
 * 布局：顶栏（标题/会话ID/用户ID/新建会话/清空历史）
 *      + 消息滚动区（MessageBubble）+ 底部输入条（发送 / 停止）
 *
 * 流式接收逻辑都在 useChat.js，这里只管渲染和事件绑定。
 */
import { ref, nextTick, watch, onMounted } from 'vue'
import MessageBubble from './components/MessageBubble.vue'
import { useChat } from './composables/useChat.js'

const { messages, streaming, sessionId, userId, send, stop, switchSession, clearCurrent, setUserId } =
  useChat()

const input = ref('')
const listEl = ref(null)
const userIdInput = ref(userId.value)

/** 发送：回车或点按钮 */
function onSend() {
  const q = input.value.trim()
  if (!q || streaming.value) return
  input.value = ''
  send(q)
}

/** 新消息/流式追加时自动滚到底部 */
watch(
  () => [messages.value.length, messages.value[messages.value.length - 1]?.content],
  async () => {
    await nextTick()
    if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
  },
)

/** 页面加载时按当前会话ID拉历史（刷新不丢记录，历史来自 MySQL） */
onMounted(() => switchSession(sessionId.value))

async function onClear() {
  if (!confirm('清空当前会话的全部聊天记录？（MySQL 与 AI 记忆都会清）')) return
  await clearCurrent()
}
</script>

<template>
  <div class="layout">
    <!-- 顶栏 -->
    <header>
      <div class="title">
        阿穿 · 平价穿搭顾问
        <span class="sub">校园学生向 · 不限男女</span>
      </div>
      <div class="ops">
        <label>
          会话
          <input class="sid" :value="sessionId" readonly title="换会话请点「新会话」" />
        </label>
        <label>
          用户ID
          <input
            class="uid"
            v-model="userIdInput"
            @change="setUserId(userIdInput)"
            title="当前无登录体系，可随意指定"
          />
        </label>
        <button class="ghost" @click="switchSession()">新会话</button>
        <button class="ghost" @click="onClear">清空历史</button>
      </div>
    </header>

    <!-- 消息区 -->
    <main ref="listEl" class="list">
      <div v-if="messages.length === 0" class="empty">
        <p>你好，我是阿穿 👋</p>
        <p>报上你的身高体重、肤色、场景（上课/约会/运动…）和预算，我直接给你能照着穿的方案。</p>
        <p class="tip">例如：我163，95斤，黄皮，下周约会穿什么？预算300</p>
      </div>
      <MessageBubble v-for="(m, i) in messages" :key="i" :msg="m" />
    </main>

    <!-- 输入条 -->
    <footer>
      <textarea
        v-model="input"
        :disabled="streaming"
        rows="1"
        placeholder="输入你的问题，回车发送（流式回答中不可输入）"
        @keydown.enter.exact.prevent="onSend"
      ></textarea>
      <button v-if="!streaming" class="primary" @click="onSend">发送</button>
      <button v-else class="stop" @click="stop">停止</button>
    </footer>
  </div>
</template>

<style scoped>
.layout {
  max-width: 760px;
  height: 100%;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  background: #f2f4f8;
}
header {
  flex: none;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px 16px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
}
.title {
  font-weight: 700;
  font-size: 16px;
}
.title .sub {
  margin-left: 8px;
  font-size: 12px;
  font-weight: 400;
  color: #6b7280;
}
.ops {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #6b7280;
}
.ops input {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 12px;
  color: #374151;
}
.ops .sid {
  width: 150px;
}
.ops .uid {
  width: 60px;
}
.ghost {
  border: 1px solid #d1d5db;
  background: #fff;
  border-radius: 6px;
  padding: 5px 10px;
  font-size: 12px;
  cursor: pointer;
}
.ghost:hover {
  background: #f3f4f6;
}
.list {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}
.empty {
  text-align: center;
  color: #9ca3af;
  margin-top: 18vh;
  line-height: 2.2;
}
.empty .tip {
  font-size: 13px;
}
footer {
  flex: none;
  display: flex;
  gap: 10px;
  padding: 12px 16px;
  background: #fff;
  border-top: 1px solid #e5e7eb;
}
textarea {
  flex: 1;
  resize: none;
  border: 1px solid #d1d5db;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 14px;
  font-family: inherit;
  outline: none;
  max-height: 120px;
}
textarea:focus {
  border-color: #2563eb;
}
.primary,
.stop {
  border: 0;
  border-radius: 10px;
  padding: 0 22px;
  font-size: 14px;
  cursor: pointer;
  color: #fff;
}
.primary {
  background: #2563eb;
}
.primary:hover {
  background: #1d4ed8;
}
.stop {
  background: #6b7280;
}
</style>
