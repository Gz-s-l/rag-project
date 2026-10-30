# 模块二：SpringBoot 主后端（聊天记录持久化 + SSE 转发）

架构中的位置：**Vue3 前端 ↔ 本服务(8080) ↔ FastAPI AI 服务(8000) + MySQL(3306)**

职责：
1. 用户聊天记录 MySQL 持久化（MyBatis-Plus）
2. WebClient 调用 FastAPI 的 SSE 流式接口（`POST /api/chat/stream`）
3. 把 SSE 流**原样**转发给前端（`GET /api/chat/stream`，供 EventSource 使用）

FastAPI 侧的接口路径 / 入参 / SSE 帧格式**零改动**；本服务是新增加的一层，只透传。

---

## 一、目录结构

```
backend/
├── pom.xml                                # SpringBoot 3.3.4 + WebFlux(WebClient) + MyBatis-Plus 3.5.7 + mysql-connector-j
├── dev_test_spring_sse.html               # 本模块调试页（EventSource 直连 8080）
└── src/main/
    ├── java/com/outfit/chat/
    │   ├── ChatBackendApplication.java    # 启动类
    │   ├── config/
    │   │   ├── AiServiceProperties.java   # ai.service.* 配置项
    │   │   ├── WebClientConfig.java       # WebClient Bean（读空闲超时，不掐长流）
    │   │   └── WebConfig.java             # CORS（开发期全放行，生产用 nginx 同域后可收紧）
    │   ├── controller/
    │   │   ├── ChatController.java        # 4 个接口（见下表）
    │   │   └── GlobalExceptionHandler.java
    │   ├── service/ChatStreamService.java # 核心：SSE 逐帧转发 + 落库时机控制
    │   ├── entity/ChatMessage.java        # chat_message 表实体
    │   ├── mapper/ChatMessageMapper.java  # MyBatis-Plus BaseMapper
    │   └── dto/                           # ApiResponse / ChatMessageVO
    └── resources/
        ├── application.yml                # 端口 8080、MySQL、ai.service 地址
        └── schema.sql                     # 建表语句（IF NOT EXISTS，每次启动自动执行）
```

## 二、接口清单

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/chat/stream?sessionId=&question=&userId=` | SSE 流式对话，**EventSource 专用**（模块四 Vue 对接这个） |
| POST | `/api/chat/stream`（JSON body） | 同上，curl 调试用 |
| GET | `/api/chat/history/{sessionId}` | 查聊天历史（MySQL，时间正序） |
| DELETE | `/api/chat/history/{sessionId}` | 清历史（MySQL + 转发 DELETE 给 FastAPI 清模型上下文记忆） |

SSE 帧格式（与 FastAPI 完全一致）：

```
data:{"type": "meta",  "sessionId": "...", "userId": 1, "question": "..."}
data:{"type": "delta", "content": "根据"}          ← N 帧，逐字
data:{"type": "done",  "sessionId": "...", "content": "完整答案", "deltaCount": 40}
data:{"type": "error", "message": "..."}           ← 仅出错时
```

## 三、本地运行步骤

前置：JDK 17+、MySQL 运行中（本机 3306，root/123456，密码在 `application.yml` 里改）。

```bash
# 1. 启动 FastAPI（模块一）
cd D:\Vscode\rag\outfit-chat\ai-service
python -m uvicorn main:app --port 8000

# 2. 编译 & 启动 SpringBoot（首次需 Maven，仓库根目录已带便携版）
cd D:\Vscode\rag
tools\apache-maven-3.9.9\bin\mvn -s tools\mvn-settings.xml -f outfit-chat\backend\pom.xml package -DskipTests
java -jar outfit-chat\backend\target\chat-backend-1.0.0.jar --server.port=8080

# 3. 浏览器打开 outfit-chat\backend\dev_test_sse.html（默认已指向 8080），直接对话
```

说明：
- 首次启动**自动建库建表**（URL 带 `createDatabaseIfNotExist=true` + schema.sql），无需手工执行 SQL；
- `--server.port=8080` 建议始终带上：部分环境有 `SERVER__PORT` 环境变量会把端口抢走；
- MySQL 连接失败时应用起不来，报错里会写明原因。

## 四、实测记录（2026-10-30，本机全部通过）

1. POST 版 SSE：40 帧 delta + meta + done，帧结构与 FastAPI 直连一致；
2. GET 版 SSE（EventSource 方式）：同样正常；
3. MySQL 落库：每轮对话 2 条（user 提问即时落库，assistant 答案在 done 帧到达后落库），历史接口按时间正序返回；
4. 多轮记忆：追问"换成上课穿"，模型记住了此前的沙漏型/黄皮/预算 300（FastAPI 侧记忆未动）；
5. DELETE：MySQL 删除 6 条 + FastAPI 侧上下文同步清除；
6. 容错：FastAPI 宕机时，前端收到标准 `{"type":"error"}` 帧，SpringBoot 不崩；
7. 参数校验：非法 sessionId / 空问题被拦截（Tomcat/控制器双层）。

## 五、落库策略（实现要点）

- 用户提问：收到请求立即 insert（流失败也留档）；
- AI 回答：以 done 帧里的完整答案为准 insert；若流中途异常，把已收到的 delta 拼接后 insert，内容不丢；
- 落库失败不阻断对话（日志告警）；
- 客户端中途关页面 → dispose 上游订阅，不浪费模型 tokens。

## 六、与 Docker 部署（最后统一做）的衔接

- 环境变量已预留：`AI_BASE_URL`（默认 http://127.0.0.1:8000，届时设为 http://ai-service:8000）、`MYSQL_HOST/MYSQL_PORT/MYSQL_DB/MYSQL_USER/MYSQL_PASSWORD`；
- MySQL 密码届时用环境变量注入，代码零改动；
- schema.sql 与最终交付的 init.sql 同源。
