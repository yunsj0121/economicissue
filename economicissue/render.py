"""Deterministic Korean images; optional permitted source captures."""
import os
from pathlib import Path
from urllib.parse import urlsplit
from PIL import Image, ImageDraw, ImageFont, ImageOps
from .sources import public_url


def font_path():
    paths = [os.getenv("KOREAN_FONT", ""), "C:/Windows/Fonts/malgunbd.ttf",
             "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
             "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]
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


def draw_image(path, title, text, footer, thumbnail=False, background=None, compact=False):
    image = Image.new("RGB", (1080, 1080), "#142d35" if thumbnail else "#f5f3ed")
    if background:
        with Image.open(background) as original:
            # Preserve the complete evidence region: no cropping or dark filter over numbers.
            evidence = ImageOps.contain(original.convert("RGB"), (920, 470))
            image.paste(evidence, ((1080 - evidence.width) // 2, 490 + (470 - evidence.height) // 2))
    draw = ImageDraw.Draw(image)
    ink = "#ffffff" if thumbnail else "#17333c"
    draw.rectangle((70, 85, 190, 99), fill="#e9ba53")
    fp = font_path()
    title_font = ImageFont.truetype(fp, 55)
    if thumbnail:
        for size in range(80, 47, -1):
            title_font = ImageFont.truetype(fp, size)
            if len(wrap(title, title_font, 920)) <= 3:
                break
        else:
            raise ValueError("썸네일 문구를 세 줄 이내로 줄여 주세요")
    lines = wrap(title, title_font, 920)
    y = 180 if thumbnail else (70 if compact else 170)
    for line in lines:
        draw.text((80, y), line, fill=ink, font=title_font)
        y += 90 if thumbnail else 80
    if not thumbnail:
        y = max(y + 50, 220 if compact else 390)
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
    if compact and not thumbnail:
        image = image.crop((0, 0, 1080, min(1080, max(450, y + 110))))
        draw = ImageDraw.Draw(image)
    draw.text((80, image.height - 82), footer[:65], fill="#9ba8aa" if thumbnail else "#596a6c",
              font=ImageFont.truetype(fp, 22))
    image.save(path)



def capture_frame(path, caption, url):
    with Image.open(path) as original:
        image = original.convert("RGB")
    # A wide, short evidence excerpt stays readable; long pages must be narrowed upstream.
    ratio = 1000 / image.width
    if image.height * ratio > 1600:
        raise ValueError("캡처가 너무 깁니다. 핵심 문단이나 표로 좁혀 주세요")
    image = image.resize((1000, max(1, round(image.height * ratio))))
    fp = font_path()
    caption_font = ImageFont.truetype(fp, 32)
    lines = wrap(caption, caption_font, 980)
    footer_font = ImageFont.truetype(fp, 22)
    footers = wrap(url, footer_font, 980)
    height = image.height + 100 + 48 * len(lines) + 30 * len(footers)
    canvas = Image.new("RGB", (1080, height), "#ffffff")
    canvas.paste(image, (40, 30))
    draw = ImageDraw.Draw(canvas)
    y = image.height + 55
    for line in lines:
        draw.text((40, y), line, font=caption_font, fill="#17333c"); y += 48
    for line in footers:
        draw.text((40, y), line, font=footer_font, fill="#596a6c"); y += 30
    canvas.save(path)


def draw_data(path, card, footer):
    image = Image.new("RGB", (1080, 1800), "#f5f3ed")
    draw, fp = ImageDraw.Draw(image), font_path()
    for i, line in enumerate(wrap(card["title"], ImageFont.truetype(fp, 44), 960)):
        draw.text((60, 60 + i * 55), line, font=ImageFont.truetype(fp, 44), fill="#17333c")
    rows, columns = card["rows"], card["columns"]
    if card["visual"] == "chart":
        values = [float(r[1].replace(",", "")) for r in rows]
        largest = max(values) or 1
        draw.text((60, 145), " / ".join(columns), font=ImageFont.truetype(fp, 26), fill="#596a6c")
        for i, (label, value) in enumerate(rows):
            y = 230 + i * 95
            label_font = ImageFont.truetype(fp, 26)
            labels = wrap(label, label_font, 295)
            if len(labels) > 2:
                raise ValueError("그래프 항목 이름을 줄여 주세요")
            for k, line in enumerate(labels):
                draw.text((60, y + k * 32), line, font=label_font, fill="#17333c")
            width = round(float(value.replace(",", "")) / largest * 400)
            draw.rectangle((380, y, 380 + width, y + 45), fill="#397c78")
            for size in range(26, 13, -1):
                value_font = ImageFont.truetype(fp, size)
                if value_font.getlength(value) <= 220:
                    break
            else:
                raise ValueError("그래프 숫자의 단위를 줄여 주세요")
            draw.text((1020, y), value, anchor="ra", font=value_font, fill="#17333c")
    else:
        cell_width = 960 // len(columns)
        font = ImageFont.truetype(fp, 36)
        y = 210
        for i, row in enumerate([columns] + rows):
            wrapped = [wrap(c, font, cell_width - 28) for c in row]
            height = max(86, max(map(len, wrapped)) * 48 + 28)
            if y + height > 1400:
                raise ValueError("표가 너무 큽니다. 행이나 셀 문구를 줄여 주세요")
            draw.rectangle((60, y, 1020, y + height), fill="#17333c" if i == 0 else ("#ffffff" if i % 2 else "#e3ece8"))
            for j, lines in enumerate(wrapped):
                for k, line in enumerate(lines):
                    draw.text((74 + j * cell_width, y + 14 + k * 48), line, font=font,
                              fill="white" if i == 0 else "#17333c")
            y += height
    data_box = (40, 190 if card["visual"] == "table" else 140, 1040, y + 70)
    y += 130 if card["visual"] == "chart" else 45
    caption_lines = wrap(card["text"], ImageFont.truetype(fp, 32), 960)
    if len(caption_lines) > 5:
        raise ValueError("표·그래프 해설을 5줄 이내로 줄여 주세요")
    for line in caption_lines:
        draw.text((60, y), line, font=ImageFont.truetype(fp, 32), fill="#17333c")
        y += 44
    draw.text((60, y + 35), footer[:65], font=ImageFont.truetype(fp, 22), fill="#596a6c")
    image.crop((0, 0, 1080, min(1800, y + 110))).save(path)
    return data_box

def capture_source(spec, source, path):
    # Screenshots require a concrete usage basis supplied by the operator.
    if not spec.get("rights", "").strip() or not spec.get("selector"):
        raise ValueError("캡처에는 이용 근거와 정확한 CSS selector가 필요합니다")
    highlights = spec.get("highlights", [])
    if not isinstance(highlights, list) or any(not isinstance(t, str) or not t.strip() for t in highlights):
        raise ValueError("highlights는 원문의 핵심 문장 문자열 목록이어야 합니다")
    if spec.get("card") != 1 and spec.get("kind") != "image" and not highlights:
        raise ValueError("본문 캡처에는 빨간 밑줄을 표시할 핵심 문장 highlights가 필요합니다")
    public_url(source["url"])
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        from .browser import launch, guarded_context
        from .sources import Collector
        browser = launch(p.chromium)
        collector = Collector({"cache_hours": 1}, path.parent / ".capture-cache")
        if not collector.allowed(source["url"]):
            browser.close()
            raise ValueError("원문 캡처 수집 허용 상태 확인 실패")
        context = guarded_context(browser, collector.allowed)
        page = context.new_page()
        response = page.goto(source["url"], wait_until="domcontentloaded", timeout=30000)
        if not response or response.status >= 400:
            raise ValueError("캡처 원문 접속 실패")
        from .browser import settle, assert_content, content_hash
        settle(page)
        assert_content(page.locator("body").inner_text())
        target = page.locator(spec["selector"])
        if target.count() != 1:
            raise ValueError("캡처 대상이 하나로 특정되지 않습니다")
        target.scroll_into_view_if_needed()
        if spec.get("text_hash") and content_hash(target.inner_text()) != spec["text_hash"]:
            browser.close()
            raise ValueError("원문이 변경되어 캡처를 중단했습니다")
        if spec.get("image_url") and target.evaluate("e => e.currentSrc || e.src") != spec["image_url"]:
            browser.close()
            raise ValueError("원문 이미지가 변경되었습니다")
        for image in target.locator("img").all():
            image.evaluate("e => e.loading = 'eager'")
        page.wait_for_function("e => [...e.querySelectorAll('img')].every(i => i.complete)", arg=target.element_handle(), timeout=10000)
        masks = [page.locator(selector) for selector in spec.get("mask_selectors", [])]
        if any(mask.count() != 1 for mask in masks):
            browser.close()
            raise ValueError("개인정보 가림 영역을 확인하지 못했습니다")
        box = target.bounding_box()
        if not box or box["height"] > 1800 or box["width"] < 300:
            raise ValueError("캡처 크기를 읽기 쉽게 좁혀 주세요")
        rectangles = target.evaluate(HIGHLIGHT_RECTS, highlights) if highlights else []
        target.screenshot(path=str(path), animations="disabled", mask=masks)
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


def render(post, sources, directory, captures=(), policy=None):
    directory = Path(directory)
    known = {s["id"]: s for s in sources}
    policy = policy or {}
    captures = list(captures)
    status = []
    for index, card in enumerate(post["cards"], 2):
        if card.get("visual") != "evidence" or any(c.get("card") == index for c in captures):
            continue
        found = [(source, c) for source in sources if source["id"] in card["source_ids"]
                 for c in source.get("capture_candidates", []) if c["id"] == card.get("capture_id")]
        if len(found) != 1:
            raise ValueError("캡처 계획과 확인된 원문 영역이 다릅니다")
        source, c = found[0]
        if c["kind"] == "image":
            raise ValueError("원문 사진·그림은 이용 근거와 가림 영역을 확인한 --captures 명세로 지정하세요")
        if not policy.get("capture_rights"):
            raise ValueError("원문 일부 캡처의 이용 근거 capture_rights를 설정하세요")
        captures.append({**c, "card": index, "source_id": source["id"],
                         "rights": policy["capture_rights"],
                         "highlights": [c["text"]] if c["kind"] == "text" else []})
    indices = [s.get("card") for s in captures]
    if len(set(indices)) != len(indices) or any(i not in range(1, len(post["cards"]) + 2) for i in indices):
        raise ValueError("캡처 이미지 번호가 중복되거나 범위를 벗어납니다")
    thumb = next((s for s in captures if s.get("card") == 1), None)
    background = directory / "background.tmp.png"
    capture_failures = []
    if thumb:
        if thumb.get("source_id") not in known:
            raise ValueError("썸네일 캡처 출처 오류")
        try:
            capture_source(thumb, known[thumb["source_id"]], background)
        except Exception as error:
            capture_failures.append({"image": "01_thumbnail.png", "source_id": thumb["source_id"],
                                     "url": known[thumb["source_id"]]["url"], "reason": str(error)})
            thumb = None
        else:
            status.append({"image": "01_thumbnail.png", "type": "capture", "source_id": thumb["source_id"]})
    try:
        draw_image(directory / "01_thumbnail.png", post["thumbnail"], "", "노체 · 경제 이슈", True,
                   background if thumb else None)
    finally:
        background.unlink(missing_ok=True)
    files = ["01_thumbnail.png"]
    thumbnail_from = post.get("thumbnail_from_card", policy.get("thumbnail_from_card"))
    first_evidence = None
    panel = directory / "thumbnail_panel.tmp.png"
    for i, card in enumerate(post["cards"], 2):
        filename = f"{i:02d}_body.png"
        spec = next((s for s in captures if s.get("card") == i), None)
        if spec:
            sid = spec.get("source_id")
            if sid not in card["source_ids"]:
                raise ValueError("캡처와 카드 출처가 다릅니다")
            try:
                capture_source(spec, known[sid], directory / filename)
                capture_frame(directory / filename, card["text"], known[sid]["url"])
                if first_evidence is None:
                    with Image.open(directory / filename) as raw:
                        raw.save(panel)
            except Exception as error:
                capture_failures.append({"image": filename, "source_id": sid,
                                         "url": known[sid]["url"], "reason": str(error)})
                draw_image(directory / filename, "원문 캡처 불가", card["text"],
                           f"자료 바로가기: {urlsplit(known[sid]['url']).netloc}",
                           compact=bool(card.get("visual")))
                status.append({"image": filename, "type": "capture_failed", "source_id": sid,
                               "url": known[sid]["url"], "reason": str(error)})
            else:
                status.append({"image": filename, "type": "capture", "source_id": sid,
                               "url": known[sid]["url"], "selector": spec["selector"]})
        else:
            footer = " · ".join(sid + " " + urlsplit(known[sid]["url"]).netloc for sid in card["source_ids"])
            if card.get("visual") in {"table", "chart"}:
                box = draw_data(directory / filename, card, footer)
                if first_evidence is None:
                    with Image.open(directory / filename) as figure:
                        figure.crop(box).save(panel)
            else:
                draw_image(directory / filename, card["title"], card["text"], footer,
                       compact=bool(card.get("visual")))
            status.append({"image": filename, "type": card.get("visual", "explanation"),
                           "source_ids": card["source_ids"]})
        if first_evidence is None and (spec or card.get("visual") in {"table", "chart"}):
            if not any(failure["image"] == filename for failure in capture_failures):
                first_evidence = filename
        files.append(filename)
    if not thumb and thumbnail_from and first_evidence:
        draw_image(directory / "01_thumbnail.png", post["thumbnail"], "", "자료 발췌 · 해설", True,
                   panel if panel.exists() else directory / first_evidence)
        status.insert(0, {"image": "01_thumbnail.png", "type": "evidence_layout", "from": first_evidence})
    elif not thumb:
        status.insert(0, {"image": "01_thumbnail.png", "type": "text_layout"})
    panel.unlink(missing_ok=True)
    import json, shutil
    shutil.rmtree(directory / ".capture-cache", ignore_errors=True)
    (directory / "image_review.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    (directory / "capture_failures.json").write_text(json.dumps(capture_failures, ensure_ascii=False, indent=2), encoding="utf-8")
    return files

