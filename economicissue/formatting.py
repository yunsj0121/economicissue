"""Mobile copy formatting shared by manual and generated drafts."""
import copy
import re


_VISUAL_META = (
    r"(?:원문|보고서|자료)(?:\s*(?:기준(?:으로)?|수치(?:를)?|내용(?:을)?))?\s*(?:재구성|정리)한\s*(?:표|그래프|이미지)(?:입니다|예요|이에요)?",
    r"실제\s*적용\s*금리(?:가|는)?\s*(?:아님|아닙니다|아니에요)",
    r"원문\s*캡처\s*(?:아님|아닙니다|아니에요)",
    r"(?:연구소의\s*)?공식\s*(?:조사\s*항목|권고)(?:이|가)?\s*(?:아님|아닙니다|아니에요)",
    r"본문의\s*가계\s*점검\s*기준",
    r"직접\s*계산(?:한)?(?:\s*가상\s*비교)?",
    r"자료\s*발췌\s*·\s*해설",
)


def visual_text(text):
    """Drop standalone production labels, preserving figures and calculation inputs."""
    lines = []
    for line in text.splitlines():
        if any(re.fullmatch(pattern + r"[.．。]*", line.strip()) for pattern in _VISUAL_META):
            continue
        parts = []
        for part in re.split(r"\s+[·|]\s+", line):
            part = part.strip()
            if part and not any(re.fullmatch(pattern + r"[.．。]*", part) for pattern in _VISUAL_META):
                parts.append(part)
        if parts:
            lines.append(" · ".join(parts))
    return "\n".join(lines)


def mobile_text(text):
    # Protect URLs and decimal points while separating sentence boundaries.
    urls = []
    def protect(match):
        raw = match.group()
        url = raw.rstrip(".．。!?")
        urls.append(url)
        return f"\ue000{len(urls) - 1}\ue001" + raw[len(url):]
    text = re.sub(r'''https?://[^\s<>"“”'‘’]+''', protect, text.strip())
    text = re.sub(r'\.([\"\u201d\u2019\u300d\u300f)]*)(?=\s|$|[가-힣])[ \t]*(?:\r?\n)?', r'\1\n', text)
    text = re.sub(r'([!?][\"\u201d\u2019]*)(?=\s|[가-힣])[ \t]*(?:\r?\n)?', r'\1\n', text)
    text = re.sub(r'[．。](?=\s|$|[가-힣])[ \t]*(?:\r?\n)?', '\n', text)
    lines = []
    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        for i, url in enumerate(urls):
            line = line.replace(f"\ue000{i}\ue001", url)
        # Device layout handles visual wrapping; never insert a break by length.
        # Keeping empty lines also preserves the author's paragraph spacing.
        lines.append(line)
    return "\n".join(lines).strip()


def format_post(post, policy=None):
    post = copy.deepcopy(post)
    post["title"] = post["title"].strip().rstrip(".．。")
    for choice in post.get("editorial", {}).get("title_candidates", []):
        choice["title"] = choice["title"].strip().rstrip(".．。")
    post["thumbnail"] = mobile_text(post["thumbnail"])
    for paragraph in post["paragraphs"]:
        text = mobile_text(paragraph["text"])
        if (policy or {}).get("blank_line_between_sentences"):
            text = "\n\n".join(line.strip() for line in text.splitlines() if line.strip())
        paragraph["text"] = text
    for card in post["cards"]:
        card["title"] = card["title"].strip().rstrip(".．。")
        card["text"] = visual_text(mobile_text(card["text"]))
    if "hashtags" in post:
        post["hashtags"] = [t.strip() for t in post["hashtags"]]
    return post
