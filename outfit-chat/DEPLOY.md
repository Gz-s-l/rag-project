# 部署文档 · 平价穿搭 AI 顾问（Docker Compose 一键部署）

> 架构：`浏览器 → nginx(frontend) → SpringBoot(backend) → FastAPI(ai-service) → 通义千问`
> 　　　　　　　　　　　　　　　　`SpringBoot → MySQL(聊天记录持久化)`
>
> **还没有服务器？** 先看 [`DEPLOY_CLOUD.md`](./DEPLOY_CLOUD.md)：服务器选型 → 系统初始化 →
> Git 拉代码 → 域名与自动 HTTPS，一条龙。本文档默认你已经有一台装好 Docker 的机器。

---

## 一、目录结构与交付物

新架构全部收在仓库的 `outfit-chat/` 目录下，与原 Streamlit 单机版（仓库根目录的 `app_qa.py`、`rag.py`、`chroma_db/` 等）互不干扰，可各自独立运行。

```
仓库根\
├── app_qa.py / app_file_uploader.py / rag.py …   # 原 Streamlit 单机版（未改动，仍可运行）
├── chroma_db\ / md5.txt                          # 原单机版向量库
└── outfit-chat\                                  # ★ 本次重构的前后端分离版本
    ├── docker-compose.yml        # 一键编排（4 个常驻服务 + 可选 caddy + 4 个数据卷 + 1 个网络）
    ├── Caddyfile                 # 可选：域名 HTTPS 入口（--profile https 启用，自动证书）
    ├── init.sql                  # MySQL 初始化：建库 + chat_message 表
    ├── .env.example              # 环境变量模板（复制为 .env 填值）
    ├── README.md                 # 新架构总览与本地启动
    ├── DEPLOY.md                 # 本文档（部署细节与排错）
    ├── DEPLOY_CLOUD.md           # 云服务器从零上线指南（选购 / 初始化 / HTTPS）
    │
    ├── ai-service\               # 模块一：FastAPI RAG 流式 AI 服务
    │   ├── Dockerfile            # python:3.12-slim，内置健康检查
    │   ├── .dockerignore         # 已排除 venv、密钥与本地向量库
    │   ├── corpus\               # 14 篇精选穿搭语料（随镜像打包，启动自动入库）
    │   ├── system_prompt.py      # 穿搭顾问人设与回答规则
    │   ├── kb_bootstrap.py       # 启动时自动建库（增量入库 + 联网采集）
    │   └── requirements.txt
    │
    ├── backend\                  # 模块二：SpringBoot 主后端
    │   ├── Dockerfile            # 多阶段：maven 编译 → jre-alpine 运行
    │   ├── docker/maven-settings.xml   # 构建期阿里云镜像加速
    │   ├── src/main/resources/schema.sql  # 应用启动自动建表（与 init.sql 同源）
    │   └── pom.xml
    │
    └── frontend\                 # 模块三：Vue3 前端
        ├── Dockerfile            # 多阶段：node 构建 → nginx 托管
        └── nginx.conf            # SPA 回退 + /api 反代（SSE 不缓冲的关键参数）
```

> 所有 `docker compose` 命令都要**在 `outfit-chat/` 目录里执行**（compose 文件的相对路径 `./ai-service`、`./init.sql`、`./Caddyfile` 都相对它解析）。

---

## 二、前置条件

| 项 | 要求 |
|---|---|
| Docker | Docker Engine 20.10+ / Docker Desktop 4.x+ |
| Docker Compose | v2（`docker compose` 命令，不是旧的 `docker-compose`） |
| 磁盘 | 建议预留 5GB（镜像 + 数据卷） |
| 网络 | 能访问阿里云百炼 API（`dashscope.aliyuncs.com`） |
| 密钥 | 阿里云百炼 DashScope API Key |

验证环境：

```bash
docker version
docker compose version
```

---

## 三、快速部署（三步）

```bash
cd D:\Vscode\rag\outfit-chat        # 注意：一定要进到 outfit-chat 目录再执行

# 1. 配置环境变量
copy .env.example .env          # Windows CMD
# cp .env.example .env          # Git Bash / Linux / macOS
# 编辑 .env，至少填 DASHSCOPE_API_KEY 和 MYSQL_ROOT_PASSWORD

# 2. 构建并启动（首次构建约 5~15 分钟，取决于网络）
docker compose up -d --build

# 3. 看状态
docker compose ps
docker compose logs -f backend
```

访问：**http://localhost:8081**

首次启动的时间线（正常现象）：

| 阶段 | 耗时 | 现象 |
|---|---|---|
| 拉基础镜像 + 构建 | 5~15 分钟 | `--build` 阶段无输出属正常 |
| MySQL 初始化 | 10~30 秒 | logs 出现 `ready for connections` |
| ai-service 启动 | 5~10 秒 | 健康检查通过 |
| **知识库自动构建** | 10~20 秒 | 后台线程从 `corpus/` 入库 14 篇语料，**期间提问可能命中不完整知识库，稍等即可** |
| backend 启动 | ~10 秒 | 健康检查通过后 frontend 才起来 |

---

## 四、端口与访问

| 服务 | 容器端口 | 宿主端口 | 说明 |
|---|---|---|---|
| frontend (nginx) | 80 | **8081**（`.env` 的 `WEB_PORT` 可改） | 默认唯一对外入口 |
| backend | 8080 | 不暴露 | 仅内部网络，避免与本地开发冲突 |
| ai-service | 8000 | 不暴露 | 仅内部网络 |
| mysql | 3306 | 不暴露 | 仅内部网络 |
| caddy（可选） | 80 / 443 | **80 / 443** | 仅在 `--profile https` 时启动，自动申请证书 |

启用域名 HTTPS 后，访问链路变成 `浏览器 → caddy(443) → frontend:80 → backend → ai-service`，
此时可以直接把 8081 的映射注释掉，只留 443 对外：

```bash
# .env
DOMAIN=chat.你的域名.com
docker compose --profile https up -d
```


需要临时排查时（不改 compose）：

```bash
# 进容器执行
docker compose exec backend sh
docker compose exec ai-service bash
docker compose exec mysql mysql -uroot -p
```

若确实要暴露后端端口调试，在 `docker-compose.yml` 的 backend 服务下加：

```yaml
    ports:
      - "8080:8080"
```

---

## 五、验收清单

### 1. 容器状态

```bash
docker compose ps
# 期望：mysql/ai-service/backend/frontend 均为 Up，且有 (healthy) 标记
```

### 2. 前端页面

浏览器打开 http://localhost:8081 —— 应看到「阿穿 · 平价穿搭顾问」聊天界面。

### 3. 流式对话（核心）

在页面输入：

> 我163，95斤，女生，黄皮，下周约会穿什么？预算300

预期：
- 回答**逐字出现**（不是等几秒后整段蹦出）→ 说明 nginx / SpringBoot / FastAPI 三段 SSE 都正常；
- 回答包含「上装 + 下装 + 鞋 + 配色」+ 避雷项 + 微调建议。

**若整段一次性出现**，说明某段缓冲没关掉，按第七节排查。

### 4. 聊天记录落库

```bash
docker compose exec mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e \
  "select id,session_id,role,left(content,40) from outfit_chat.chat_message order by id desc limit 6;"
```

预期：每轮对话 2 条（user + assistant）。

### 5. 历史与清空

页面上点「新会话」→ 输入新问题 → 刷新页面，历史从 MySQL 恢复；
点「清空历史」→ 弹窗确认 → 消息清空，MySQL 对应 session 记录也被删除。

### 6. 无外网降级验证（可选）

```bash
docker compose stop ai-service
# 页面再提问：应看到红色 ⚠ 出错的 error 帧提示，SpringBoot 不崩
docker compose start ai-service
```

---

## 六、配置项说明（.env）

| 变量 | 默认 | 说明 |
|---|---|---|
| `DASHSCOPE_API_KEY` | 无（必填） | 阿里云百炼 Key，缺失则大模型调用失败 |
| `MYSQL_ROOT_PASSWORD` | 123456 | **首次初始化数据卷时生效**，改后需删卷重建 |
| `WEB_PORT` | 8081 | 前端对外端口 |
| `CHAT_MODEL_NAME` | qwen-max | 对话模型。**当前账号下 `qwen3-max` 返回 Model not exist，别填它** |
| `EMBEDDING_MODEL_NAME` | text-embedding-v4 | 向量化模型，改动会导致已有向量维度不兼容（需删 ai_data 卷重建） |
| `TOP_K` | 4 | 检索条数 |
| `KB_AUTO_BOOTSTRAP` | true | 启动自动补齐知识库 |
| `WEB_SEARCH_ENABLED` | true | 启动时联网扩充知识库（问答时不联网） |
| `WEB_SEARCH_PROVIDER` | auto | auto=百度→搜狗→360 自动降级；也可 `bocha`（需 Key） |
| `PIP_INDEX_URL` | 清华源 | 构建期 pip 加速，留空用官方源 |

修改后重启生效：

```bash
docker compose up -d          # 仅重建受影响的容器
```

---

## 七、常见问题排查

### 1. 回答"憋一会儿然后整段蹦出"（SSE 被缓冲）

三个环节都可能缓冲，逐层排查：

```bash
# ① 直连 AI 服务确认源头是流式的
docker compose exec ai-service python -c "
import urllib.request, json
req = urllib.request.Request('http://127.0.0.1:8000/api/chat/stream',
    data=json.dumps({'sessionId':'probe','question':'你好','userId':1}).encode(),
    headers={'Content-Type':'application/json'})
for line in urllib.request.urlopen(req):
    print(line[:80]); break
"
# 逐帧打印 => AI 服务正常，问题在 nginx 或 SpringBoot

# ② 直连 backend 对比（需临时暴露 8080，见第四节）
curl -N -X POST http://localhost:8080/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"sessionId":"probe2","question":"你好","userId":1}'
```

- ② 也是流式、只在浏览器里不流 → **nginx 缓冲**：确认 `nginx.conf` 里 `proxy_buffering off;`、`gzip off;`、`X-Accel-Buffering no` 都在；
- ② 也是整段 → **SpringBoot 侧**：确认 `ChatStreamService` 是逐帧 `emitter.send(...)`（本项目已如此），检查是否有网关/代理再套了一层。

### 2. `ai-service` 健康检查一直不通过

```bash
docker compose logs ai-service | tail -50
```

常见原因：
- `DASHSCOPE_API_KEY` 没填 → 服务能起但调用失败（日志有 warning，不影响 healthcheck）；
- `chroma-hnswlib` 编译失败 → 在 `ai-service/Dockerfile` 的 apt 安装行补 `cmake`；
- 内存不足（<2GB）→ `docker compose logs` 里出现 OOM，给 Docker Desktop 加内存。

### 3. `backend` 起不来：`Communications link failure`

MySQL 还没就绪。compose 已配 `depends_on: service_healthy`，若仍出现：

```bash
docker compose logs mysql | tail -30
docker compose restart backend
```

### 4. `backend` 报 `Public Key Retrieval is not allowed` / 认证失败

连接串已带 `allowPublicKeyRetrieval=true`；若改过 MySQL 用户认证插件（如 caching_sha2 改 mysql_native），在 `init.sql` 里调整或改用非 root 账号。

### 5. 改了 `MYSQL_ROOT_PASSWORD` 但没生效

MySQL 初始化只在**数据卷为空**时执行。需要重置：

```bash
docker compose down
docker volume rm rag_mysql_data        # 卷名 = 目录名_mysql_data，用 docker volume ls 确认
docker compose up -d
```

⚠ 这会**删除全部聊天记录**，生产环境请先备份（见第八节）。

### 6. 页面能开但接口 502

```bash
docker compose ps          # backend 是否 healthy
docker compose logs backend | tail -50
```
`frontend` 依赖 backend 健康后才启动；若手动 `restart frontend` 时 backend 恰好没起来，会出现短暂 502。

### 7. 端口 8081 被占用

改 `.env` 的 `WEB_PORT=8090` 后 `docker compose up -d`。

---

## 八、数据持久化与备份

| 数据卷 | 内容 | 丢了会怎样 |
|---|---|---|
| `mysql_data` | 聊天记录（chat_message） | 用户历史全丢 |
| `ai_data` | Chroma 向量库 + chat_history 会话记忆 + kb_state.json | 会话上下文丢失；向量库会自动从 corpus 重建（联网采集部分需重新抓） |

备份：

```bash
# MySQL 逻辑备份
docker compose exec mysql sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" outfit_chat' > backup_$(date +%F).sql

# AI 数据卷打包
docker run --rm -v rag_ai_data:/data -v "%cd%":/backup alpine tar czf /backup/ai_data.tar.gz -C /data .
```

恢复：

```bash
docker compose exec -T mysql sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" outfit_chat' < backup_2026-10-30.sql
```

---

## 九、生产环境建议（上线前必看）

1. **改密码**：`MYSQL_ROOT_PASSWORD` 换成强密码；建议另建业务账号，不用 root（同步改 `MYSQL_USER/MYSQL_PASSWORD`）。
2. **不要暴露 3306/8000/8080**：本编排已只暴露 8081，保持这个习惯。
3. **HTTPS**：前置一层 nginx/Caddy 或云负载均衡做 TLS；本仓库的 nginx.conf 只管 80。
   ⚠ TLS 层同样要关缓冲：`proxy_buffering off; proxy_read_timeout 3600s;`
4. **加 JWT 与限流**：当前按需求未做鉴权；上线前在 backend 加 Spring Security + JWT，并给 `/api/chat/stream` 加并发/频率限制（SSE 长连接很吃连接数）。
5. **资源限制**：给 ai-service 加 `deploy.resources.limits.memory: 2g`（Chroma + onnxruntime 内存需求较高）。
6. **日志**：`docker compose logs` 只适合短期排查看；生产接 ELK/Loki，并给容器配 `logging.options.max-size`。
7. **模型与配额**：留意百炼账号的 QPS/Token 配额，SSE 并发高时容易 429。

---

## 十、常用运维命令

```bash
docker compose ps                     # 状态
docker compose logs -f --tail=100     # 跟踪全部日志
docker compose logs -f ai-service     # 单服务日志
docker compose restart backend        # 重启单个服务
docker compose up -d --build backend  # 改代码后重建单个服务
docker compose down                   # 停止并删除容器（保留数据卷）
docker compose down -v                # ⚠ 连数据卷一起删（数据全丢）
docker compose pull && docker compose up -d   # 更新基础镜像
```

---

## 十一、本次交付的验证状态（如实说明）

| 项 | 状态 |
|---|---|
| 三个模块本地联调（5173 → 8080 → 8000 → MySQL） | ✅ 已实测通过（模块一/二/三 README 有记录） |
| `docker-compose.yml` YAML 结构、服务依赖、卷与端口 | ✅ 已用解析器校验 |
| 各 Dockerfile 语法与构建顺序 | ✅ 已逐行检查（多阶段、层缓存、健康检查） |
| nginx SSE 关键参数（`proxy_buffering off` / `gzip off` / 长超时） | ✅ 已按 SSE 标准配置 |
| Caddyfile / HTTPS 入口（SSE 分支关闭压缩与缓冲） | ⚠ 配置已写好，未在真实域名上签过证书 |
| **镜像实际构建与容器内运行** | ⚠ **未验证** —— 本机没有安装 Docker，无法执行 `docker compose up` |

所以你首次执行 `docker compose up -d --build` 时，若某个镜像构建报错，把报错贴给我，我按错误改 Dockerfile。最可能出现的两处：`chroma-hnswlib` 需要 `cmake`、以及国内 pip/maven 源速度问题（`.env` 里的 `PIP_INDEX_URL` 已预留）。

云服务器上的完整排错顺序（含 OOM、证书申请失败、80 被占用）见 `DEPLOY_CLOUD.md` 第十二节。
