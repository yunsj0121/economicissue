"""Ordered final image handoff plus a portable gallery with downloads."""
import html
import json
from pathlib import Path


def write_delivery(directory, title, files):
    directory = Path(directory)
    # The consumer must attach these files as one native image gallery in chat.
    # An HTML file or manifest alone cannot control the ChatGPT client renderer.
    delivery = {"version": 1, "presentation": "native_multi_image_gallery",
                "final_only": True, "order": files,
                "images": [{"path": name, "role": "thumbnail" if i == 0 else "body",
                            "alt_text": None} for i, name in enumerate(files)],
                "alt_text_author": "user", "post": "post.txt", "copyable_post": "copyable_post.md",
                "fallback_gallery": "gallery.html",
                "instructions": ["Attach every image in order as one native image gallery",
                                 "Show final images inline with per-image download support",
                                 "Do not substitute a ZIP, file links, or Library links for the gallery",
                                 "Alt text is supplied separately by the user",
                                 "Confirm the receiving client displayed the gallery; file generation alone is not confirmation"]}
    (directory / "delivery.json").write_text(json.dumps(delivery, ensure_ascii=False, indent=2), encoding="utf-8")
    # Local gallery is self-contained so it also works after moving the HTML file.
    import base64
    cards = []
    for i, name in enumerate(files):
        data = base64.b64encode((directory / name).read_bytes()).decode("ascii")
        cards.append({"src": "data:image/png;base64," + data, "name": name,
                      "label": "썸네일" if i == 0 else f"이미지 {i + 1}"})
    payload = json.dumps(cards, ensure_ascii=True).replace("<", "\\u003c")
    page = '''<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title><style>
body{margin:0;background:#111;color:white;font:16px system-ui;max-width:760px;margin:auto;padding:16px}
img{display:block;width:100%;max-height:75vh;object-fit:contain;border-radius:14px}
nav{display:flex;gap:10px;overflow-x:auto;margin:14px 0}button{background:none;border:2px solid transparent;border-radius:10px;padding:3px;flex:0 0 82px;cursor:pointer}
button[aria-pressed=true]{border-color:#fff}button img{width:76px;height:76px;object-fit:cover;border-radius:6px}
a{color:white;display:inline-block;padding:10px;border:1px solid #777;border-radius:8px}h1{font-size:22px}
</style><h1>__TITLE__</h1><img id="main" alt=""><nav aria-label="최종 이미지 선택"></nav>
<p id="position" aria-live="polite"></p><a id="download">현재 이미지 다운로드</a>
<script>const images=__IMAGES__, main=document.querySelector('#main'), nav=document.querySelector('nav');
function select(i){main.src=images[i].src;document.querySelector('#position').textContent=(i+1)+' / '+images.length;
const a=document.querySelector('#download');a.href=images[i].src;a.download=images[i].name;
[...nav.children].forEach((b,n)=>b.setAttribute('aria-pressed',String(n===i)));}
images.forEach((image,i)=>{const b=document.createElement('button');b.type='button';b.setAttribute('aria-label',image.label);
const img=document.createElement('img');img.src=image.src;img.alt='';b.append(img);b.onclick=()=>select(i);nav.append(b)});select(0);
</script></html>'''
    (directory / "gallery.html").write_text(page.replace("__TITLE__", html.escape(title)).replace("__IMAGES__", payload), encoding="utf-8")


def write_preview(directory, post, sources, files):
    """Portable mobile preview in publication order, with sources before hashtags."""
    import base64
    import json
    directory = Path(directory)
    used = {sid for c in post['paragraphs'] + post['cards'] for sid in c['source_ids']}
    article_lines = [post["title"], "", "[이미지 01_thumbnail.png]", ""]
    for number, paragraph in enumerate(post["paragraphs"], 1):
        article_lines.extend([paragraph["text"].strip(), ""])
        for index, card in enumerate(post["cards"], 2):
            if card["after"] == number:
                article_lines.extend([f"[이미지 {index:02d}_body.png]", ""])
    if post.get("hashtags"):
        article_lines.extend(["", " ".join(post["hashtags"])])
    article_text = "\n".join(article_lines).strip()
    (directory / "copyable_post.md").write_text(
        "```text\n" + article_text + "\n```\n", encoding="utf-8")
    failures_path = directory / "capture_failures.json"
    failures = json.loads(failures_path.read_text(encoding="utf-8")) if failures_path.exists() else []
    failed_ids = {item["source_id"] for item in failures}
    with (directory / "copyable_post.md").open("a", encoding="utf-8") as copyable:
        copyable.write("\n자료 출처 바로가기\n\n")
        for source in sources:
            if source["id"] in used:
                label = "원문 캡처 실패 — 자료 바로가기" if source["id"] in failed_ids else "원문 바로가기"
                copyable.write(f"- [{label}: {source['title']}]({source['url']})\n")
    def image(name):
        data = base64.b64encode((directory / name).read_bytes()).decode("ascii")
        return '<img alt="" src="data:image/png;base64,' + data + '">'
    parts = ["<!doctype html><html lang=ko><meta charset=utf-8>",
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             '<style>body{max-width:680px;margin:32px auto;padding:0 20px;font:18px/1.9 system-ui;color:#222}img{width:100%;height:auto;margin:24px 0}p{white-space:pre-wrap;margin:28px 0}aside{font-size:14px;overflow-wrap:anywhere}h1{font-size:26px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f3f4;padding:18px;border-radius:10px;font:15px/1.8 ui-monospace,monospace}a{color:#075e70}button{padding:9px 14px;border:0;border-radius:7px;background:#17333c;color:white;font-size:15px}</style>',
             '<title>' + html.escape(post['title']) + '</title>',
             '<h1>' + html.escape(post['title']) + '</h1>', image(files[0]),
             '<section aria-label="복사용 원고"><h2>복사용 원고</h2><button type="button" id="copy">원고 복사</button><pre><code id="article">' + html.escape(article_text) + '</code></pre></section>',
             '<script>document.querySelector("#copy").onclick=async()=>{await navigator.clipboard.writeText(document.querySelector("#article").textContent);document.querySelector("#copy").textContent="복사했어요"}</script>']
    for number, paragraph in enumerate(post['paragraphs'], 1):
        parts.append('<p>' + html.escape(paragraph['text']) + '</p>')
        for index, card in enumerate(post['cards'], 1):
            if card['after'] == number:
                parts.append(image(files[index]))
    used = {sid for c in post['paragraphs'] + post['cards'] for sid in c['source_ids']}
    parts.append('<aside><h2>자료 출처 바로가기</h2>')
    for source in sources:
        if source['id'] in used:
            label = '원문 캡처 실패 — 자료 바로가기' if source['id'] in failed_ids else '원문 바로가기'
            parts.append('<p><a href="' + html.escape(source['url'], quote=True) + '" target="_blank" rel="noopener noreferrer">' +
                         html.escape(label + ': ' + source['title']) + '</a></p>')
    parts.extend(['</aside>', '<p>' + html.escape(' '.join(post.get('hashtags', []))) + '</p></html>'])
    (directory / 'preview.html').write_text(''.join(parts), encoding='utf-8')
