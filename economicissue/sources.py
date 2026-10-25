"""Bounded discovery and extraction. No model calls in this module."""
import hashlib
import html
import ipaddress
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import io
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

AGENT = "EconomicIssueBot/0.1"


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", text))).strip()


def canonical(url):
    p = urllib.parse.urlsplit(url)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(p.query)
             if not k.startswith("utm_") and k not in {"fbclid", "gclid"}]
    return urllib.parse.urlunsplit((p.scheme, p.netloc.lower(), p.path or "/",
                                    urllib.parse.urlencode(query), ""))


def public_url(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError("공개 HTTPS 주소만 지원합니다")
    for info in socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise ValueError("내부 주소는 수집하지 않습니다")


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def request(url, headers=None, data=None):
    public_url(url)
    url = urllib.parse.quote(url, safe=":/?&=%+;,@!$'()*[]~")
    req = urllib.request.Request(url, data=data, headers={"User-Agent": AGENT, **(headers or {})})
    with urllib.request.build_opener(SafeRedirect).open(req, timeout=45) as response:
        body = response.read(20_000_001)
        if len(body) > 20_000_000:
            raise ValueError("응답 크기 초과")
        return body, response.url


class Collector:
    def __init__(self, policy, cache):
        self.policy, self.cache = policy, Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.robots = {}
        self.last_request = {}
        self.statuses = []

    def cached_json(self, key, loader):
        path = self.cache / (hashlib.sha256(key.encode()).hexdigest() + ".json")
        if path.exists() and time.time() - path.stat().st_mtime < self.policy["cache_hours"] * 3600:
            return json.loads(path.read_text(encoding="utf-8"))
        result = loader()
        path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        return result

    def search(self, query, web=False):
        client, secret = os.getenv("NAVER_CLIENT_ID"), os.getenv("NAVER_CLIENT_SECRET")
        if not client or not secret:
            raise ValueError("자동 탐색에는 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET이 필요합니다")
        kind = "webkr" if web else "news"
        params = {"query": query, "display": self.policy["search_limit"]}
        if not web:
            params["sort"] = "date"
        url = "https://openapi.naver.com/v1/search/" + kind + ".json?" + urllib.parse.urlencode(params)
        def load():
            body, _ = request(url, {"X-Naver-Client-Id": client, "X-Naver-Client-Secret": secret})
            return json.loads(body)["items"]
        return self.cached_json(url, load)

    def allowed(self, url):
        p = urllib.parse.urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self.robots:
            parser = urllib.robotparser.RobotFileParser()
            try:
                body, _ = request(origin + "/robots.txt")
                parser.parse(body.decode("utf-8", "replace").splitlines())
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    parser.parse([])
                else:
                    return False
            except (OSError, ValueError):
                return False
            self.robots[origin] = parser
        return self.robots[origin].can_fetch(AGENT, url)

    def fetch_public(self, url):
        def load():
            if not self.allowed(url):
                raise ValueError("robots 또는 접속 오류로 수집 제외")
            host = urllib.parse.urlsplit(url).netloc
            interval = self.policy.get("request_interval_seconds", 1)
            time.sleep(max(0, interval - (time.monotonic() - self.last_request.get(host, 0))))
            self.last_request[host] = time.monotonic()
            body, resolved = request(url)
            if not self.allowed(resolved):
                raise ValueError("이동된 원문 수집 불가")
            return {"body": body.hex(), "url": resolved}
        value = self.cached_json("public:" + url, load)
        return bytes.fromhex(value["body"]), value["url"]

    def pdf_text(self, body):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(body))
        pages = []
        for number, page in enumerate(reader.pages[:self.policy.get("max_pdf_pages", 40)], 1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(f"[PDF p.{number}]\n{text[:10000]}")
        text = "\n".join(pages)
        if len(text) < 300:
            raise ValueError("PDF 본문 부족: 스캔 문서 OCR은 지원하지 않습니다")
        return text, len(reader.pages)

    def browser_pdf(self, url):
        """Click actual public PDF links; do not guess hidden download endpoints."""
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                context = browser.new_context(accept_downloads=True, service_workers="block")
                host = urllib.parse.urlsplit(url).hostname
                def guard(route):
                    try:
                        public_url(route.request.url)
                        if route.request.resource_type in {"image", "font", "media"}:
                            return route.abort()
                        if urllib.parse.urlsplit(route.request.url).hostname != host:
                            return route.abort()
                        if not self.allowed(route.request.url):
                            return route.abort()
                        route.continue_()
                    except (OSError, ValueError):
                        route.abort()
                context.route("**/*", guard)
                page = context.new_page()
                response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if not response or response.status >= 400:
                    raise ValueError("보고서 상세 접속 실패")
                links = page.locator("a").filter(has_text=re.compile(r"\.pdf|다운로드\s*\(PDF\)", re.I))
                if not links.count():
                    raise ValueError("공개 PDF 다운로드 링크 없음")
                with page.expect_download(timeout=30000) as event:
                    links.first.click()
                download = event.value
                if download.failure():
                    raise ValueError("PDF 다운로드 실패")
                public_url(download.url)
                if not self.allowed(download.url):
                    raise ValueError("첨부 파일 수집 불가")
                path = Path(download.path())
                if path.stat().st_size > 20_000_000:
                    raise ValueError("PDF 크기 초과")
                body = path.read_bytes()
                if not body.startswith(b"%PDF"):
                    raise ValueError("PDF 형식이 아닙니다")
                return body
            finally:
                browser.close()

    def extract(self, url):
        url = canonical(url)
        def load():
            body, resolved = self.fetch_public(url)
            if body.startswith(b"%PDF"):
                text, total_pages = self.pdf_text(body)
                return {"url": resolved, "title": urllib.parse.unquote(urllib.parse.urlsplit(resolved).path.rsplit('/', 1)[-1]),
                        "published": "", "text": text, "pdf_pages": total_pages,
                        "retrieved": datetime.now(timezone.utc).isoformat()}
            import trafilatura
            doc = trafilatura.bare_extraction(body, url=resolved, include_comments=False,
                                              include_tables=True, with_metadata=True)
            text = (doc.text or "").strip() if doc else ""
            pdf_note = ""
            host = urllib.parse.urlsplit(resolved).hostname or ""
            if host in {"www.hanaif.re.kr", "hanaif.re.kr", "www.kbfg.com", "kbfg.com"}:
                # Reports often expose only a summary in HTML. Parse the actual attachment.
                from .direct import DOM, https_url
                anchors = DOM(body.decode("utf-8", "replace")).root.find("a")
                pdfs = [https_url(a.attrs.get("href", ""), resolved) for a in anchors
                        if re.search(r"\.pdf(?:$|[?#])", a.attrs.get("href", ""), re.I)]
                try:
                    pdf = self.fetch_public(pdfs[0])[0] if pdfs else self.browser_pdf(resolved)
                    pdf_text, total_pages = self.pdf_text(pdf)
                    text = pdf_text + ("\n[공식 HTML 설명]\n" + text if text else "")
                except Exception as e:
                    pdf_note = "첨부 미수집: " + type(e).__name__
                    if len(text) < 300:
                        raise ValueError("첨부 수집 실패 및 HTML 근거 부족") from e
            if len(text) < 300:
                raise ValueError("본문 부족: 로그인·차단 또는 근거 부족")
            if any(w in text[:300].lower() for w in ("access denied", "captcha", "로그인 후 이용")):
                raise ValueError("접근 제한 원문 제외")
            return {"url": canonical(resolved), "title": clean(doc.title or "") if doc else "",
                    "published": doc.date or "" if doc else "", "text": text, "attachment_note": pdf_note,
                    "retrieved": datetime.now(timezone.utc).isoformat()}
        return self.cached_json("article:" + url, load)


def discover(collector, manual=()):
    p, rows, errors = collector.policy, [], []
    if not manual:
        from .direct import discover_direct
        rows, collector.statuses = discover_direct(collector)
    for query, web in [(q, False) for q in p["queries"]] + [(q, True) for q in p["official_queries"]]:
        if manual:
            break
        try:
            for item in collector.search(query, web):
                title = clean(item["title"])
                if any(w in title for w in p["exclude"]):
                    continue
                published = item.get("pubDate", "")
                if published:
                    age = (datetime.now(timezone.utc) - parsedate_to_datetime(published)).days
                    if age < 0 or age > p["max_age_days"]:
                        continue
                score = sum(w in title for w in p["keywords"]) + bool(re.search(r"\d", title))
                rows.append({"url": item.get("originallink") or item["link"],
                             "title": title, "score": score, "provider": "naver", "kind": "report" if web else "news"})
        except (OSError, ValueError, KeyError) as e:
            errors.append(f"검색 {query}: {type(e).__name__}")
    rows.extend({"url": u, "title": "수동 원문", "score": 99, "provider": "manual", "kind": "manual"} for u in manual)
    unique = {}
    for row in rows:
        title = row["title"] + " " + row.get("summary", "")
        relevance = sum(w in title for w in p["keywords"])
        if row["kind"] != "manual" and (not relevance or any(w in title for w in p["exclude"])):
            continue
        if row.get("published"):
            try:
                published = datetime.fromisoformat(row["published"])
                days = (datetime.now(timezone.utc) - published).days
                maximum = p["max_age_days"] if row["kind"] in {"news", "community"} else p.get("report_age_days", 120)
                if days < 0 or days > maximum:
                    continue
            except ValueError:
                pass
        row["score"] = row.get("score", 0) + relevance + bool(re.search(r"\d", title))
        unique.setdefault(canonical(row["url"]), row)
    from .direct import balanced
    return balanced(list(unique.values()), p["candidate_limit"], p.get("per_provider_limit", 6)), errors


def compact(text, keywords, limit):
    """Keep opening context and relevant paragraphs in their original order."""
    blocks = [s.strip() for s in text.splitlines() if s.strip()]
    ranked = sorted(range(len(blocks)), key=lambda i: (i == 0, sum(k in blocks[i] for k in keywords)), reverse=True)
    selected, used = [], 0
    for i in ranked:
        block = blocks[i][:limit]
        if used + len(block) <= limit:
            selected.append(i)
            used += len(block) + 1
    return "\n".join(blocks[i][:limit] for i in sorted(selected))[:limit]
