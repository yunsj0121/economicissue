"""Deterministic publication checks; no paid repair calls or padding."""
import re


def publication_text(post):
    body = "\n\n".join(p["text"].strip() for p in post["paragraphs"])
    tags = " ".join(post.get("hashtags", []))
    return body + ("\n\n" + tags if tags else "")


def check_publication(post, policy):
    tags = post.get("hashtags", [])
    count = policy.get("hashtag_count")
    if count is not None and (len(tags) != count or len(set(tags)) != count or
                              any(not re.fullmatch(r"#[가-힣A-Za-z0-9_]+", t) for t in tags)):
        raise ValueError(f"서로 다른 관련 해시태그 {count}개가 필요합니다")
    body = "\n\n".join(p["text"] for p in post["paragraphs"])
    if count is not None and "#" in body:
        raise ValueError("해시태그는 본문 대신 hashtags에 작성하세요")
    length = policy.get("length", {})
    text = publication_text(post) if length.get("include_hashtags", True) else body
    if length.get("include_title", False):
        text = post["title"] + "\n\n" + text
    characters = len(text)
    if length and not length["min"] <= characters <= length["max"]:
        raise ValueError(f"공백 포함 {characters}자: {length['min']}~{length['max']}자로 수정하세요")
    if policy.get("blank_line_between_sentences"):
        for p in post["paragraphs"]:
            lines = p["text"].splitlines()
            if any(a.strip() and b.strip() for a, b in zip(lines, lines[1:])):
                raise ValueError("문장 사이 빈 줄 하나가 필요합니다")
            if any(line.rstrip().endswith(('.', '。', '．')) for line in lines):
                raise ValueError("문장 끝 마침표를 제거하세요")
    positions = [card["after"] for card in post["cards"]]
    if policy.get("spread_images") and (positions != sorted(positions) or len(set(positions)) != len(positions)):
        raise ValueError("본문 이미지는 서로 다른 관련 문단 뒤에 순서대로 배치하세요")
    visuals = [card.get("visual", "explanation") for card in post["cards"]]
    if sum(v in {"evidence", "table", "chart"} for v in visuals) < policy.get("minimum_data_images", 0):
        raise ValueError("원문 캡처·비교표·그래프로 근거를 보여주는 이미지가 부족합니다")
    if policy.get("mixed_visuals") and len(set(visuals)) < 2:
        raise ValueError("본문 이미지 종류를 두 가지 이상으로 구성하세요")
    return {"characters_with_spaces": characters, "hashtag_count": len(tags),
            "count_basis": "본문·해시태그와 그 사이 공백/줄바꿈, 제목·출처·이미지 안내 제외"}
