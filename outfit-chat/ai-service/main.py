"""FastAPI 应用入口（模块一：AI 流式服务）

职责边界：
    本服务只负责「RAG 检索 + 大模型流式生成」，不处理用户体系、聊天记录落库。
    聊天记录持久化由 SpringBoot + MySQL 承担，FastAPI 只把 token 流推出去。

启动方式（本地，务必在本目录下执行，因为有相对模块导入）：
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

接口文档：
    http://localhost:8000/docs
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import api_chat
import api_knowledge
import config_data as config
import kb_bootstrap

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """应用生命周期钩子（FastAPI 新版推荐写法，替代 @app.on_event）

    启动时做两件事：
        1. 打印配置，便于排查；
        2. 【本次改造】在后台线程里自动构建知识库（本地精选语料 + 过期则联网增量采集）。

    RagService 仍然懒加载（Chroma + Embedding 初始化约 1~3 秒），
    这样容器能更快通过 healthcheck，首次对话的额外延迟可接受。
    """
    logger.info("AI 服务启动，数据目录=%s", config.DATA_DIR)
    logger.info(
        "对话模型=%s，嵌入模型=%s，topK=%s，集合=%s",
        config.chat_model_name,
        config.embedding_model_name,
        config.top_k,
        config.collection_name,
    )
    if not config.DASHSCOPE_API_KEY:
        logger.warning("未检测到 DASHSCOPE_API_KEY，调用大模型会失败，请检查环境变量或 .env")

    # 【本次改造】启动即自动装载知识库：
    #   本地精选语料必做（快）；联网采集按缓存有效期判断（慢，放后台不阻塞启动）。
    #   任何异常都会在 bootstrap 内部被捕获，绝不会因为知识库问题起不来服务。
    if config.kb_auto_bootstrap:
        kb_bootstrap.bootstrap_async(force_web=False)
        logger.info("已在后台启动知识库自动构建，进度可查询 GET /api/knowledge/status")
    else:
        logger.info("KB_AUTO_BOOTSTRAP=false，跳过知识库自动构建")

    yield
    logger.info("AI 服务已停止")


app = FastAPI(
    title="男生平价穿搭 AI 顾问 - AI 服务",
    version="1.1.0",
    lifespan=lifespan,
    description=(
        "由 Streamlit 项目迁移而来的 RAG 流式服务，本版本角色为「男生平价日常穿搭顾问（校园学生场景）」。\n\n"
        "- `POST /api/chat/stream`：SSE 流式对话，供 SpringBoot WebClient 调用\n"
        "- `GET  /api/chat/stream`：同上（GET 版），便于浏览器直接调试\n"
        "- `GET  /api/knowledge/status`：知识库自动构建进度\n"
        "- `GET  /api/knowledge/search`：向量检索预览（不调大模型，零成本）\n"
        "- 对话记忆由 `chat_history/<sessionId>` 维护，与原项目一致\n"
    ),
)

# 生产环境应由 nginx / SpringBoot 统一入口，浏览器不直连本服务；
# 这里放开 CORS 只是为了模块一本地用 EventSource 直连调试。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_chat.router, prefix="/api/chat", tags=["对话"])
app.include_router(api_knowledge.router, prefix="/api/knowledge", tags=["知识库"])


@app.get("/health", summary="健康检查", tags=["运维"])
def health() -> JSONResponse:
    """健康检查

    入参: 无

    出参:
        - status         : str  固定 ok
        - chatModel      : str  当前对话模型
        - embeddingModel : str  当前嵌入模型
        - topK           : int  检索 top_k
        - dataDir        : str  数据目录（向量库 / 会话历史所在位置）

    说明：不校验 DashScope 密钥连通性（会产生真实调用费用），
    只反映进程存活与配置加载情况，供 Docker healthcheck / SpringBoot 探活使用。
    """
    return JSONResponse(
        {
            "status": "ok",
            "chatModel": config.chat_model_name,
            "embeddingModel": config.embedding_model_name,
            "topK": config.top_k,
            "dataDir": config.DATA_DIR,
        }
    )
