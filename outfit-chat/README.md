# 平价穿搭 AI 顾问 · 前后端分离版

从原 Streamlit 单机项目（仓库根目录）重构而来，业务上改造为**平价日常穿搭顾问**（面向全体人群，重点服务校园学生场景）。

```
浏览器
  │  EventSource（SSE，逐字流式）
  ▼
Vue3 前端 (Vite dev :5173 / nginx :80)
  │  /api/**（同源，无需跨域）
  ▼
SpringBoot 主后端 (:8080)  ──WebClient 消费 SSE 并转发──▶  FastAPI AI 服务 (:8000)
  │                                                            │
  └── MyBatis-Plus ──▶ MySQL (outfit_chat)          RAG 检索 ──▶ Chroma (本地向量库)
                                                                 └──▶ 通义千问 qwen-max
```

SpringBoot 是唯一的数据出口：前端只跟它打交道，AI 服务不认识 MySQL，也不直接暴露给浏览器。

---

## 一、目录结构

```
outfit-chat/
├── ai-service/              # 模块一：FastAPI AI 服务
│   ├── main.py              # 应用入口、CORS、/health
│   ├── api_chat.py          # SSE 流式对话 + 历史查询/清空
│   ├── api_knowledge.py     # 知识库状态 / 重建 / 检索预览
│   ├── rag.py               # 原项目 RAG 链（仅替换 system prompt）
│   ├── vector_stores.py     # 原项目向量库（未改动）
│   ├── knowledge_base.py    # 原项目入库逻辑（未改动，含 MD5 去重）
│   ├── system_prompt.py     # 穿搭顾问人设与回答规则
│   ├── kb_bootstrap.py      # 启动时自动建库（语料增量入库 + 联网采集）
│   ├── web_collector.py     # 联网采集（多源降级 + 清洗过滤）
│   ├── corpus/              # 14 篇精选穿搭语料（知识库源，随镜像打包）
│   ├── schemas.py           # 所有接口的入参/出参定义
│   ├── requirements.txt
│   └── Dockerfile
│
├── backend/                 # 模块二：SpringBoot 主后端
│   ├── src/main/java/com/outfit/chat/
│   │   ├── controller/      # ChatController、全局异常处理
│   │   ├── service/         # ChatStreamService（SSE 转发核心）
│   │   ├── entity/ mapper/  # MyBatis-Plus 实体与 Mapper
│   │   ├── config/          # WebClient、CORS、AI 服务地址配置
│   │   └── dto/             # 统一响应体
│   ├── src/main/resources/  # application.yml、schema.sql
│   ├── pom.xml
│   └── Dockerfile
│
├── frontend/                # 模块三：Vue3 前端
│   ├── src/App.vue          # 聊天界面
│   ├── src/composables/useChat.js   # SSE 流控制
│   ├── src/api/chat.js      # 接口封装
│   ├── src/components/MessageBubble.vue
│   ├── nginx.conf           # SPA 回退 + /api 反代（SSE 不缓冲）
│   └── Dockerfile
│
├── docker-compose.yml       # 一键编排（+ 可选 caddy HTTPS）
├── Caddyfile                # 域名 HTTPS 入口（--profile https）
├── init.sql                 # 建库建表
├── .env.example             # 环境变量模板
├── DEPLOY.md                # 部署细节与排错
└── DEPLOY_CLOUD.md          # 云服务器从零上线（选购 → HTTPS）
```

---

## 二、本地启动（不用 Docker）

### 环境要求

| 项 | 版本 |
|---|---|
| Python | 3.12（AI 服务） |
| JDK | 17+（后端） |
| Node | 18+（前端） |
| MySQL | 8.x（本地 3306 即可，首次启动自动建库建表） |

### 三个终端

```bash
# ① AI 服务（:8000）
cd outfit-chat/ai-service
pip install -r requirements.txt         # 首次
uvicorn main:app --port 8000 --reload
# 当前账号 qwen3-max 不可用，如遇 Model not exist：
#   Windows CMD: set CHAT_MODEL_NAME=qwen-max
#   Git Bash   : export CHAT_MODEL_NAME=qwen-max

# ② 主后端（:8080）
cd outfit-chat/backend
mvn package -DskipTests                 # 首次
java -jar target/chat-backend-1.0.0.jar --server.port=8080
# 注意：本机若有 SERVER__PORT 环境变量会被 Spring 抢走，必须显式带 --server.port

# ③ 前端（:5173）
cd outfit-chat/frontend
npm install                             # 首次
npm run dev
```

打开 **http://localhost:5173** 直接聊天（vite 默认绑 IPv6，用 `localhost` 而非 `127.0.0.1`）。

### 调试页面（不依赖前端工程）

- `ai-service/dev_test_sse.html`：直连 AI 服务 8000，看逐字输出原始帧
- `backend/dev_test_spring_sse.html`：直连主后端 8080，含查历史 / 清历史

---

## 三、接口契约

前端与后端之间（SSE 由 SpringBoot 原样转发，帧格式与 AI 服务一致）：

| 方法 | 路径 | 入参 | 出参 |
|---|---|---|---|
| GET | `/api/chat/stream` | query: `sessionId`、`question`、`userId` | SSE 流（EventSource 只能用 GET） |
| POST | `/api/chat/stream` | JSON 同上，另可带 `history` | SSE 流（curl / 服务间调用） |
| GET | `/api/chat/history/{sessionId}` | 路径参数 | `{code:0, data:[{role, content, createTime}]}` 时间正序 |
| DELETE | `/api/chat/history/{sessionId}` | 路径参数 | `{code:0, data:{deleted:N}}`，同时清 AI 侧记忆 |

### SSE 帧格式

```
data: {"type":"meta",  "sessionId":"...","userId":1,"question":"..."}
data: {"type":"delta", "content":"根据"}
data: {"type":"done",  "sessionId":"...","content":"完整答案","deltaCount":40}
data: {"type":"error", "message":"..."}
```

用 JSON 承载而不是裸文本：模型输出含换行，裸文本会被 SSE 协议拆帧，前端拼接会错行。

> **这三条是硬约束**：接口路径、入参 JSON 结构、SSE 帧格式在重构过程中始终未变，
> 任何一层（Vue / SpringBoot / FastAPI）都不应单方面改动，否则链路立刻断。

---

## 四、知识库

- **来源**：`ai-service/corpus/` 下 14 个 txt（身材版型 / 配色肤色 / 校园场景 / 四季叠穿 / 比例避坑 / 平价清单 / 面料 / 鞋配 / 女生专题）
- **时机**：容器或服务启动时自动增量入库，靠原项目的 MD5 去重保证不重复
- **耗时**：首次 10~20 秒，二次启动命中缓存直接跳过
- **联网补充**：`web_collector.py` 会按配置的关键词抓公开穿搭干货并清洗后入库（7 天过期一次）。
  **问答环节完全不联网**，只查本地向量库，所以流式响应速度不受影响
- **状态查询**：`GET /api/knowledge/status`；强制重建：`POST /api/knowledge/bootstrap?force=true`

---

## 五、文档索引

| 文档 | 内容 |
|---|---|
| `ai-service/README.md` | AI 服务接口、系统提示词全文、知识库机制、验证话术 |
| `backend/README.md` | 后端接口、落库策略、WebClient 配置、本地启动 |
| `frontend/README.md` | 前端结构、SSE 流控制、跨域方案 |
| `DEPLOY.md` | Docker 部署、配置项、SSE 分层排查、备份恢复 |
| `DEPLOY_CLOUD.md` | 没有服务器时从买机器到域名 HTTPS 的完整流程 |

---

## 六、已知限制

- **本机无 Docker**：镜像从未实际构建，`docker compose up --build` 是首次真实验证
- **`qwen3-max` 在当前 DashScope 账号下不可用**（返回 `Model not exist`），默认已改为 `qwen-max`
- **免密钥联网采集产出不稳定**：百度/搜狗有反爬，实际入库依赖当次网络状况；稳定扩库建议把 txt 放进 `corpus/` 或配置 `WEB_SEARCH_PROVIDER=bocha` + Key
- **未做 JWT**：`userId` 由前端传入，仅用于区分聊天记录，不具备鉴权能力
