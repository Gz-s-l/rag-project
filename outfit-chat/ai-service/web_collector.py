"""联网采集穿搭干货（离线一次性扩充知识库）

定位（很重要）：
    这个模块**只在服务启动时（或手动触发）跑一次**，用来扩充静态知识库。
    用户提问时**绝不联网**，问答走本地向量库检索，保证流式响应速度稳定。

它做什么：
    1. 按 config.web_search_queries 里的关键词搜索；
    2. 过滤掉电商/带货/短视频站点；
    3. 抓正文 → 去标签 → 逐行清洗（删广告、删奢侈品、删浮夸话术）；
    4. 通过"相关性校验"的文本才返回，交给 kb_bootstrap 入库。

设计原则：
    - 绝不阻塞启动：整体有时间上限，超时立刻收尾；
    - 绝不污染知识库：宁可少收，也不收广告和垃圾内容（校验不过一律丢弃）；
    - 绝不写死单一数据源：provider 可切换，抓不到就自动降级为只用本地语料。
"""

import hashlib
import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import config_data as config

logger = logging.getLogger(__name__)

# 伪装成普通浏览器，避免被直接拒绝
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 电商 / 带货 / 短视频站点：直接不抓（用户明确要求不收商品广告和带货链接）
_BLOCKED_DOMAINS = (
    "taobao.com", "tmall.com", "tmall.hk", "jd.com", "jd.hk", "pinduoduo.com",
    "yangkeduo.com", "1688.com", "vip.com", "suning.com", "dangdang.com",
    "xiaohongshu.com", "xhslink.com", "douyin.com", "kuaishou.com", "weidian.com",
    "youzan.com", "uniqlo.cn", "uniqlo.com", "mogu.com", "yohobuy.com",
)

# 奢侈品 / 高价潮牌：命中即丢弃该行（用户明确要求过滤）
_LUXURY_WORDS = (
    "LV", "路易威登", "Gucci", "古驰", "Prada", "普拉达", "Balenciaga", "巴黎世家",
    "Hermes", "爱马仕", "Chanel", "香奈儿", "Dior", "迪奥", "Burberry", "巴宝莉",
    "Supreme", "Off-White", "Stone Island", "奢侈品", "轻奢", "高定", "万元级",
)

# 导购 / 广告话术：命中即丢弃该行
_AD_WORDS = (
    "优惠券", "领券", "秒杀", "包邮", "下单", "加购", "购物车", "到手价", "券后",
    "直播间", "点击购买", "点击查看", "限时特", "限时优", "团购", "代购", "折扣码",
    "双十一", "618", "爆款", "淘口令", "复制链接", "扫码", "客服咨询", "立即抢购",
    "库存告急", "销量第一", "旗舰店", "正品保障", "七天无理由",
)

# 浮夸 / 网红话术：用户要求过滤网红浮夸内容
_HYPE_WORDS = (
    "炸街", "顶流", "天花板", "封神", "yyds", "绝绝子", "高级感拉满",
    "网红同款", "博主同款", "明星同款", "必入爆款", "谁穿谁好看",
)

# 穿搭相关性词：清洗后必须命中足够数量，才算“干货”
_RELEVANT_WORDS = (
    "穿搭", "搭配", "版型", "配色", "颜色", "直筒", "阔腿", "锥形", "剪裁",
    "上衣", "下装", "裤", "外套", "衬衫", "卫衣", "T恤", "夹克", "针织",
    "衣长", "裤长", "腰线", "显高", "显瘦", "面料", "垂感", "叠穿", "风格",
    "鞋", "袜子", "肩线", "层次", "深色", "浅色", "基础款",
)

# 明显是导航 / 版权 / 交互残渣的行
_NOISE_PATTERNS = (
    r"^首页", r"^登录", r"^注册", r"^下载", r"^版权", r"Copyright", r"^免责声明",
    r"^上一篇", r"^下一篇", r"^相关阅读", r"^广告", r"^举报", r"^分享到",
    r"^\s*\[?\d+\]\s*$", r"微信", r"公众号", r"扫码关注", r"本文来源", r"责任编辑",
)

# 跳转后如果还停在这些域名，说明是搜索站内聚合页（标题列表/图集），不是正文
_SEARCH_AGGREGATOR_HOSTS = ("www.baidu.com", "m.baidu.com", "www.sogou.com", "www.so.com")

# 搜索结果标题里出现这些词，说明是图片站/问答聚合/短视频，没有可读正文
_HIT_TITLE_BLACKLIST = (
    "百度图片", "图片大全", "百度知道", "百度百科", "抖音", "快手", "微博",
    "小红书", "淘宝", "京东", "天猫", "拼多多",
)

# provider=auto 时的尝试顺序：百度中文结果最准，被限流就换搜狗，再换 360
_PROVIDER_CHAIN = ("baidu", "sogou", "so360")


@dataclass
class SearchHit:
    """一条搜索结果"""
    title: str
    url: str
    snippet: str


@dataclass
class CollectedDoc:
    """一篇清洗完成、可以入库的文档"""
    title: str
    url: str
    query: str
    content: str

    @property
    def source(self) -> str:
        return f"web:{self.url}"

    @property
    def digest(self) -> str:
        """内容指纹，用于跨次启动去重"""
        return hashlib.md5(self.content.encode("utf-8")).hexdigest()


class WebCollector:
    """联网采集器：搜索 → 抓正文 → 清洗 → 相关性校验"""

    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ):
        self.provider = (provider or config.web_search_provider or "none").lower()
        self.api_key = api_key if api_key is not None else config.web_search_api_key
        self.deadline = time.time() + (timeout_seconds or config.web_timeout_seconds)
        self.max_results = config.web_max_results_per_query
        self.max_pages = config.web_max_pages

        # 显式跳过系统代理会导致某些内网环境抓不到，这里沿用环境代理设置
        self.session = requests.Session()
        self.session.headers.update(_HEADERS)

        self._seen_urls: Set[str] = set()
        self._seen_digests: Set[str] = set()
        # 反爬相关：预热标记 + 被判定不可用的搜索源 + 连续被拦次数
        self._warmed_up = False
        self._dead_providers: Set[str] = set()
        self._blocked_streak = 0

    # ------------------------------------------------------------------
    # 对外主流程
    # ------------------------------------------------------------------
    def collect(self, queries: Optional[List[str]] = None) -> List[CollectedDoc]:
        """按关键词批量采集

        :param queries: 关键词列表，默认取 config.web_search_queries
        :return: 清洗并校验通过的文档列表（可能为空，调用方需容忍）
        """
        if self.provider == "none":
            logger.info("联网采集已关闭（WEB_SEARCH_PROVIDER=none），仅使用本地精选语料")
            return []

        queries = queries or config.web_search_queries
        docs: List[CollectedDoc] = []
        fetched_pages = 0

        for query in queries:
            if self._timeout():
                logger.warning("联网采集达到时间上限，提前收尾（已处理 %d 个关键词）", queries.index(query))
                break
            if self._blocked_streak >= 2:
                logger.warning("搜索接口连续多次返回安全验证页，本轮停止采集（已入库的仍会保留）")
                break

            # 查询之间留个间隔，降低被判定为爬虫的概率（连续快速请求会立刻触发验证页）
            time.sleep(random.uniform(1.2, 2.2))

            hits = self.search(query, self.max_results)
            logger.info("关键词「%s」搜索到 %d 条结果", query, len(hits))

            for hit in hits:
                if fetched_pages >= self.max_pages or self._timeout():
                    break
                if not self._accept_url(hit.url) or hit.url in self._seen_urls:
                    continue

                self._seen_urls.add(hit.url)
                fetched_pages += 1

                html, final_url = self.fetch(hit.url)
                if not html:
                    continue
                # 跳转后落回搜索引擎站内（聚合页/图集/问答聚合），只有标题没有正文，直接丢弃
                final_host = (urlparse(final_url).hostname or "").lower()
                if final_host in _SEARCH_AGGREGATOR_HOSTS:
                    logger.debug("落回搜索站内聚合页，丢弃：%s", final_url[:80])
                    continue
                # 跳转后落到电商/短视频站（百度 link 会二次跳转），同样丢弃
                if self._is_blocked_host(final_url):
                    logger.debug("跳转到屏蔽站点，丢弃：%s", final_url[:80])
                    continue

                content = self.clean(html, hit.title)
                if not content:
                    logger.debug("清洗后不达标，丢弃：%s", hit.url)
                    continue

                digest = hashlib.md5(content.encode("utf-8")).hexdigest()
                if digest in self._seen_digests:
                    continue
                self._seen_digests.add(digest)

                docs.append(
                    CollectedDoc(title=hit.title, url=final_url, query=query, content=content)
                )
                logger.info("采集入库候选：%s（%d 字）", hit.title[:30], len(content))

                time.sleep(0.3)  # 轻微限速，别给站点压力

        logger.info("联网采集结束：抓取 %d 页，有效文档 %d 篇", fetched_pages, len(docs))
        return docs

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------
    def _warm_up(self) -> None:
        """先访问一次首页拿 Cookie（BAIDUID），再搜就明显不容易被拦"""
        if self._warmed_up:
            return
        self._warmed_up = True
        try:
            self.session.get("https://www.baidu.com/", timeout=10)
        except Exception as exc:  # noqa: BLE001
            logger.debug("预热失败（不影响后续尝试）：%s", exc)

    def search(self, query: str, count: int = 5) -> List[SearchHit]:
        """按关键词搜索

        provider=auto（默认）时按 _PROVIDER_CHAIN 依次尝试：
        某个源返回反爬验证页就被标记为"本轮不可用"，自动换下一个源。
        这也是为什么三个免密钥源都实现了一遍——单源在国内很容易被限流。

        :return: 命中的搜索结果（已过相关性初筛）；全部失败返回空列表
        """
        if self.provider != "auto":
            return self._search_one(self.provider, query, count)

        for name in _PROVIDER_CHAIN:
            if name in self._dead_providers:
                continue
            hits = self._search_one(name, query, count)
            if hits:
                return hits
        return []

    def _search_one(self, provider: str, query: str, count: int) -> List[SearchHit]:
        """调用单个搜索源，异常一律吞掉（采集是尽力而为，不能影响服务）"""
        try:
            if provider == "bocha":
                return self._search_bocha(query, count)
            if provider == "bing":
                return self._search_bing(query, count)
            if provider == "sogou":
                return self._search_sogou(query, count)
            if provider == "so360":
                return self._search_360(query, count)
            return self._search_baidu(query, count)
        except Exception as exc:  # noqa: BLE001
            logger.warning("搜索失败（%s / %s）：%s", provider, query, exc)
            return []

    def _search_baidu(self, query: str, count: int) -> List[SearchHit]:
        """解析百度搜索结果页（免密钥，中文结果质量最好，作为默认源）

        注意：百度结果里混有广告位和"百度图片/知道"这类站内聚合页，
        这里只做初筛（标题+摘要必须和穿搭相关），正文质量交给 clean() 把关。
        """
        self._warm_up()
        resp = self.session.get(
            "https://www.baidu.com/s",
            params={"wd": query, "rn": str(count)},
            timeout=15,
        )
        resp.raise_for_status()

        # 命中反爬验证页时直接放弃这轮，避免把验证页当正文入库
        if "百度安全验证" in resp.text or "wappass.baidu.com" in resp.url:
            self._blocked_streak += 1
            self._dead_providers.add("baidu")
            logger.warning("百度返回安全验证页，本轮跳过：%s", query)
            time.sleep(3.0)  # 退避一下再试下一个关键词
            return []
        self._blocked_streak = 0

        soup = BeautifulSoup(resp.text, "html.parser")
        hits: List[SearchHit] = []
        for item in soup.select("div.result, div.c-container"):
            link = item.select_one("h3 a")
            if not link or not link.get("href"):
                continue
            title = link.get_text(" ", strip=True)
            if not title:
                continue
            # 摘要优先取结构化摘要区，取不到就用整个容器文本（截断）
            snippet_tag = item.select_one(".c-abstract, div[class*='content-right'], .c-span-last")
            snippet = (
                snippet_tag.get_text(" ", strip=True)
                if snippet_tag
                else item.get_text(" ", strip=True)[:300]
            )
            hit = SearchHit(title=title, url=link["href"], snippet=snippet)
            if self._accept_hit(hit):
                hits.append(hit)
        return hits

    def _search_sogou(self, query: str, count: int) -> List[SearchHit]:
        """解析搜狗搜索结果页（免密钥，作为百度的备用源）

        搜狗的结果链接是站内相对跳转（/link?url=...），必须补全成绝对地址，
        requests 会自动跟随跳转拿到真实页面。
        """
        resp = self.session.get(
            "https://www.sogou.com/web",
            params={"query": query},
            timeout=15,
        )

        # 搜狗被限流时会 302 到 /antispider/（状态码可能是 200 也可能是 404），
        # 所以在 raise_for_status 之前先判掉，避免把反爬页当异常抛出刷日志
        if "antispider" in resp.url or "请输入验证码" in resp.text:
            self._dead_providers.add("sogou")
            logger.warning("搜狗触发反爬，本轮跳过：%s", query)
            return []
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        hits: List[SearchHit] = []
        for item in soup.select("div.vrwrap, div.rb, div.result"):
            link = item.select_one("h3 a")
            if not link or not link.get("href"):
                continue
            title = link.get_text(" ", strip=True)
            if not title:
                continue
            snippet = item.get_text(" ", strip=True).replace(title, "", 1)[:300]
            hit = SearchHit(
                title=title,
                url=urljoin("https://www.sogou.com/", link["href"]),
                snippet=snippet,
            )
            if self._accept_hit(hit):
                hits.append(hit)
        return hits

    def _search_360(self, query: str, count: int) -> List[SearchHit]:
        """解析 360 搜索结果页（免密钥，第三个备用源）"""
        resp = self.session.get(
            "https://www.so.com/s",
            params={"q": query},
            timeout=15,
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        hits: List[SearchHit] = []
        for item in soup.select("li.res-list, div.result"):
            link = item.select_one("h3 a")
            if not link or not link.get("href"):
                continue
            title = link.get_text(" ", strip=True)
            if not title:
                continue
            snippet = item.get_text(" ", strip=True).replace(title, "", 1)[:300]
            hit = SearchHit(
                title=title,
                url=urljoin("https://www.so.com/", link["href"]),
                snippet=snippet,
            )
            if self._accept_hit(hit):
                hits.append(hit)
        return hits

    def _search_bing(self, query: str, count: int) -> List[SearchHit]:
        """解析必应搜索结果页（免密钥）

        说明：搜索结果本身不可全信，命中结果还要过 _accept_hit 的相关性校验，
        这样可以挡掉"只匹配到半个词"的无关结果。
        """
        resp = self.session.get(
            "https://cn.bing.com/search",
            params={"q": query, "count": str(count)},
            timeout=15,
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        hits: List[SearchHit] = []
        for item in soup.select("li.b_algo"):
            link = item.select_one("h2 a")
            if not link or not link.get("href"):
                continue
            title = link.get_text(" ", strip=True)
            snippet_tag = item.select_one("p")
            snippet = snippet_tag.get_text(" ", strip=True) if snippet_tag else ""
            hit = SearchHit(title=title, url=link["href"], snippet=snippet)
            if self._accept_hit(hit):
                hits.append(hit)
        return hits

    def _search_bocha(self, query: str, count: int) -> List[SearchHit]:
        """博查（Bochaai）Web Search API，中文结果质量更好，需要 API Key"""
        if not self.api_key:
            logger.warning("WEB_SEARCH_PROVIDER=bocha 但未配置 WEB_SEARCH_API_KEY，跳过")
            return []

        resp = self.session.post(
            "https://api.bochaai.com/v1/web-search",
            json={"query": query, "count": count, "summary": True},
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
        values = (payload.get("data") or {}).get("webPages", {}).get("value", []) or []

        hits: List[SearchHit] = []
        for item in values:
            hit = SearchHit(
                title=item.get("name", ""),
                url=item.get("url", ""),
                snippet=item.get("summary") or item.get("snippet", ""),
            )
            if self._accept_hit(hit):
                hits.append(hit)
        return hits

    # ------------------------------------------------------------------
    # 抓取与清洗
    # ------------------------------------------------------------------
    def fetch(self, url: str) -> tuple:
        """抓取网页 HTML

        :return: (html, 最终URL)；失败返回 ("", url)。
                 返回最终 URL 是因为百度结果多是跳转链接，跳转后可能落回百度站内聚合页，
                 这种页面必须挡掉（它是标题列表，不是正文）。
        """
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                logger.debug("抓取失败 %s -> HTTP %s", url, resp.status_code)
                return "", url
            # 中文站点常把编码写成 ISO-8859-1，按内容嗅探纠正，否则取到的是乱码
            if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding or "utf-8"
            if len(resp.text) < 500:
                return "", url
            return resp.text, resp.url
        except Exception as exc:  # noqa: BLE001
            logger.debug("抓取异常 %s：%s", url, exc)
            return "", url

    def clean(self, html: str, title: str = "") -> str:
        """HTML → 纯文本 → 逐行过滤 → 质量校验

        :param html:  原始 HTML
        :param title: 页面标题，仅用于生成文首说明
        :return: 清洗后的文本；不达标返回空串（调用方据此丢弃）
        """
        text = self._html_to_text(html)
        kept: List[str] = []

        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if len(line) < 12:                 # 太碎，基本是导航或标题残片
                continue
            if self._is_noise(line):
                continue
            if self._has_any(line, _AD_WORDS):      # 广告导购
                continue
            if self._has_any(line, _LUXURY_WORDS):  # 奢侈品
                continue
            if self._has_any(line, _HYPE_WORDS):    # 网红浮夸
                continue
            if not self._has_any(line, _RELEVANT_WORDS):  # 和穿搭无关
                continue
            kept.append(line)

        if len(kept) < 4:
            return ""

        body = "\n".join(kept)
        # 相关性强度校验：有效干货里至少要出现 8 次穿搭相关词
        if self._count_relevant(body) < 8 or len(body) < 200:
            return ""
        # 文体校验：必须是"讲道理"的段落，不能是标题列表/图集（这类页面关键词密集但没有信息）
        if not self._looks_like_prose(body):
            logger.debug("不像正文（标题列表类页面），丢弃：%s", title[:20])
            return ""

        header = (
            f"【网络采集·男生穿搭干货】\n"
            f"主题：{title.strip()[:50] or '穿搭资料'}\n"
            f"说明：以下内容为公开穿搭经验整理，仅保留搭配逻辑与版型配色知识。\n"
        )
        return header + body

    @staticmethod
    def _html_to_text(html: str) -> str:
        """剥掉脚本样式和结构性标签，取正文文本"""
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "iframe", "nav",
                         "footer", "header", "aside", "form", "svg"]):
            tag.decompose()
        # 用换行分隔块级元素，避免整页挤成一行导致无法按行过滤
        for tag in soup.find_all(["p", "div", "li", "br", "h1", "h2", "h3", "h4", "tr"]):
            tag.append("\n")
        return soup.get_text("\n", strip=True)

    @staticmethod
    def _is_noise(line: str) -> bool:
        """导航、版权、引流残渣"""
        if "http://" in line or "https://" in line or "www." in line:
            return True
        return any(re.search(p, line) for p in _NOISE_PATTERNS)

    @staticmethod
    def _has_any(line: str, words) -> bool:
        return any(w in line for w in words)

    @staticmethod
    def _count_relevant(text: str) -> int:
        return sum(text.count(w) for w in _RELEVANT_WORDS)

    @staticmethod
    def _looks_like_prose(text: str) -> bool:
        """判断是不是"讲道理的正文"，而不是标题列表/图集

        判据：平均行长够长 + 有标点（标题列表两者都不满足）。
        这一关专门用来挡百度的"精选笔记""图片""知道"这类聚合页——
        它们关键词密度很高，但只有一串标题，入库只会污染检索。
        """
        lines = [ln for ln in text.split("\n") if ln.strip()]
        if not lines:
            return False
        avg_len = sum(len(ln) for ln in lines) / len(lines)
        punctuated = sum(1 for ln in lines if ("。" in ln or "，" in ln)) / len(lines)
        return avg_len >= 22 and punctuated >= 0.35

    def _accept_hit(self, hit: SearchHit) -> bool:
        """搜索结果初筛：不相关的、明显不是正文的，连抓都不抓"""
        # 图片站/问答聚合/短视频，点进去没有可读正文
        if any(bad in hit.title for bad in _HIT_TITLE_BLACKLIST):
            return False
        blob = f"{hit.title} {hit.snippet}"
        return self._count_relevant(blob) >= 2

    def _accept_url(self, url: str) -> bool:
        """URL 白名单校验：必须是 http(s)，且不在电商/带货站点黑名单"""
        if not url or not url.startswith(("http://", "https://")):
            return False
        return not self._is_blocked_host(url)

    @staticmethod
    def _is_blocked_host(url: str) -> bool:
        """判断 URL 是否落在电商/带货/短视频黑名单域名上"""
        host = (urlparse(url).hostname or "").lower()
        if not host:
            return True
        return any(bad in host for bad in _BLOCKED_DOMAINS)

    def _timeout(self) -> bool:
        return time.time() > self.deadline
