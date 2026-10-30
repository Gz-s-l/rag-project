"""接口入参 / 出参定义（Pydantic v2）

约定：
    1. 字段名统一使用 lowerCamelCase，与 Vue 前端 / SpringBoot 的 Java 命名保持一致，
       避免跨端序列化时再做字段名映射。
    2. 每个字段都带 description，FastAPI 会自动生成 /docs 可交互文档。
    3. 会话 ID 会被用作对话历史文件名，因此必须做字符白名单校验，防止路径穿越。
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# 会话ID白名单：只允许字母、数字、下划线、中划线，长度 1~64
# 原因：该值会被拼进 chat_history/<sessionId> 文件路径，必须阻断 "../" 之类的穿越写法
SESSION_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


# --------------------------------------------------------------------------
# 对话接口
# --------------------------------------------------------------------------
class ChatRequest(BaseModel):
    """POST /api/chat/stream 请求体"""

    sessionId: str = Field(
        ...,
        pattern=SESSION_ID_PATTERN,
        description="会话ID，同一会话的多轮对话共享该ID，用于加载对话历史。仅允许字母/数字/下划线/中划线。",
        examples=["session_1001"],
    )
    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="用户本轮提问内容，长度 1~2000 字符。",
        examples=["你们的退换货政策是什么？"],
    )
    userId: Optional[int] = Field(
        default=None,
        description="用户ID（可选）。FastAPI 侧当前不落库，仅原样透传回 meta 事件，供 SpringBoot 关联用户。",
        examples=[1001],
    )
    history: Optional[List["HistoryItem"]] = Field(
        default=None,
        description=(
            "历史对话（可选）。默认传 null 即可——对话记忆由 FastAPI 侧的本地文件存储维护，"
            "由 sessionId 决定。该字段预留给后续「由 SpringBoot 的 MySQL 提供历史」的切换方案，"
            "当前不参与 RAG 链计算。"
        ),
    )


class HistoryItem(BaseModel):
    """一条历史消息"""

    role: str = Field(..., description="角色：user / assistant / system", examples=["user"])
    content: str = Field(..., description="消息内容")


class ChatMeta(BaseModel):
    """SSE 事件：meta（流开始）"""

    type: str = Field("meta", description="事件类型，固定 meta")
    sessionId: str = Field(..., description="会话ID（回显）")
    userId: Optional[int] = Field(None, description="用户ID（回显）")
    question: str = Field(..., description="本轮提问（回显）")


class ChatDelta(BaseModel):
    """SSE 事件：delta（增量文本）"""

    type: str = Field("delta", description="事件类型，固定 delta")
    content: str = Field(..., description="本次增量文本片段，前端需按顺序追加")


class ChatDone(BaseModel):
    """SSE 事件：done（流结束）"""

    type: str = Field("done", description="事件类型，固定 done")
    sessionId: str = Field(..., description="会话ID")
    content: str = Field(..., description="完整回答（所有 delta 拼接结果），便于服务端直接落库")
    deltaCount: int = Field(..., description="本次流共推送的增量片段数量")


class ChatError(BaseModel):
    """SSE 事件：error（流内异常）"""

    type: str = Field("error", description="事件类型，固定 error")
    message: str = Field(..., description="错误信息，前端应提示用户并允许重试")


# --------------------------------------------------------------------------
# 对话历史接口
# --------------------------------------------------------------------------
class MessageVO(BaseModel):
    """历史消息出参"""

    role: str = Field(..., description="角色：user / assistant / system")
    content: str = Field(..., description="消息内容")


class HistoryVO(BaseModel):
    """GET /api/chat/history/{sessionId} 出参 data"""

    sessionId: str = Field(..., description="会话ID")
    total: int = Field(..., description="消息总条数")
    messages: List[MessageVO] = Field(..., description="按时间正序排列的历史消息")


# --------------------------------------------------------------------------
# 知识库接口
# --------------------------------------------------------------------------
class KnowledgeUploadVO(BaseModel):
    """知识库上传出参 data"""

    filename: str = Field(..., description="上传的文件名")
    encoding: str = Field(..., description="解析文件时使用的编码")
    charCount: int = Field(..., description="解析出的正文字符数")
    result: str = Field(
        ...,
        description="入库结果，取值：success（入库成功）/ [跳过]...（MD5 重复）/ [失败]...（写入异常）",
    )


class KnowledgeTextRequest(BaseModel):
    """POST /api/knowledge/text 请求体"""

    filename: str = Field(
        default="manual_input.txt",
        description="文档名，会写入向量的 metadata.source 字段，检索时可用于溯源。",
        examples=["退换货政策.txt"],
    )
    content: str = Field(..., min_length=1, description="纯文本内容", examples=["七天无理由退换货……"])


# --------------------------------------------------------------------------
# 通用响应包装（非 SSE 接口使用）
# --------------------------------------------------------------------------
class ApiResponse(BaseModel):
    """统一响应结构

    code: 0 表示成功，非 0 表示失败（与 SpringBoot 侧保持同一套约定）
    """

    code: int = Field(0, description="业务状态码，0=成功")
    message: str = Field("success", description="提示信息")
    data: Optional[Any] = Field(None, description="业务数据")


ChatRequest.model_rebuild()
