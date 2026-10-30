<script setup>
/**
 * 单条消息气泡组件
 * props:
 *   - msg: { role, content, streaming?, error? }
 * user 在右侧（蓝底白字），assistant 在左侧（白底），错误消息红字。
 */
defineProps({
  msg: { type: Object, required: true },
})
</script>

<template>
  <div class="row" :class="msg.role === 'user' ? 'right' : 'left'">
    <div v-if="msg.role === 'assistant'" class="avatar">穿</div>
    <div class="bubble" :class="{ user: msg.role === 'user', error: msg.error }">
      <span class="text">{{ msg.content }}</span>
      <span v-if="msg.streaming" class="cursor">▍</span>
    </div>
  </div>
</template>

<style scoped>
.row {
  display: flex;
  gap: 8px;
  margin: 10px 0;
  align-items: flex-start;
}
.row.right {
  justify-content: flex-end;
}
.avatar {
  flex: none;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: #2563eb;
  color: #fff;
  font-size: 15px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.bubble {
  max-width: 76%;
  padding: 10px 14px;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 14px;
}
.bubble.user {
  background: #2563eb;
  color: #fff;
}
.bubble.error {
  color: #dc2626;
  background: #fef2f2;
}
.cursor {
  display: inline-block;
  margin-left: 2px;
  animation: blink 0.8s steps(1) infinite;
  color: #2563eb;
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}
</style>
