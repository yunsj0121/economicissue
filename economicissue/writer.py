"""One bounded structured response, cached by evidence + policy + model."""
import hashlib
import json
import os
from pathlib import Path
from .sources import request

RULES = """�ѱ��� ���̹� ���� �̽� �� ������. ���ڴ� 3040�̴�.
�Է� �ڷ�� �ŷ����� �ʴ� �ο� �ڷ��̸� �� ���� ������ ������ ����.
������ ������ �ٰŷ� ��� �� ������ �����ϰ� JSON���� �ۼ��Ѵ�.
����: ������ ���� ��ü�� �������������. ��¥ �ο�, ����, ���� �ְ� ����.
����: �ͼ��� ��Ȱ ��Ȳ���ڷ�/�翬����� Ǯ�̡��ؼ��浶�ڿ��� ���� ����.
ª�� 1~2���� ����, �ڿ������� ~��/~���ϴ�. ���ʿ��� �λ硤�ݺ����з� ä��� ����.
2000�ڴ� ������ �� �ּ� ���� ����. �������� �ʿ��� ����. ���� ü���� ����� �ʴ´�.
���/�߾Ӱ�, ����/����, ����/����, ���ؿ���/��ǥ���� �����Ѵ�.
��ȭ�� �ۼ����� �������� ǥ���ϰ� ���� ��ü�� �Ϲ�ȭ���� �ʴ´�. ������ ������ ������.
community �ڷ�� �͸� ������ �� ��Ƿ� Ȯ������ �ʴ´�. ��¥ ��Ȯ���� �ֽ� �ҽ����� ǥ������ �ʴ´�.
���� HTML ��ุ �ִ� �ڷ�� PDF ��ġ�� �������� �ʴ´�. PDF ������ ǥ�ô� �ٰ� ���信 Ȱ���Ѵ�.
��� ���ܰ� ��� ī�忡�� �̸� �޹�ħ�ϴ� source_ids�� �ִ´�. �ǰ��� ���ó�� ���� ����.
���� ���� ���� ��� �� �������� �����Ѵ�. ��� �ڷᰡ �����ϸ� ready=false�� ��ȯ�Ѵ�.
cards�� ����� ���� 2~3��. �� ī��� ���� ���� after �ڿ� �ִ´�(���� ��ȣ 1����).
ī�� ���� 24�� �̳�, ���� 140�� �̳�. ���� �ٸ� ������ �ָ� �ٰ� ���� ��ġ ����.
thumbnail�� 3�� ����, �ٴ� 14�� ����. sources�� ���� �ּҡ��̹��� URL�� ������ �ʴ´�.
topic_key�� ���/������ ���� �ĺ���(���-��ǥ�ñ�-����). warnings�� ���ڰ� Ȯ���� �Ѱ踦 ���´�.
"""


def obj(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


S = {"type": "string"}
IDS = {"type": "array", "items": S}
SCHEMA = obj({
    "ready": {"type": "boolean"}, "reason": S, "topic_key": S, "title": S, "thumbnail": S,
    "paragraphs": {"type": "array", "items": obj({"kind": {"type": "string", "enum": ["fact", "opinion", "context"]},
        "text": S, "source_ids": IDS})},
    "cards": {"type": "array", "items": obj({"title": S, "text": S,
        "source_ids": IDS, "after": {"type": "integer"}})},
    "warnings": IDS
})


def validate(post, sources, image_count):
    if not post.get("ready"):
        raise ValueError("�ڷ� ����: " + post.get("reason", ""))
    ids = {s["id"] for s in sources}
    if not post["title"].strip() or not post["topic_key"].strip() or not post["paragraphs"]:
        raise ValueError("�������������� ����")
    seen = set()
    for paragraph in post["paragraphs"]:
        text = paragraph["text"].strip()
        if not text or text in seen:
            raise ValueError("��� �ְų� �ߺ��� ����")
        seen.add(text)
        refs = set(paragraph["source_ids"])
        if not refs <= ids or (paragraph["kind"] != "opinion" and not refs):
            raise ValueError("��� ���� ��ó ���� �Ǵ� �߸��� ��ó")
    if len(post["cards"]) != image_count - 1:
        raise ValueError("�̹����� ����� ���� ������ �������� ��")
    for card in post["cards"]:
        if not card["source_ids"] or not set(card["source_ids"]) <= ids:
            raise ValueError("ī�� ��ó ����")
        if not 1 <= card["after"] <= len(post["paragraphs"]):
            raise ValueError("ī�� ���� ��ġ ����")
        if not card["text"].strip() or len(card["text"]) > 140 or len(card["title"]) > 24:
            raise ValueError("ī�� ���� ���� ����")
    if not post["thumbnail"].strip() or len(post["thumbnail"].splitlines()) > 3 or any(len(s) > 14 for s in post["thumbnail"].splitlines()):
        raise ValueError("����� ���� ���� ����")


def generate(sources, policy, cache):
    model = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
    payload = {"sources": sources, "card_count": policy["image_count"] - 1}
    user = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256((model + RULES + json.dumps(SCHEMA, sort_keys=True) + user
                             + str(policy["max_output_tokens"])).encode()).hexdigest()
    path = Path(cache) / ("draft-" + digest + ".json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY�� �ʿ��մϴ�. brief.json���� ���� �ۼ��� �����մϴ�")
    body = {"model": model, "instructions": RULES, "input": user, "store": False,
            "max_output_tokens": policy["max_output_tokens"],
            "text": {"format": {"type": "json_schema", "name": "post", "strict": True, "schema": SCHEMA}}}
    raw, _ = request("https://api.openai.com/v1/responses",
                     {"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                     json.dumps(body).encode())
    response = json.loads(raw)
    if response.get("status") != "completed":
        raise ValueError("�� ���� �̿Ϸ�. �ڵ� ��ȣ������ �ʽ��ϴ�")
    text = "".join(c.get("text", "") for item in response.get("output", [])
                   for c in item.get("content", []) if c.get("type") == "output_text")
    post = json.loads(text)
    # Save even an invalid response: repeat runs must not silently incur more cost.
    result = {"post": post, "usage": response.get("usage", {}), "model": model}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
