"""Mobile copy formatting shared by manual and generated drafts."""
import copy
import re
import textwrap


def mobile_text(text, width=32):
    # Protect URLs and decimal points while separating sentence boundaries.
    urls = []
    def protect(match):
        raw = match.group()
        url = raw.rstrip(".．。!?")
        urls.append(url)
        return f"\ue000{len(urls) - 1}\ue001" + raw[len(url):]
    text = re.sub(r'''https?://[^\s<>"“”'‘’]+''', protect, text.strip())
    text = re.sub(r'\.([\"\u201d\u2019\u300d\u300f)]*)(?=\s|$|[가-힣])', r'\1\n', text)
    text = re.sub(r'([!?][\"\u201d\u2019]*)(?=\s|[가-힣])\s*', r'\1\n', text)
    text = re.sub(r'[．。](?=\s|$|[가-힣])', '\n', text)
    lines = []
    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        for i, url in enumerate(urls):
            line = line.replace(f"\ue000{i}\ue001", url)
        lines.extend(textwrap.wrap(line, width=width, break_long_words=True,
                                   break_on_hyphens=False) if width and "://" not in line else [line])
    return "\n".join(lines).strip()


def format_post(post):
    post = copy.deepcopy(post)
    post["title"] = post["title"].strip().rstrip(".．。")
    post["thumbnail"] = mobile_text(post["thumbnail"], width=0)
    for paragraph in post["paragraphs"]:
        paragraph["text"] = mobile_text(paragraph["text"])
    for card in post["cards"]:
        card["title"] = card["title"].strip().rstrip(".．。")
        card["text"] = mobile_text(card["text"], width=0)
    return post
