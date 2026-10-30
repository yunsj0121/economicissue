"""Public-page inspection shared by collection and evidence captures.

No login, CAPTCHA solving, proxy bypass, or disabled certificate verification.
"""
import hashlib
import os
import re
import shutil
from datetime import datetime, timezone
from urllib.parse import urlsplit


def launch(chromium):
    options = {}
    executable = os.getenv("CHROMIUM_EXECUTABLE_PATH")
    if not executable and not os.path.isfile(chromium.executable_path):
        executable = shutil.which("chromium") or shutil.which("google-chrome")
    if executable:
        options["executable_path"] = executable
    proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    if proxy:
        options["proxy"] = {"server": proxy}
    return chromium.launch(**options)


def normalized(text):
    return re.sub(r"\s+", " ", text).strip()


def content_hash(text):
    return hashlib.sha256(normalized(text).encode()).hexdigest()


def assert_content(text, minimum=300):
    opening = normalized(text)[:500].lower()
    if any(s in opening for s in ("access denied", "verify you are human", "captcha",
                                  "로그인 후 이용", "로그인이 필요", "삭제된 게시", "삭제된 글",
                                  "존재하지 않는 게시", "접근 권한이 없")):
        raise ValueError("로그인·삭제·차단 화면으로 원문 확인 실패")
    if len(normalized(text)) < minimum:
        raise ValueError("원문 본문 부족")


def guarded_context(browser, allowed=None, **options):
    from .sources import public_url
    context = browser.new_context(viewport={"width": 1000, "height": 900},
                                  service_workers="block", **options)
    def guard(route):
        try:
            public_url(route.request.url)
            if allowed and route.request.resource_type in {"document", "xhr", "fetch"}:
                if not allowed(route.request.url):
                    return route.abort()
            route.continue_()
        except (ValueError, OSError):
            route.abort()
    context.route("**/*", guard)
    return context


def settle(page):
    # Bounded wait for dynamic article content; never assume HTTP 200 means an article.
    page.wait_for_timeout(700)
    page.evaluate("document.fonts.ready")


INSPECT = r"""({selectors, limit}) => {
    const main = selectors.map(s => document.querySelector(s)).find(e => e && e.innerText.trim().length >= 300);
    if (!main) throw new Error('본문 영역을 확인하지 못했습니다');
    function selector(e) {
        const parts = [];
        while (e && e.nodeType === 1) {
            if (e.id) { parts.unshift('#' + CSS.escape(e.id)); break; }
            let n = 1, p = e;
            while ((p = p.previousElementSibling)) if (p.tagName === e.tagName) n++;
            parts.unshift(e.tagName.toLowerCase() + ':nth-of-type(' + n + ')'); e = e.parentElement;
        }
        return parts.join(' > ');
    }
    const candidates = [];
    for (const e of main.querySelectorAll('table,p,img')) {
        if (candidates.length >= limit) break;
        const r = e.getBoundingClientRect(), text = e.innerText?.trim() || '';
        if (r.width < 300 || r.height < 20 || r.height > 1400) continue;
        if (e.tagName === 'IMG' && (!e.complete || e.naturalWidth < 400 || e.naturalHeight < 150)) continue;
        if (e.tagName !== 'IMG' && (text.length < 35 || text.length > 400)) continue;
        if (e.closest('nav,header,footer,aside,[class*=comment],[class*=profile]')) continue;
        candidates.push({selector:selector(e), text, kind:e.tagName === 'IMG' ? 'image' : 'text',
                         image_url:e.tagName === 'IMG' ? e.currentSrc || e.src : ''});
    }
    const meta = document.querySelector('meta[property="article:published_time"],meta[name="date"],meta[property="og:article:published_time"]');
    const time = main.querySelector('time[datetime]') || document.querySelector('time[datetime]');
    return {title:document.querySelector('h1')?.innerText || document.title,
            text:main.innerText, published:meta?.content || time?.dateTime || '',
            candidates};
}"""


def inspect_page(url, policy, allowed):
    from playwright.sync_api import sync_playwright
    from .sources import public_url
    public_url(url)
    if not allowed(url):
        raise ValueError("원문 수집 허용 상태를 확인하지 못했습니다")
    host = urlsplit(url).hostname
    site = policy.get("browser_sites", {}).get(host, {})
    selectors = site.get("selectors", ["article", "[role=main]", "main", ".se-main-container"])
    with sync_playwright() as p:
        browser = launch(p.chromium)
        try:
            context = guarded_context(browser, allowed)
            page = context.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if not response or response.status >= 400:
                raise ValueError("브라우저 원문 접속 실패")
            public_url(page.url)
            if not allowed(page.url):
                raise ValueError("이동된 원문 수집 불가")
            settle(page)
            data = page.evaluate(INSPECT, {"selectors": selectors, "limit": 8})
            assert_content(data["text"])
            candidates = []
            for item in data.pop("candidates"):
                item["id"] = content_hash(url + item["selector"])[:16]
                item["text_hash"] = content_hash(item["text"]) if item["kind"] == "text" else ""
                candidates.append(item)
            return {**data, "url": page.url, "capture_candidates": candidates,
                    "browser_verified": True, "access_state": "content_verified",
                    "checked_at": datetime.now(timezone.utc).isoformat()}
        finally:
            browser.close()
