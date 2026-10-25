"""Direct public listings/RSS. No search key, browser, or LLM needed for discovery."""
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit


class Node:
    def __init__(self, tag="root", attrs=(), parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    def text(self):
        return " ".join(c.text() if isinstance(c, Node) else c for c in self.children).strip()

    def find(self, tag=None):
        result = []
        for child in self.children:
            if isinstance(child, Node):
                if tag is None or child.tag == tag:
                    result.append(child)
                result.extend(child.find(tag))
        return result


class DOM(HTMLParser):
    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.root = self.current = Node()
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        if self.current.tag not in {"script", "style"}:
            self.current.children.append(data)


def https_url(raw, base):
    raw = html.unescape(raw.strip())
    if raw.startswith("javascript:"):
        # Read an embedded URL literal; never execute website JavaScript.
        found = re.search(r"['\"](/[^'\"]+)['\"]", raw)
        if not found:
            return ""
        raw = found.group(1)
    url = urljoin(base, raw)
    p = urlsplit(url)
    if p.scheme == "http":
        url = urlunsplit(("https", p.netloc, p.path, p.query, ""))
    return url if urlsplit(url).scheme == "https" else ""


def date_iso(value):
    match = re.search(r"\b(20\d{2})[-./](\d{1,2})[-./](\d{1,2})\b", value or "")
    if match:
        try:
            return datetime(*map(int, match.groups()), tzinfo=timezone.utc).isoformat()
        except ValueError:
            return ""
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError):
        return ""


def context(anchor):
    node = anchor
    for _ in range(5):
        if node.tag in {"li", "tr", "article"}:
            return node
        if not node.parent:
            break
        node = node.parent
    return anchor.parent or anchor


def parse_listing(markup, source):
    rows, seen = [], set()
    for anchor in DOM(markup).root.find("a"):
        url = https_url(anchor.attrs.get("href", ""), source["url"])
        if not url or not re.search(source["detail_pattern"], url) or url in seen:
            continue
        box = context(anchor)
        title_nodes = [n for n in box.find() if "tit" in n.attrs.get("class", "").split()]
        title = (title_nodes[0].text() if title_nodes else anchor.text()).strip()
        if not title:
            continue
        seen.add(url)
        rows.append({"url": url, "title": re.sub(r"\s+", " ", title)[:180],
                     "published": date_iso(box.text()), "provider": source["id"], "kind": source["kind"]})
    return rows


def parse_feed(data, source):
    root = ET.fromstring(data)
    rows = []
    for item in root.findall(".//item"):
        title = html.unescape(item.findtext("title", "")).strip()
        url = https_url(item.findtext("link", ""), source["url"])
        if url and title:
            description = re.sub(r"<[^>]+>", " ", html.unescape(item.findtext("description", "")))
            rows.append({"url": url, "title": title, "summary": description[:500],
                         "published": date_iso(item.findtext("pubDate", "")),
                         "provider": source["id"], "kind": source["kind"]})
    return rows


def discover_direct(collector):
    rows, statuses = [], []
    for source in collector.policy.get("direct_sources", []):
        try:
            body, resolved = collector.fetch_public(source["url"])
            if source["format"] == "page":
                found = [{"url": resolved, "title": source["title"],
                          "kind": source["kind"], "provider": source["id"], "published": ""}]
            elif source["format"] == "rss":
                found = parse_feed(body, source)
            else:
                found = parse_listing(body.decode("utf-8", "replace"), source)
            if not found:
                raise ValueError("목록 항목 없음: 페이지 구조 또는 접근 상태 확인 필요")
            rows.extend(found[:collector.policy.get("per_provider_limit", 6)])
            statuses.append({"provider": source["id"], "status": "ok", "items": len(found), "url": resolved})
        except Exception as e:
            # Isolate a broken provider; never claim all sources were collected.
            statuses.append({"provider": source["id"], "status": "failed", "error": type(e).__name__, "url": source["url"]})
    return rows, statuses


def balanced(rows, limit, provider_cap):
    """Round-robin providers so an active community cannot crowd out reports."""
    queues = {}
    for row in sorted(rows, key=lambda r: r.get("score", 0), reverse=True):
        queues.setdefault(row.get("provider", "manual"), []).append(row)
    selected = []
    for i in range(provider_cap):
        for queue in queues.values():
            if i < len(queue) and len(selected) < limit:
                selected.append(queue[i])
    return selected


def kosis_data(params, key, fetch):
    """Operator-selected series using KOSIS's issued userStatsId; redact the key."""
    safe = {k: params[k] for k in ("userStatsId", "prdSe", "newEstPrdCnt") if k in params}
    if "userStatsId" not in safe:
        raise ValueError("KOSIS에서 발급한 통계자료 userStatsId가 필요합니다")
    url = "https://kosis.kr/openapi/statisticsData.do?" + urlencode(
        {**safe, "method": "getList", "apiKey": key, "format": "json", "jsonVD": "Y"})
    body, _ = fetch(url)
    records = json.loads(body)
    if not isinstance(records, list) or not records or any("err" in r for r in records):
        raise ValueError("KOSIS 통계 응답 오류")
    if len(records) > 200:
        raise ValueError("통계 범위를 200행 이하로 좁혀 주세요")
    return records

