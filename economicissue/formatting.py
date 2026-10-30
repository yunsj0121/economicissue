"""Mobile copy formatting shared by manual and generated drafts."""
import copy
import re


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
        card["text"] = mobile_text(card["text"])
    if "hashtags" in post:
        post["hashtags"] = [t.strip() for t in post["hashtags"]]
    return post
