import re
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/118.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

REQUEST_TIMEOUT = 12


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "")
    return text.strip()


def _fetch_html(url: str) -> Optional[str]:
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        # 站点多为GBK编码
        resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
        return resp.text
    except Exception as exc:
        print(f"[DailyBriefFetcher] 无法获取 {url}: {exc}")
        return None


def _extract_article_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    selectors = [
        "div#article",
        "div.article",
        "div.new_cont",
        "div.detail",
        "div.content",
        "div#Cnt-Main-Article-QQ",
    ]
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            text = node.get_text(" ", strip=True)
            if len(text) > 60:
                return text
    # fallback
    body = soup.body.get_text(" ", strip=True) if soup.body else soup.get_text(" ", strip=True)
    return body[:3000]


class BriefFetcherBase:
    """抓取器基类，返回原始帖子内容"""

    id: str = "base"
    name: str = "BaseFetcher"
    max_articles: int = 10

    def fetch_items(self) -> List[Dict]:
        raise NotImplementedError


class SampleStaticFetcher(BriefFetcherBase):
    """占位抓取器"""

    id = "sample_static"
    name = "示例抓取器"
    max_articles = 5

    def fetch_items(self) -> List[Dict]:
        now = datetime.now().isoformat()
        items = []
        for idx in range(self.max_articles):
            items.append(
                {
                    "title": f"示例主题 {idx + 1}",
                    "summary": "这里是示例摘要，用于展示每日简报界面效果。",
                    "category": ["维护公告解读", "物价变动分析", "高手攻略"][idx % 3],
                    "source": self.name,
                    "published_at": now,
                    "url": "https://xyq.yzz.cn/",
                    "score": 0.5,
                    "content": "示例内容，仅用于占位。",
                    "popularity": max(self.max_articles - idx, 1),
                }
            )
        return items


class YZZNewsFetcher(BriefFetcherBase):
    """叶子猪梦幻新闻"""

    id = "yzz_news"
    name = "叶子猪新闻"
    base_url = "https://xyq.yzz.cn/"
    max_articles = 12

    def fetch_items(self) -> List[Dict]:
        html = _fetch_html(self.base_url)
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        items: List[Dict] = []
        seen = set()
        selectors = [
            "div.m_hotnews ul li a",
            "div.m_list ul li a",
            "div.newslist ul li a",
            "div.newsList ul li a",
        ]

        def iter_links():
            found = []
            for selector in selectors:
                found.extend(soup.select(selector))
            if not found:
                found = soup.select("a")
            for a in found[:40]:
                yield a

        for a in iter_links():
            rank = len(items)
            title = _clean_text(a.get_text())
            href = a.get("href", "")
            if not title or len(title) < 6 or not href:
                continue
            if ".shtml" not in href and ".html" not in href:
                continue
            url = urljoin(self.base_url, href)
            if url in seen:
                continue
            seen.add(url)
            items.append(
                {
                    "title": title,
                    "url": url,
                    "source": self.name,
                    "category_hint": "新闻",
                    "published_at": datetime.now().isoformat(),
                    "content": "",
                    "popularity": max(self.max_articles - rank, 1),
                }
            )
            if len(items) >= self.max_articles:
                break

        return self._fill_contents(items)

    def _fill_contents(self, items: List[Dict]) -> List[Dict]:
        for item in items:
            html = _fetch_html(item["url"])
            if not html:
                continue
            item["content"] = _extract_article_text(html)
        return items


class YZZPriceFetcher(BriefFetcherBase):
    """叶子猪物价情报"""

    id = "yzz_price"
    name = "叶子猪物价"
    base_url = "https://xyq.yzz.cn/price/"
    max_articles = 10

    def fetch_items(self) -> List[Dict]:
        html = _fetch_html(self.base_url)
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        items: List[Dict] = []
        seen = set()
        selectors = [
            "div.price_list ul li a",
            "div.priceList ul li a",
            "ul.list li a",
        ]

        def iter_links():
            found = []
            for selector in selectors:
                found.extend(soup.select(selector))
            if not found:
                found = soup.select("a")
            for a in found[:40]:
                yield a

        for a in iter_links():
            rank = len(items)
            title = _clean_text(a.get_text())
            href = a.get("href", "")
            if not title or len(title) < 4 or not href:
                continue
            if ".shtml" not in href and ".html" not in href:
                continue
            url = urljoin(self.base_url, href)
            if url in seen:
                continue
            seen.add(url)
            items.append(
                {
                    "title": title,
                    "url": url,
                    "source": self.name,
                    "category_hint": "物价",
                    "published_at": datetime.now().isoformat(),
                    "content": "",
                    "popularity": max(self.max_articles - rank, 1),
                }
            )
            if len(items) >= self.max_articles:
                break

        return self._fill_contents(items)

    def _fill_contents(self, items: List[Dict]) -> List[Dict]:
        for item in items:
            html = _fetch_html(item["url"])
            if not html:
                continue
            item["content"] = _extract_article_text(html)
        return items


class OfficialNewsFetcher(BriefFetcherBase):
    """梦幻西游官网资讯/公告"""

    id = "official_news"
    name = "官网公告"
    base_url = "https://xyq.163.com/news/"
    max_articles = 10

    def fetch_items(self) -> List[Dict]:
        html = _fetch_html(self.base_url)
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        items: List[Dict] = []
        seen = set()
        selectors = [
            "div.m-cont ul li a",
            "div.news-list ul li a",
            "div.list ul li a",
        ]

        def iter_links():
            found = []
            for selector in selectors:
                found.extend(soup.select(selector))
            if not found:
                found = soup.select("a")
            for a in found[:40]:
                yield a

        for a in iter_links():
            rank = len(items)
            title = _clean_text(a.get_text())
            href = a.get("href", "")
            if not title or len(title) < 6 or not href:
                continue
            if "javascript" in href.lower():
                continue
            if not href.startswith("http"):
                href = urljoin(self.base_url, href)
            url = href
            if url in seen:
                continue
            seen.add(url)
            items.append(
                {
                    "title": title,
                    "url": url,
                    "source": self.name,
                    "category_hint": "公告",
                    "published_at": datetime.now().isoformat(),
                    "content": "",
                    "popularity": max(self.max_articles - rank, 1),
                }
            )
            if len(items) >= self.max_articles:
                break

        return self._fill_contents(items)

    def _fill_contents(self, items: List[Dict]) -> List[Dict]:
        for item in items:
            html = _fetch_html(item["url"])
            if not html:
                continue
            item["content"] = _extract_article_text(html)
        return items


class YZZFocusFetcher(BriefFetcherBase):
    """叶子猪今日焦点"""

    id = "yzz_focus"
    name = "叶子猪焦点"
    base_url = "https://xyq.yzz.cn/focus/"
    max_articles = 20

    def fetch_items(self) -> List[Dict]:
        html = _fetch_html(self.base_url)
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        container = soup.select_one("div#list ul.list") or soup.select_one("ul.list")
        if not container:
            return []
        items: List[Dict] = []
        lis = container.find_all("li", recursive=False)
        if not lis:
            lis = container.find_all("li")
        for idx, li in enumerate(lis):
            anchors = li.find_all("a")
            if not anchors:
                continue
            article_link = anchors[-1]
            title = _clean_text(article_link.get_text())
            href = article_link.get("href", "")
            if not title or not href:
                continue
            url = urljoin(self.base_url, href)
            summary_node = li.find("p")
            summary = _clean_text(summary_node.get_text()) if summary_node else ""
            date_span = li.find("span")
            published = ""
            if date_span:
                published = date_span.get_text(strip=True).strip("[]")
            published_iso = f"{published}T00:00:00" if published else datetime.now().isoformat()

            items.append(
                {
                    "title": title,
                    "url": url,
                    "source": self.name,
                    "category_hint": "热点",
                    "published_at": published_iso,
                    "content": summary,
                    "popularity": max(self.max_articles - idx, 1),
                }
            )
            if len(items) >= self.max_articles:
                break
        return items


class TiebaHotFetcher(BriefFetcherBase):
    """贴吧移动端热帖"""

    id = "tieba_hot"
    name = "贴吧热帖"
    api_url = "https://tieba.baidu.com/mo/q/m"
    max_articles = 8

    def fetch_items(self) -> List[Dict]:
        try:
            params = {"kw": "梦幻西游", "pn": "0"}
            resp = requests.get(
                self.api_url, params=params, headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT
            )
            resp.raise_for_status()
        except Exception as exc:
            print(f"[DailyBriefFetcher] 贴吧请求失败: {exc}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        items: List[Dict] = []
        for a in soup.select("div.ls a"):
            rank = len(items)
            title = _clean_text(a.get_text())
            href = a.get("href", "")
            if not title or not href:
                continue
            url = urljoin("https://tieba.baidu.com", href)
            content = self._fetch_thread_content(url)
            if not content:
                continue

            items.append(
                {
                    "title": title,
                    "url": url,
                    "source": self.name,
                    "category_hint": "攻略",
                    "published_at": datetime.now().isoformat(),
                    "content": content,
                    "popularity": max(self.max_articles - rank, 1),
                }
            )
            if len(items) >= self.max_articles:
                break
        return items

    def _fetch_thread_content(self, url: str) -> str:
        html = _fetch_html(url)
        if not html:
            return ""
        soup = BeautifulSoup(html, "lxml")
        posts = soup.select("div.d_post_content, div.lzl_single_post")
        if not posts:
            text = soup.get_text(" ", strip=True)
            return text[:2000]
        chunks = []
        for post in posts[:3]:
            text = post.get_text(" ", strip=True)
            if len(text) > 20:
                chunks.append(text)
        return " ".join(chunks)[:2500]


def build_default_fetchers() -> List[BriefFetcherBase]:
    """默认抓取器列表"""
    fetchers: List[BriefFetcherBase] = [
        YZZFocusFetcher(),
        YZZNewsFetcher(),
        YZZPriceFetcher(),
        OfficialNewsFetcher(),
        TiebaHotFetcher(),
    ]
    return fetchers

