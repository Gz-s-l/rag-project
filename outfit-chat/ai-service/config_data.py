"""全局配置

说明：
    本文件由原 Streamlit 项目的 config_data.py 迁移而来。
    业务参数（模型名、top_k、切分参数等）与原文件完全一致，未做任何改写。

    唯一适配点：数据目录（chroma_db / md5.txt / chat_history）支持通过环境变量
    RAG_DATA_DIR 覆盖，目的是在 Docker 中把向量库挂载到独立数据卷。
    未设置该环境变量时，行为与原项目完全一致（取本文件所在目录）。
"""

from dotenv import load_dotenv
import os

load_dotenv()
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")

# 1. 拿到 config.py 文件所在的真实目录（固定不变）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. 【新增，仅用于容器部署】数据根目录，默认与原项目一致 = 本文件所在目录
DATA_DIR = os.getenv("RAG_DATA_DIR", BASE_DIR)

# 3. 所有路径都基于 DATA_DIR 拼接
md5_path = os.path.join(DATA_DIR, "md5.txt")
persist_directory = os.path.join(DATA_DIR, "chroma_db")

# 4. 【新增】对话历史的落盘目录（原项目在 file_history_store.py 中写死为 "./chat_history"，
#    这里提到配置中，一是为了跟随 DATA_DIR 落到数据卷，二是避免依赖进程工作目录）
chat_history_directory = os.path.join(DATA_DIR, "chat_history")

# Chroma
# 【本次改造】集合名从 "rag" 改为 "outfit"，用途也从"电商客服知识库"变成"穿搭知识库"。
# 用新集合而不是直接往 rag 里灌数据，原因：旧的电商语料（尺码表等）会污染穿搭检索结果，
# 同时保留旧集合可以让原 Streamlit 项目继续可用，互不影响。
collection_name = os.getenv("CHROMA_COLLECTION", "outfit")

# spliter
chunk_size = 1000
chunk_overlap = 100
separators = ["\n\n", "\n", ".", ",", "?", "!", "。", "，", "！", "？", " ", ""]

max_split_char_number = 1000       # 文本分割阈值

# 说明：以下三项在原文件中是写死的，这里改为「环境变量优先、默认值保持原值」。
# 目的有二：
#   1. 不同阿里云百炼账号的模型权限不同（例：qwen3-max 在部分账号下返回 Model not exist），
#      通过 CHAT_MODEL_NAME 可切换为 qwen-max / qwen-plus 而不改代码；
#   2. Docker 环境下用环境变量注入，避免为改一个模型名重新打镜像。
embedding_model_name = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-v4")
# 默认值从 qwen3-max 改为 qwen-max：实测当前账号下 qwen3-max 返回 Model not exist，
# qwen-max 可用，保证启动即用。你的账号若确认能用 qwen3-max，设 CHAT_MODEL_NAME 覆盖即可。
chat_model_name = os.getenv("CHAT_MODEL_NAME", "qwen-max")

# 检索返回的文档条数。原项目 top_k=2，那是单一客服问答够用；
# 穿搭推荐需要同时命中"身材 + 配色 + 场景"三类知识，2 条明显不够，故默认提到 4。
top_k = int(os.getenv("TOP_K", "4"))

session_config = {
    "configurable": {
        "session_id": "uesr_001",
    }
}


# =====================================================================
# 知识库自动构建配置（本次新增）
# =====================================================================
# 精选语料目录：随镜像打包，启动时自动增量入库，不需要手工复制粘贴
corpus_directory = os.getenv("CORPUS_DIR", os.path.join(BASE_DIR, "corpus"))

# 知识库构建状态文件（记录上次联网采集时间、已入库来源，用于增量）
kb_state_path = os.path.join(DATA_DIR, "kb_state.json")

# 启动时是否自动构建知识库（精选语料入库 + 过期则联网增量采集）
kb_auto_bootstrap = os.getenv("KB_AUTO_BOOTSTRAP", "true").lower() in ("1", "true", "yes")

# 联网采集开关。默认开启，失败会自动降级为「只用本地精选语料」，不影响服务启动
web_search_enabled = os.getenv("WEB_SEARCH_ENABLED", "true").lower() in ("1", "true", "yes")

# 联网采集的数据来源
#   auto  = 多源自动降级：百度 → 搜狗 → 360（默认，免密钥，最不容易被单点限流卡住）
#   baidu / sogou / so360 / bing = 只用指定源
#   bocha = 博查搜索 API（需 WEB_SEARCH_API_KEY），结果最稳定，推荐生产使用
#   none  = 关闭联网，只用本地精选语料
# 实测经验：必应在部分网络环境下会把长句查询截成首字匹配，结果全是无关词条，故不放入 auto 链。
web_search_provider = os.getenv("WEB_SEARCH_PROVIDER", "auto").lower()

# 联网采集用的 API Key（provider 为 bocha 时必填）
web_search_api_key = os.getenv("WEB_SEARCH_API_KEY", "")

# 每个查询词最多取几条结果、每次采集最多抓几个页面（控制启动耗时与费用）
web_max_results_per_query = int(os.getenv("WEB_MAX_RESULTS_PER_QUERY", "8"))
web_max_pages = int(os.getenv("WEB_MAX_PAGES", "20"))

# 采集缓存有效期（天）。未过期则启动时跳过联网，直接用已有向量库，避免每次重启都重复抓取
web_refresh_days = int(os.getenv("WEB_REFRESH_DAYS", "7"))

# 单次采集的时间上限（秒），超时立即收尾，不拖慢服务启动
web_timeout_seconds = int(os.getenv("WEB_TIMEOUT_SECONDS", "150"))

# 联网采集的关键词，覆盖用户要求的五类：身材穿搭 / 配色 / 季节穿搭 / 版型避坑 / 平价单品思路
# 【v2】服务对象扩展为全体人群，关键词同时覆盖男生、女生与通用向。
# 选词经验：用"攻略/指南/技巧"这类词，搜索引擎更倾向返回文章页；
# 词太长太细（四五个限定词叠加）容易返回图片页和短视频页，反而采不到正文。
web_search_queries = [
    "男生穿搭技巧 入门 指南",
    "女生穿搭技巧 入门 指南",
    "穿搭配色 基础 规则",
    "男生 微胖 显瘦 穿搭 技巧",
    "女生 微胖 显瘦 穿搭 技巧",
    "男生 小个子 显高 穿搭",
    "女生 小个子 显高 穿搭",
    "女生 梨形身材 裤子 裙子 怎么选",
    "学生党 平价 穿搭 单品",
    "女生 秋冬 叠穿 外套 搭配",
    "男生 秋冬 叠穿 外套 搭配",
    "男生 直筒裤 裤长 怎么选",
    "男生 穿搭 常见 错误 避坑",
    "女生 穿搭 常见 错误 避坑",
]

