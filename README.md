# RAG 穿搭 / 客服知识库系统

本仓库包含两个可独立运行的项目：

| 目录 | 内容 | 技术栈 | 状态 |
|---|---|---|---|
| 仓库根目录 | **原版**：Streamlit 单机知识库问答 | Streamlit + LangChain + Chroma | 保留，可继续使用 |
| [`outfit-chat/`](./outfit-chat/) | **重构版**：平价穿搭 AI 顾问，前后端分离 + 容器化 | Vue3 + SpringBoot + FastAPI + MySQL | 已完成本地全链路验证 |

> 重构版完全独立：自己的 compose、自己的依赖、自己的文档，不依赖根目录任何代码。

---

## 一、原版（Streamlit 单机）

基于通义千问 + Chroma 的本地知识库问答系统，支持文件上传、对话记忆、向量检索。

```
├── app_qa.py               # 对话问答主界面
├── app_file_uploader.py    # 知识库文件上传界面
├── config_data.py          # 配置文件（API Key、路径、模型参数）
├── rag.py                  # RAG 核心逻辑
├── knowledge_base.py       # 知识库写入与去重
├── vector_stores.py        # 向量库检索
├── file_history_store.py   # 对话历史管理
├── requirements.txt        # 依赖包
├── .env                    # 环境变量（需自行创建）
├── chroma_db/              # 向量库（自动生成）
└── md5.txt                 # 文件去重记录（自动生成）
```

### 运行

```bash
pip install -r requirements.txt

# .env 中填入 DASHSCOPE_API_KEY=你的通义千问API Key

streamlit run app_file_uploader.py   # 先构建知识库
streamlit run app_qa.py              # 再启动问答
```

### 功能

- 支持 TXT 文件上传并自动向量化
- MD5 去重，避免重复导入
- 多轮对话记忆
- 基于本地 Chroma 向量库

### 常见问题

- 报错找不到模块：检查依赖是否安装完整
- Chroma 无法写入：关闭程序后删除 `chroma_db` 再重启
- API Key 报错：检查 `.env` 是否放在项目根目录

---

## 二、重构版（`outfit-chat/`）

原 Streamlit 项目重构为可 Docker 部署的前后端分离架构，业务上从「电商客服」改造为「平价穿搭顾问」（校园学生场景，不限性别）：

```
浏览器 → Vue3 前端 → SpringBoot 主后端 → FastAPI AI 服务 → 通义千问
                            ↓                    ↓
                     MySQL（聊天记录）      Chroma（穿搭知识库）
```

| 目录 | 职责 |
|---|---|
| `outfit-chat/ai-service/` | FastAPI AI 服务：原 RAG 检索/问答逻辑原样迁移 + SSE 流式输出 + 知识库自动构建 |
| `outfit-chat/backend/` | SpringBoot 主后端：WebClient 消费 SSE 并转发、聊天记录 MySQL 持久化（MyBatis-Plus） |
| `outfit-chat/frontend/` | Vue3 聊天前端：EventSource 接收流式回答，逐字渲染 |
| `outfit-chat/docker-compose.yml` | 一键编排：mysql / ai-service / backend / frontend（+ 可选 caddy 自动 HTTPS） |

**本地开发**：见 [`outfit-chat/README.md`](./outfit-chat/README.md)
**Docker 部署**：见 [`outfit-chat/DEPLOY.md`](./outfit-chat/DEPLOY.md)
**云服务器上线**：见 [`outfit-chat/DEPLOY_CLOUD.md`](./outfit-chat/DEPLOY_CLOUD.md)

```bash
cd outfit-chat
cp .env.example .env      # 填 DASHSCOPE_API_KEY、MYSQL_ROOT_PASSWORD
docker compose up -d --build
```
