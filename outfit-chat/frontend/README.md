# 模块三：Vue3 前端（聊天界面 + EventSource 流式接收）

架构中的位置：**本前端(5173) ↔ SpringBoot 主后端(8080) ↔ FastAPI AI 服务(8000) + MySQL**

技术栈：Vue 3.5（组合式 API）+ Vite 5，无其他运行时依赖，体积极小。

---

## 一、目录结构

```
frontend/
├── package.json / vite.config.js / index.html
└── src/
    ├── main.js / style.css
    ├── App.vue                    # 聊天主界面（顶栏 + 消息区 + 输入条）
    ├── api/chat.js                # 接口封装：SSE 地址构造 / 查历史 / 清历史
    ├── composables/useChat.js     # 聊天状态与 SSE 流控制（EventSource）
    └── components/MessageBubble.vue  # 消息气泡（含流式打字光标）
```

## 二、功能清单

- 聊天界面：用户右侧蓝气泡、AI 左侧白气泡（带头像「穿」）、逐字流式渲染 + 闪烁光标
- 流式接收：`EventSource` → `GET /api/chat/stream`，按 `meta/delta/done/error` 帧处理；
  done 帧以后端完整答案为准覆盖，避免丢字
- 「停止」按钮：流式中途可手动断开
- 会话管理：sessionId 自动生成（`web_` 前缀），存 localStorage，刷新不丢；
  「新会话」一键切换；sessionId 规则与后端白名单一致
- 历史记录：进页面自动从 MySQL 拉当前会话历史（刷新恢复）；
  「清空历史」调 DELETE（MySQL 存档 + AI 侧上下文一起清）
- 用户ID：顶栏可改，存 localStorage（当前无登录体系）

## 三、本地运行

```bash
# 1. 先启动 FastAPI(8000) 和 SpringBoot(8080)（见各模块 README）

# 2. 启动前端
cd D:\Vscode\rag\outfit-chat\frontend
npm install        # 首次
npm run dev        # 打开 http://localhost:5173
```

生产构建：`npm run build` → 产物在 `dist/`，将来由 nginx 托管（最后统一做）。

## 四、跨域说明

开发期 vite 把 `/api` 代理到 `http://127.0.0.1:8080`，浏览器眼里同源，无跨域问题；
SpringBoot 侧的 CORS 全放行配置是兜底。生产环境 nginx 同域反代后两者都可直接删。

## 五、实测记录（2026-10-30，本机全部通过）

1. `npm run build` 编译通过，产物 dist/ 正常生成；
2. vite dev + 代理链路：前端 5173 → SpringBoot 8080 → FastAPI 8000 全链路流式对话正常，
   逐字输出、光标动画、done 收尾均正确；
3. 历史恢复：刷新页面后自动加载 MySQL 里的历史消息；
4. 清空历史：确认弹窗 → MySQL 与 AI 侧记忆双清；
5. 停止按钮：断开后可继续输入下一问。
