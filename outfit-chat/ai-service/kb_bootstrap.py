"""知识库自动构建（启动时自动完成，无需手工导入文档）

做三件事：
    1. 把 corpus/ 下的精选语料按文件名顺序增量入库（用户素材排第一，优先入库）；
    2. 如果联网采集过期（默认 7 天）或手动强制，则调用 web_collector 扩充知识库；
    3. 把结果写进 data/kb_state.json，下次启动据此判断"哪些已经入过、要不要再联网"。

增量怎么实现：
    完全复用原项目 knowledge_base.py 里的 MD5 去重机制（check_md5 / save_md5）——
    同一段内容第二次入库会直接返回「[跳过]内容已经存在知识库中」，
    所以每次启动都可以无脑全量遍历，真正被向量化的只有新增内容，成本可控。

线程模型：
    构建在后台线程里跑，不阻塞服务启动（第一次启动就能开始接请求）。
    全局一把锁保证同一时刻只有一个构建任务；状态放在内存里供 /api/knowledge/status 查询。
"""

import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import config_data as config
from knowledge_base import KnowledgeBaseService
from web_collector import WebCollector

logger = logging.getLogger(__name__)

# 全局状态：供接口查询，避免每次都读文件
_lock = threading.Lock()
_thread: Optional[threading.Thread] = None
_status: Dict[str, Any] = {
    "running": False,
    "ready": False,
    "stage": "idle",          # idle / seed / web / done / failed
    "message": "尚未开始",
    "startedAt": None,
    "finishedAt": None,
    "seedFiles": 0,
    "seedNew": 0,
    "webDocs": 0,
    "webNew": 0,
    "chunks": 0,
    "errors": [],
}


# ----------------------------------------------------------------------
# 状态读写
# ----------------------------------------------------------------------
def _load_state() -> Dict[str, Any]:
    """读取构建状态文件，损坏或不存在时返回空结构"""
    try:
        with open(config.kb_state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取知识库状态文件失败，按首次构建处理：%s", exc)
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    """写入构建状态文件（原子写，避免中途崩溃留下半个文件）"""
    try:
        os.makedirs(os.path.dirname(config.kb_state_path), exist_ok=True)
        tmp = config.kb_state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, config.kb_state_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("写入知识库状态文件失败：%s", exc)


def get_status() -> Dict[str, Any]:
    """返回当前知识库构建状态（供 HTTP 接口使用）"""
    with _lock:
        snapshot = dict(_status)
    snapshot["webSearchEnabled"] = config.web_search_enabled
    snapshot["webSearchProvider"] = config.web_search_provider
    snapshot["refreshDays"] = config.web_refresh_days
    snapshot["collection"] = config.collection_name
    return snapshot


# ----------------------------------------------------------------------
# 语料入库
# ----------------------------------------------------------------------
def _read_text(path: str) -> str:
    """读取语料文件，UTF-8 优先，GBK 兜底"""
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
        except FileNotFoundError:
            return ""
    return ""


def _ingest_seed(service: KnowledgeBaseService) -> Dict[str, int]:
    """把 corpus/ 下的精选语料增量入库

    :return: {"files": 文件数, "new": 真正入库的文件数, "skipped": 命中 MD5 去重的文件数}
    """
    corpus_dir = config.corpus_directory
    if not os.path.isdir(corpus_dir):
        logger.warning("精选语料目录不存在：%s", corpus_dir)
        return {"files": 0, "new": 0, "skipped": 0}

    # 按文件名排序，00_ 开头的用户指定素材排在最前，优先入库
    filenames = sorted(
        f for f in os.listdir(corpus_dir) if f.lower().endswith((".txt", ".md"))
    )

    files = new = skipped = 0
    for name in filenames:
        text = _read_text(os.path.join(corpus_dir, name))
        if not text.strip():
            continue
        files += 1
        try:
            result = service.upload_by_str(text, name)
        except Exception as exc:  # noqa: BLE001
            logger.exception("语料入库失败：%s", name)
            _status["errors"].append(f"{name}: {exc}")
            continue

        if result == "success":
            new += 1
            logger.info("语料入库成功：%s（%d 字）", name, len(text))
        else:
            skipped += 1
            logger.info("语料已存在，跳过：%s", name)

    return {"files": files, "new": new, "skipped": skipped}


def _ingest_web(service: KnowledgeBaseService) -> Dict[str, int]:
    """联网采集 + 入库（失败自动降级，不影响已入库的本地语料）"""
    if not config.web_search_enabled:
        logger.info("联网采集已关闭（WEB_SEARCH_ENABLED=false）")
        return {"docs": 0, "new": 0}

    try:
        docs = WebCollector().collect()
    except Exception as exc:  # noqa: BLE001
        logger.warning("联网采集异常，已降级为仅使用本地语料：%s", exc)
        _status["errors"].append(f"web collect: {exc}")
        return {"docs": 0, "new": 0}

    new = 0
    for doc in docs:
        try:
            result = service.upload_by_str(doc.content, f"web_{doc.title[:30]}.txt")
            if result == "success":
                new += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("网络语料入库失败：%s（%s）", doc.url, exc)
            _status["errors"].append(f"web ingest {doc.url}: {exc}")

    return {"docs": len(docs), "new": new}


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------
def _collection_count(service: KnowledgeBaseService) -> int:
    """当前集合里有多少条向量（用于状态展示，失败返回 0）"""
    try:
        return service.chroma._collection.count()
    except Exception:  # noqa: BLE001
        return 0


def _run(force_web: bool) -> None:
    """构建主流程（在后台线程里执行）"""
    started = datetime.now()
    with _lock:
        _status.update(
            running=True, ready=False, stage="seed", errors=[],
            startedAt=started.strftime("%Y-%m-%d %H:%M:%S"),
            finishedAt=None, message="正在导入本地精选语料…",
            seedFiles=0, seedNew=0, webDocs=0, webNew=0,
        )

    state = _load_state()
    try:
        service = KnowledgeBaseService()
        before = _collection_count(service)

        # ---- 第一步：本地精选语料（必做，快）----
        seed = _ingest_seed(service)
        with _lock:
            _status.update(
                seedFiles=seed["files"], seedNew=seed["new"],
                stage="web", message="本地语料已就绪，检查是否需要联网扩充…",
            )
        logger.info(
            "本地语料处理完成：共 %d 个文件，新入库 %d，跳过 %d",
            seed["files"], seed["new"], seed["skipped"],
        )

        # ---- 第二步：判断是否需要联网采集 ----
        last_web = state.get("lastWebRun")
        need_web = force_web
        if not need_web and last_web:
            try:
                elapsed_days = (started - datetime.strptime(last_web, "%Y-%m-%d %H:%M:%S")).days
                need_web = elapsed_days >= config.web_refresh_days
            except ValueError:
                need_web = True
        elif not last_web:
            need_web = True

        if need_web:
            with _lock:
                _status["message"] = "正在联网采集穿搭干货（首次启动会久一点）…"
            web = _ingest_web(service)
            # 只有真正采到内容才更新"上次采集时间"，
            # 否则网络不通时会被标记成"已采集过"，之后 7 天都不再尝试。
            if web["docs"] > 0:
                state["lastWebRun"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with _lock:
                _status.update(webDocs=web["docs"], webNew=web["new"])
        else:
            web = {"docs": 0, "new": 0}
            logger.info("联网采集未过期（上次 %s），跳过", last_web)

        after = _collection_count(service)

        # ---- 第三步：落状态 ----
        state.update(
            {
                "version": 1,
                "lastRun": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "collection": config.collection_name,
                "chunks": after,
                "lastAdded": after - before,
                "seedFiles": seed["files"],
                "webDocs": web["docs"],
            }
        )
        _save_state(state)

        with _lock:
            _status.update(
                running=False, ready=after > 0, stage="done",
                chunks=after,
                finishedAt=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                message=f"知识库就绪：共 {after} 条向量（本次新增 {after - before} 条）",
            )
        logger.info("知识库构建完成：共 %d 条向量，本次新增 %d 条", after, after - before)

    except Exception as exc:  # noqa: BLE001 - 构建失败不能影响服务本身
        logger.exception("知识库构建失败")
        with _lock:
            _status.update(
                running=False, stage="failed",
                finishedAt=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                message=f"知识库构建失败：{exc}",
            )
            _status["errors"].append(str(exc))


def bootstrap_async(force_web: bool = False) -> bool:
    """后台触发一次构建

    :param force_web: 是否忽略缓存有效期，强制重新联网采集
    :return: True=已启动；False=已有任务在跑，本次忽略
    """
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            logger.info("知识库构建已在执行中，忽略本次触发")
            return False
        _thread = threading.Thread(
            target=_run, args=(force_web,), name="kb-bootstrap", daemon=True
        )
        _thread.start()
        return True


def wait_until_done(timeout: float = 300) -> bool:
    """等待构建结束（仅供本地脚本/测试使用，服务运行时不调用）"""
    t = _thread
    if t is None:
        return True
    t.join(timeout)
    return not t.is_alive()
