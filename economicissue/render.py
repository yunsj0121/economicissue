"""Deterministic Korean images; optional permitted source captures."""
import os
from pathlib import Path
from urllib.parse import urlsplit
from PIL import Image, ImageDraw, ImageFont, ImageOps
from .sources import public_url


def font_path():
    paths = [os.getenv("KOREAN_FONT", ""), "C:/Windows/Fonts/malgunbd.ttf",
             "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"]
    for path in paths:
        if path and Path(path).is_file():
            return path
    raise ValueError("한글 폰트 경로 KOREAN_FONT를 설정하세요")


def wrap(text, font, width):
    result = []
    for paragraph in text.splitlines():
        line = ""
        for ch in paragraph:
            if font.getlength(line + ch) > width:
                result.append(line)
                line = ""
            line += ch
        result.append(line)
    return result


def draw_image(path, title, text, footer, thumbnail=False, background=None):
    image = Image.new("RGB", (1080, 1080), "#142d35" if thumbnail else "#f5f3ed")
    if background:
        with Image.open(background) as original:
            image = ImageOps.fit(original.convert("RGB"), (1080, 1080))
        image = Image.blend(image, Image.new("RGB", image.size, "#09191f"), 0.65)
    draw = ImageDraw.Draw(image)
    ink = "#ffffff" if thumbnail else "#17333c"
    draw.rectangle((70, 85, 190, 99), fill="#e9ba53")
    fp = font_path()
    title_font = ImageFont.truetype(fp, 80 if thumbnail else 55)
    lines = wrap(title, title_font, 920)
    y = 230 if thumbnail else 170
    for line in lines:
        draw.text((80, y), line, fill=ink, font=title_font)
        y += 108 if thumbnail else 80
    if not thumbnail:
        y = max(y + 50, 390)
        for size in range(45, 27, -1):
            body_font = ImageFont.truetype(fp, size)
            body_lines = wrap(text, body_font, 910)
            if y + len(body_lines) * (size + 22) < 920:
                break
        else:
            raise ValueError("이미지 문구가 너무 깁니다")
        for line in body_lines:
            draw.text((80, y), line, fill=ink, font=body_font)
            y += size + 22
    if y > 940:
        raise ValueError("이미지 제목이 영역을 초과합니다")
    draw.text((80, 998), footer[:65], fill="#9ba8aa" if thumbnail else "#596a6c",
              font=ImageFont.truetype(fp, 22))
    image.save(path)


def capture_source(spec, source, path):
    # Screenshots require a concrete usage basis supplied by the operator.
    if not spec.get("rights", "").strip() or not spec.get("selector"):
        raise ValueError("캡처에는 이용 근거와 정확한 CSS selector가 필요합니다")
    highlights = spec.get("highlights", [])
    if not isinstance(highlights, list) or any(not isinstance(t, str) or not t.strip() for t in highlights):
        raise ValueError("highlights는 원문의 핵심 문장 문자열 목록이어야 합니다")
    if spec.get("card") != 1 and not highlights:
        raise ValueError("본문 캡처에는 빨간 밑줄을 표시할 핵심 문장 highlights가 필요합니다")
    public_url(source["url"])
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1200, "height": 1000},
                                      java_script_enabled=False, service_workers="block")
        def guard(route):
            try:
                public_url(route.request.url)
                route.continue_()
            except (ValueError, OSError):
                route.abort()
        context.route("**/*", guard)
        page = context.new_page()
        response = page.goto(source["url"], wait_until="domcontentloaded", timeout=30000)
        if not response or response.status >= 400:
            raise ValueError("캡처 원문 접속 실패")
        target = page.locator(spec["selector"])
        if target.count() != 1:
            raise ValueError("캡처 대상이 하나로 특정되지 않습니다")
        target.scroll_into_view_if_needed()
        box = target.bounding_box()
        if not box or box["height"] > 1800 or box["width"] < 300:
            raise ValueError("캡처 크기를 읽기 쉽게 좁혀 주세요")
        rectangles = target.evaluate(HIGHLIGHT_RECTS, highlights) if highlights else []
        target.screenshot(path=str(path), animations="disabled")
        if rectangles:
            underline_capture(path, rectangles, box["width"], box["height"])
        browser.close()


# Locate exact visible source text, including text split across inline elements.
# Returning rectangles avoids changing the original page's text or layout.
HIGHLIGHT_RECTS = r"""(target, phrases) => {
    const chars = [], points = [];
    const walker = document.createTreeWalker(target, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
        const node = walker.currentNode, parent = node.parentElement;
        if (!parent || parent.closest('script,style,noscript') ||
            !parent.getClientRects().length || getComputedStyle(parent).visibility === 'hidden') continue;
        for (let i = 0; i < node.textContent.length; i++) {
            const ch = /\s/.test(node.textContent[i]) ? ' ' : node.textContent[i];
            if (ch === ' ' && chars.at(-1) === ' ') continue;
            chars.push(ch); points.push([node, i]);
        }
    }
    const text = chars.join(''), origin = target.getBoundingClientRect(), rects = [];
    for (const phrase of phrases) {
        const needle = phrase.trim().replace(/\s+/g, ' '), start = text.indexOf(needle);
        if (start < 0 || text.indexOf(needle, start + 1) >= 0)
            throw new Error('핵심 문장이 없거나 여러 번 나타납니다: ' + needle);
        const first = points[start], last = points[start + needle.length - 1];
        const range = document.createRange();
        range.setStart(first[0], first[1]); range.setEnd(last[0], last[1] + 1);
        const visible = [...range.getClientRects()].filter(r => r.width > 0 && r.height > 0);
        if (!visible.length) throw new Error('핵심 문장이 보이지 않습니다: ' + needle);
        for (const r of visible) {
            if (r.left < origin.left - 1 || r.right > origin.right + 1 ||
                r.top < origin.top - 1 || r.bottom > origin.bottom + 1)
                throw new Error('핵심 문장이 캡처 영역을 벗어납니다');
            rects.push([r.left - origin.left, r.bottom - origin.top,
                        r.right - origin.left]);
        }
    }
    return rects;
}"""


def underline_capture(path, rectangles, width, height):
    with Image.open(path) as original:
        image = original.convert("RGB")
    sx, sy = image.width / width, image.height / height
    draw = ImageDraw.Draw(image)
    thickness = max(2, round(3 * sy))
    for left, bottom, right in rectangles:
        y = min(image.height - thickness, round(bottom * sy) + 1)
        draw.line((max(0, round(left * sx)), y, min(image.width - 1, round(right * sx)), y),
                  fill="#e32636", width=thickness)
    image.save(path)


def render(post, sources, directory, captures=()):
    directory = Path(directory)
    known = {s["id"]: s for s in sources}
    indices = [s.get("card") for s in captures]
    if len(set(indices)) != len(indices) or any(i not in range(1, len(post["cards"]) + 2) for i in indices):
        raise ValueError("캡처 이미지 번호가 중복되거나 범위를 벗어납니다")
    thumb = next((s for s in captures if s.get("card") == 1), None)
    background = directory / "background.tmp.png"
    if thumb:
        if thumb.get("source_id") not in known:
            raise ValueError("썸네일 캡처 출처 오류")
        capture_source(thumb, known[thumb["source_id"]], background)
    try:
        draw_image(directory / "01_thumbnail.png", post["thumbnail"], "", "노체 · 경제 이슈", True,
                   background if thumb else None)
    finally:
        background.unlink(missing_ok=True)
    files = ["01_thumbnail.png"]
    for i, card in enumerate(post["cards"], 2):
        filename = f"{i:02d}_body.png"
        spec = next((s for s in captures if s.get("card") == i), None)
        if spec:
            sid = spec.get("source_id")
            if sid not in card["source_ids"]:
                raise ValueError("캡처와 카드 출처가 다릅니다")
            capture_source(spec, known[sid], directory / filename)
        else:
            footer = " · ".join(sid + " " + urlsplit(known[sid]["url"]).netloc for sid in card["source_ids"])
            draw_image(directory / filename, card["title"], card["text"], footer)
        files.append(filename)
    return files

