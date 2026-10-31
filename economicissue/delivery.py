"""Ordered final image handoff plus a portable gallery with downloads."""
import html
import hashlib
import json
from pathlib import Path


def write_delivery(directory, title, files, post=None):
    directory = Path(directory)
    review_path = directory / "image_review.json"
    reviews = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else []
    reviewed = {item["image"]: item for item in reviews}
    images, jobs = [], []
    for i, name in enumerate(files):
        path = directory / name
        details = reviewed.get(name, {})
        capture = details.get("type") == "capture"
        item = {"path": name, "role": "thumbnail" if i == 0 else "body", "alt_text": None,
                "asset_type": "source_capture" if capture else "generation_input",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        if capture:
            item.update({k: details[k] for k in ("source_id", "url", "selector", "raw_path", "raw_sha256")
                         if k in details})
            item["delivery_method"] = "original_png_native_attachment"
            item["image_generation_allowed"] = False
        else:
            item["delivery_method"] = "original_image_gen_result"
            copy = {"title": title}
            if post:
                card = post["cards"][i - 1] if i else None
                copy = ({"thumbnail": post["thumbnail"]} if i == 0 else
                        {key: card[key] for key in ("title", "text", "columns", "rows") if key in card})
            prompt = ("작업자가 만든 첨부 레이아웃을 참고해 게시용 이미지 한 장을 생성하세요. "
                      "아래 확정 문구·숫자·단위·조건을 정확히 유지하세요. 썸네일은 1:1이며 글자를 크게 배치하세요. "
                      "자료에 없는 숫자나 원문 화면을 만들지 마세요. 원문 캡처를 흉내 내지 마세요.\n"
                      + json.dumps(copy, ensure_ascii=False))
            jobs.append({"image_index": i + 1, "role": item["role"], "input_path": name, "input_sha256": item["sha256"],
                         "tool": "image_gen.imagegen", "prompt": prompt,
                         "transparent_background": False})
        images.append(item)
    generated = [i + 1 for i, item in enumerate(images) if item["asset_type"] == "generation_input"]
    captures = [i + 1 for i, item in enumerate(images) if item["asset_type"] == "source_capture"]
    groups = []
    if generated:
        groups.append({"id": "generated", "image_indices": generated,
                       "delivery_protocol": "image_gen_results_same_response"})
    if captures:
        groups.append({"id": "source_captures", "image_indices": captures,
                       "delivery_protocol": "original_png_native_multi_image_attachment"})
    # This is a request for agent-side tool execution, never a native attachment receipt.
    delivery = {"version": 2, "presentation": "native_multi_image_gallery",
                "delivery_protocol": "image_gen_results_and_original_capture_attachments",
                "delivery_status": "pending_generation_and_native_attachment" if jobs else "pending_native_attachment",
                "required_generated_image_results": len(jobs),
                "required_original_capture_attachments": len(captures),
                "gallery_groups": groups,
                "generation_jobs": "image-generation.json",
                "attach_generated_results_directly": True,
                "run_image_generation_in_one_response": True,
                "tool_preview_is_delivery": False, "manifest_is_delivery_receipt": False,
                "forbid_markdown_image_links": True, "forbid_automatic_zip_fallback": True,
                "final_only": True, "order": files,
                "images": images,
                "alt_text_author": "user", "post": "post.txt", "copyable_post": "copyable_post.md",
                "instructions": ["Run every generation job with the actual image_gen tool; PNG layouts are inputs only",
                                 "Resolve input_path against the final bundle directory; inspect the reference before editing",
                                 "Preserve the original returned tool objects in the current session",
                                 "Check final Korean copy, numbers, units and thumbnail aspect ratio",
                                 "Return actual results in order with generatedImage(result) in the same response",
                                 "Retry only failed jobs and reuse successful original result objects",
                                 "Attach source captures as unchanged PNGs in a separate native image group; never regenerate them",
                                 "Do not wrap view_image data URLs or file paths as generated image results",
                                 "Do not substitute Markdown, ZIP, HTML or preview output for native attachment",
                                 "Alt text is supplied separately by the user",
                                 "Keep pending status unless actual native attachments and bulk save have been verified"]}
    (directory / "delivery.json").write_text(json.dumps(delivery, ensure_ascii=False, indent=2), encoding="utf-8")
    (directory / "image-generation.json").write_text(json.dumps({"jobs": jobs}, ensure_ascii=False, indent=2), encoding="utf-8")


def write_image_gallery(directory, title, files, archive_name="images.zip", gallery_name="gallery.html"):
    """Self-contained browsing and one-click ZIP download, including nested groups."""
    import base64
    import zipfile
    directory = Path(directory)
    archive_path = directory / archive_name
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in files:
            archive.write(directory / name, arcname=name)
    archive_data = base64.b64encode(archive_path.read_bytes()).decode("ascii")
    # Local gallery is self-contained so it also works after moving the HTML file.
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
<a id="download-all" href="data:application/zip;base64,__ZIP__" download="__ARCHIVE__">전체 이미지 ZIP 다운로드</a>
<script>const images=__IMAGES__, main=document.querySelector('#main'), nav=document.querySelector('nav');
function select(i){main.src=images[i].src;document.querySelector('#position').textContent=(i+1)+' / '+images.length;
const a=document.querySelector('#download');a.href=images[i].src;a.download=images[i].name;
[...nav.children].forEach((b,n)=>b.setAttribute('aria-pressed',String(n===i)));}
images.forEach((image,i)=>{const b=document.createElement('button');b.type='button';b.setAttribute('aria-label',image.label);
const img=document.createElement('img');img.src=image.src;img.alt='';b.append(img);b.onclick=()=>select(i);nav.append(b)});select(0);
</script></html>'''
    (directory / gallery_name).write_text(
        page.replace("__TITLE__", html.escape(title)).replace("__IMAGES__", payload)
        .replace("__ZIP__", archive_data).replace("__ARCHIVE__", html.escape(archive_name, quote=True)),
        encoding="utf-8")


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
