import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * Vite 配置
 *
 * 开发期跨域方案：前端跑 5173，SpringBoot 跑 8080。
 * 所有 /api 请求经 vite 代理转发到 8080，浏览器眼里就是同源，不需要后端 CORS；
 * （SpringBoot 的 WebConfig CORS 放行是兜底，两条路都通。）
 *
 * proxy 支持 SSE：默认关闭缓冲，EventSource 收流不会被攒包卡顿。
 */
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
      },
    },
  },
})
