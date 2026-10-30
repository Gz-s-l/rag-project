"""知识库管理接口

对应原 Streamlit 项目里的 app_file_uploader.py：
    Streamlit 版是「页面直接调 KnowledgeBaseService.upload_by_str()」，
    这里把它包成 HTTP 接口，内部调用的仍然是同一个类、同一个方法，入库逻辑（含 MD5 去重、
    文本切分、metadata 写入）完全没变。

注意：Chroma 本地持久化模式不支持多进程同时写，务必以单 worker 启动服务（见 Dockerfile）。
"""

import logging
import threading
from typing import Optional

from fastapi import APIRouter, File, Query, UploadFile

import kb_bootstrap
from knowledge_base import KnowledgeBaseService
from schemas import ApiResponse, KnowledgeTextRequest, KnowledgeUploadVO

logger = logging.getLogger(__name__)

router = APIRouter()

_kb_service: Optional[KnowledgeBaseService] = None
_kb_lock = threading.Lock()


def get_kb_service() -> KnowledgeBaseService:
    """懒加载获取 KnowledgeBaseService 单例"""
    global _kb_service
    if _kb_service is None:
        with _kb_lock:
            if _kb_service is None:
                _kb_service = KnowledgeBaseService()
    return _kb_service


def _decode(raw: bytes) -> tuple[str, str]:
    """把上传的字节解码成文本

    原 Streamlit 版本固定用 UTF-8 解码（uploader_file.getvalue().decode("utf-8")），
    这里保持 UTF-8 优先，额外补一个 GBK 兜底，避免中文 txt 直接报错。
    Windows 下导出的 txt 常见 GBK 编码，纯 UTF-8 会抛 UnicodeDecodeError。

    :return: (文本, 实际使用的编码)
    """
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    # 全部失败时用替换模式兜底，保证接口不 500
    return raw.decode("utf-8", errors="replace"), "utf-8(replace)"


@router.post(
    "/upload",
    summary="上传 TXT 文件到知识库（multipart/form-data）",
    response_model=ApiResponse,
)
async def upload_file(file: UploadFile = File(..., description="待入库的 TXT 文件")) -> ApiResponse:
    """上传 TXT 文件并写入向量库

    入参（multipart/form-data）:
        - file : UploadFile  必填，字段名固定为 file，建议 .txt

    出参:
        - code    : int   0=成功
        - message : str   提示信息
        - data    : {filename, encoding, charCount, result}
            result 取值：
                success        入库成功
                [跳过]...       内容 MD5 已存在，未重复入库
                [失败]...       向量写入异常

    说明:
        单文件建议不超过 5MB。这里一次性读入内存后交给原有切分器，
        与 Streamlit 版本行为一致。
    """
    filename = file.filename or "unnamed.txt"
    raw = await file.read()
    text, encoding = _decode(raw)

    logger.info("收到知识库上传：%s，%d 字节，编码=%s，字符数=%d", filename, len(raw), encoding, len(text))

    try:
        result = get_kb_service().upload_by_str(text, filename)
    except Exception as exc:  # noqa: BLE001
        logger.exception("知识库上传失败：%s", filename)
        return ApiResponse(code=500, message=f"入库异常: {exc}", data=None)

    return ApiResponse(
        data=KnowledgeUploadVO(
            filename=filename, encoding=encoding, charCount=len(text), result=result
        ).model_dump()
    )


@router.post(
    "/text",
    summary="直接提交文本到知识库（JSON）",
    response_model=ApiResponse,
)
def upload_text(body: KnowledgeTextRequest) -> ApiResponse:
    """直接把一段文本写入向量库（便于接口调试 / 批量灌数据）

    入参（JSON Body）:
        - filename : str  选填，默认 manual_input.txt，写入向量 metadata.source
        - content  : str  必填，正文

    出参:
        - code    : int   0=成功
        - message : str   提示信息
        - data    : {filename, encoding, charCount, result}
    """
    logger.info("收到知识库文本：%s，字符数=%d", body.filename, len(body.content))
    try:
        result = get_kb_service().upload_by_str(body.content, body.filename)
    except Exception as exc:  # noqa: BLE001
        logger.exception("知识库文本入库失败：%s", body.filename)
        return ApiResponse(code=500, message=f"入库异常: {exc}", data=None)

    return ApiResponse(
        data=KnowledgeUploadVO(
            filename=body.filename,
            encoding="text",
            charCount=len(body.content),
            result=result,
        ).model_dump()
    )


# --------------------------------------------------------------------------
# 以下为本次改造新增的接口（原有接口路径与出入参均未改动）
# --------------------------------------------------------------------------
@router.get(
    "/status",
    summary="查看知识库构建状态",
    response_model=ApiResponse,
)
def kb_status() -> ApiResponse:
    """查看知识库自动构建的进度与结果

    服务启动后会在后台自动构建知识库（本地精选语料 + 联网增量），
    这个接口用来确认"是否已经就绪"，避免在构建未完成时误判检索效果。

    入参: 无

    出参 data:
        - running        : bool  是否正在构建
        - ready          : bool  是否已就绪（向量条数 > 0）
        - stage          : str   idle / seed / web / done / failed
        - message        : str   人类可读的进度说明
        - startedAt      : str   本次开始时间
        - finishedAt     : str   本次结束时间
        - seedFiles      : int   处理的本地语料文件数
        - seedNew        : int   本次新入库的语料文件数
        - webDocs        : int   本次联网采集到的有效文档数
        - webNew         : int   其中新入库的数量
        - chunks         : int   当前集合内向量总条数
        - collection     : str   当前使用的 Chroma 集合名
        - errors         : list  构建过程中的错误（非致命）
    """
    return ApiResponse(data=kb_bootstrap.get_status())


@router.post(
    "/bootstrap",
    summary="手动触发知识库构建",
    response_model=ApiResponse,
)
def kb_bootstrap_trigger(
    force: bool = Query(False, description="true=忽略缓存有效期，强制重新联网采集"),
) -> ApiResponse:
    """手动触发一次知识库构建（异步执行，立即返回）

    入参（Query）:
        - force : bool  选填，默认 false。true 表示不管上次采集时间，重新联网采集。

    出参 data:
        - started : bool  是否成功启动（已有任务在跑时返回 false）

    典型用途：
        - 第一次部署后想立刻确认能不能联网采集；
        - 想手动补一次最新资料。
    """
    started = kb_bootstrap.bootstrap_async(force_web=force)
    return ApiResponse(
        message="已开始构建" if started else "已有构建任务在执行中",
        data={"started": started},
    )


@router.get(
    "/search",
    summary="知识库检索预览（调试用）",
    response_model=ApiResponse,
)
def kb_search(
    q: str = Query(..., min_length=1, description="检索问题"),
    k: int = Query(4, ge=1, le=20, description="返回条数，默认 4"),
) -> ApiResponse:
    """直接用向量检索看看命中什么内容（不调用大模型，零成本）

    入参（Query）:
        - q : str  必填，检索语句
        - k : int  选填，返回条数，默认 4

    出参 data:
        - query : str   检索语句
        - hits  : list  命中片段，每项含 content / source / createTime / score（距离，越小越相似）
    """
    try:
        pairs = get_kb_service().chroma.similarity_search_with_score(q, k=k)
    except Exception as exc:  # noqa: BLE001
        logger.exception("知识库检索预览失败")
        return ApiResponse(code=500, message=f"检索失败: {exc}", data=None)

    hits = []
    for doc, score in pairs:
        meta = doc.metadata or {}
        hits.append(
            {
                "content": doc.page_content[:400],
                "source": meta.get("source", ""),
                "createTime": meta.get("create_time", ""),
                "score": round(float(score), 4),
            }
        )
    return ApiResponse(data={"query": q, "hits": hits})
