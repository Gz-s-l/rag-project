"""对话接口（SSE 流式）

本模块只做「协议层」的事情：
    HTTP 请求 -> 参数校验 -> 调用原有 RAG 链 -> 把 token 流按 SSE 协议逐条推给调用方

原有 RAG 逻辑（rag.py / vector_stores.py / file_history_store.py）一行未改，
直接复用 RagService.chain.stream(...) 这个入口，和 Streamlit 版本的调用方式完全一致。

SSE 事件协议（每一帧固定为 `data: {JSON}\n\n`，不用 event: 命名事件，
这样 SpringBoot WebClient 和浏览器 EventSource 都只需要处理一种数据帧，实现最简单）：

    data: {"type":"meta",  "sessionId":"...","userId":1001,"question":"..."}
    data: {"type":"delta", "content":"您"}
    data: {"type":"delta", "content":"好"}
    data: {"type":"done",  "sessionId":"...","content":"您好……","deltaCount":12}
    data: {"type":"error", "message":"..."}

    客户端约定：
        1. 收到 delta 就追加到气泡；
        2. 收到 done 表示本轮结束，content 是完整答案，可直接落库；
        3. 收到 error 表示本轮失败，应保留已渲染内容并提示重试。
"""

import json
import logging
import threading
from typing import Any, Dict, Iterator, List, Optional

from fastapi import APIRouter, Path, Query
from fastapi.responses import StreamingResponse

import config_data as config
from file_history_store import get_history
from rag import RagService
from schemas import (
    ApiResponse,
    ChatRequest,
    HistoryVO,
    MessageVO,
    SESSION_ID_PATTERN,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# --------------------------------------------------------------------------
# RagService 单例
# --------------------------------------------------------------------------
# RagService 构造时会创建 DashScope 嵌入模型 + 打开 Chroma 向量库，属于重资源对象，
# 且内部无请求级状态（会话隔离靠 session_id），因此全局只创建一次。
_rag_service: Optional[RagService] = None
_rag_lock = threading.Lock()


def get_rag_service() -> RagService:
    """懒加载获取 RagService 单例（双检锁，避免并发首次请求重复初始化）"""
    global _rag_service
    if _rag_service is None:
        with _rag_lock:
            if _rag_service is None:
                logger.info("初始化 RagService（Chroma + Embedding + LLM）...")
                _rag_service = RagService()
                logger.info("RagService 初始化完成")
    return _rag_service


# --------------------------------------------------------------------------
# SSE 工具
# --------------------------------------------------------------------------
def sse_frame(payload: Dict[str, Any]) -> str:
    """把业务数据序列化成一帧 SSE

    用 JSON 承载内容而不是直接 `data: 文本`，原因是模型输出里会带换行，
    裸文本会把一帧拆成多帧导致前端解析错乱；JSON 会把换行转义成 \\n，天然安全。

    :param payload: 要推送的业务数据，必须含 type 字段
    :return: 符合 SSE 规范的一帧字符串
    """
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    # 关键：告诉 nginx 不要缓冲该响应，否则 token 会被攒成一坨才下发，失去流式效果
    "X-Accel-Buffering": "no",
}


def stream_chat(session_id: str, question: str, user_id: Optional[int] = None) -> Iterator[str]:
    """核心生成器：把 RAG 链的 token 流转成 SSE 帧

    :param session_id: 会话ID（对话记忆的隔离维度）
    :param question:   用户提问
    :param user_id:    用户ID，仅回显，不参与计算
    :return: SSE 帧生成器
    """
    yield sse_frame(
        {"type": "meta", "sessionId": session_id, "userId": user_id, "question": question}
    )

    try:
        service = get_rag_service()

        # 与原 Streamlit 版本等价：
        #   st.session_state["rag"].chain.stream({"input": prompt}, config=config.session_config)
        # 区别仅在于 session_id 由请求传入，而不是写死在 config.session_config 里。
        chain_config = {"configurable": {"session_id": session_id}}
        char_stream = service.chain.stream({"input": question}, config=chain_config)

        buffer: List[str] = []
        for chunk in char_stream:
            if not chunk:
                continue
            buffer.append(chunk)
            yield sse_frame({"type": "delta", "content": chunk})

        full_text = "".join(buffer)
        logger.info("会话[%s] 回答完成，片段数=%d，字符数=%d", session_id, len(buffer), len(full_text))
        yield sse_frame(
            {
                "type": "done",
                "sessionId": session_id,
                "content": full_text,
                "deltaCount": len(buffer),
            }
        )
    except Exception as exc:  # noqa: BLE001 - 流内异常必须转成 error 帧，不能直接抛出（响应头已发送）
        logger.exception("会话[%s] 流式回答失败", session_id)
        yield sse_frame({"type": "error", "message": f"{type(exc).__name__}: {exc}"})


# --------------------------------------------------------------------------
# 接口定义
# --------------------------------------------------------------------------
@router.post(
    "/stream",
    summary="流式对话（POST，主接口，供 SpringBoot WebClient 调用）",
    response_description="text/event-stream，帧格式见模块说明",
)
def chat_stream(body: ChatRequest) -> StreamingResponse:
    """流式对话

    入参（JSON Body）:
        - sessionId : str   必填，会话ID，字母/数字/下划线/中划线，1~64 位
        - question  : str   必填，用户提问，1~2000 字
        - userId    : int   选填，用户ID，仅回显
        - history   : list  选填，预留字段，当前不参与计算

    出参: text/event-stream
        - meta  帧：流开始，回显 sessionId / userId / question
        - delta 帧：content 为增量文本，前端按序追加
        - done  帧：content 为完整答案，deltaCount 为片段数
        - error 帧：流内异常，message 为错误描述
    """
    logger.info("收到对话请求 sessionId=%s userId=%s question=%s", body.sessionId, body.userId, body.question)
    return StreamingResponse(
        stream_chat(body.sessionId, body.question, body.userId),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get(
    "/stream",
    summary="流式对话（GET，便于浏览器 EventSource 直连调试）",
    response_description="text/event-stream，帧格式见模块说明",
)
def chat_stream_get(
    sessionId: str = Query(..., pattern=SESSION_ID_PATTERN, description="会话ID"),
    question: str = Query(..., min_length=1, max_length=2000, description="用户提问"),
    userId: Optional[int] = Query(None, description="用户ID（可选，仅回显）"),
) -> StreamingResponse:
    """流式对话（GET 版本）

    仅用于本地联调：浏览器原生 EventSource 不支持 POST，
    这个接口可以让前端在 SpringBoot 未就绪时直接连 FastAPI 验证流式效果。

    入参（Query）:
        - sessionId : str  必填
        - question  : str  必填
        - userId    : int  选填

    出参: text/event-stream，帧格式同 POST /stream
    """
    return StreamingResponse(
        stream_chat(sessionId, question, userId),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get(
    "/history/{sessionId}",
    summary="查询会话历史",
    response_model=ApiResponse,
)
def get_chat_history(
    sessionId: str = Path(..., pattern=SESSION_ID_PATTERN, description="会话ID")
) -> ApiResponse:
    """查询某个会话的历史消息

    数据来源：FastAPI 侧的本地文件存储（chat_history/<sessionId>），
    与 RAG 链做记忆时读的是同一份数据，因此这里看到的就是模型实际看到的上下文。

    入参（Path）:
        - sessionId : str  会话ID

    出参:
        - code    : int   0=成功
        - message : str   提示信息
        - data    : {sessionId, total, messages:[{role, content}]}
    """
    try:
        messages = get_history(sessionId).messages
    except Exception as exc:  # noqa: BLE001
        logger.exception("读取会话[%s]历史失败", sessionId)
        return ApiResponse(code=500, message=f"读取历史失败: {exc}", data=None)

    # LangChain 的消息类型 -> 前端通用角色名
    role_map = {"human": "user", "ai": "assistant", "system": "system"}
    items = [
        MessageVO(role=role_map.get(m.type, m.type), content=m.content)
        for m in messages
    ]
    return ApiResponse(
        data=HistoryVO(sessionId=sessionId, total=len(items), messages=items).model_dump()
    )


@router.delete(
    "/history/{sessionId}",
    summary="清空会话历史",
    response_model=ApiResponse,
)
def clear_chat_history(
    sessionId: str = Path(..., pattern=SESSION_ID_PATTERN, description="会话ID")
) -> ApiResponse:
    """清空某个会话的历史消息（相当于「新开会话」/「清空上下文」）

    入参（Path）:
        - sessionId : str  会话ID

    出参:
        - code    : int   0=成功
        - message : str   提示信息
    """
    try:
        get_history(sessionId).clear()
    except Exception as exc:  # noqa: BLE001
        logger.exception("清空会话[%s]历史失败", sessionId)
        return ApiResponse(code=500, message=f"清空历史失败: {exc}", data=None)
    return ApiResponse(message="已清空")
