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
                "alt_text_author": "user", "post": "post.txt",
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
