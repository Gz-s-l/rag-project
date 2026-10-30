# =====================================================================
# 模块一 / 模块四：AI 服务镜像（FastAPI + RAG + SSE）
# 单独构建：docker build -t outfit-ai-service:1.0.0 ./ai-service
# 单独运行：docker run -p 8000:8000 -e DASHSCOPE_API_KEY=xxx outfit-ai-service:1.0.0
# 编排启动：在项目根目录 docker compose up -d --build
# =====================================================================
FROM python:3.12-slim

# PYTHONUNBUFFERED：日志实时输出，docker logs 才能看到流式过程
# ANONYMIZED_TELEMETRY：关闭 Chroma 匿名上报，容器内无外网时避免无谓重试
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai \
    ANONYMIZED_TELEMETRY=False \
    RAG_DATA_DIR=/app/data \
    LOG_LEVEL=INFO

WORKDIR /app

# build-essential：chroma-hnswlib 在没有匹配 wheel 时需要现场编译
# libgomp1：onnxruntime（chromadb 依赖）运行期需要的 OpenMP 库，slim 镜像默认没有
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖再拷代码，充分利用 Docker 层缓存
# PIP_INDEX_URL：国内构建可传清华/阿里镜像加速，不传则用官方源
ARG PIP_INDEX_URL=""
COPY requirements.txt .
RUN if [ -n "$PIP_INDEX_URL" ]; then \
        pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt; \
    else \
        pip install --no-cache-dir -r requirements.txt; \
    fi \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

# 业务代码（其中 rag.py / vector_stores.py / knowledge_base.py / file_history_store.py
# 为原项目原样迁移，未改写逻辑）
COPY . .

# 数据目录：向量库、md5 去重记录、会话历史都落在这里
# 基础向量库随镜像带一份，容器起来即可问答；生产环境用数据卷覆盖 /app/data
RUN mkdir -p /app/data/chat_history \
    && if [ -d /app/chroma_db ]; then cp -r /app/chroma_db /app/data/chroma_db; fi \
    && if [ -f /app/md5.txt ]; then cp -f /app/md5.txt /app/data/md5.txt; fi

EXPOSE 8000

# 健康检查：用 Python 标准库发请求，避免额外安装 curl
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status==200 else 1)"

# 必须单 worker：Chroma 本地持久化 + 文件型会话历史都不支持多进程并发写
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
