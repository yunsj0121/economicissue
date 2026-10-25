"""Cheap editorial signals for ranking; scores are not predicted traffic."""
import re

TITLE_STYLES = ("비교형", "결과형", "갈등형", "선택형", "반전형", "계산형")
DEFAULT_TOPICS = {
    "생활비·저축": ["생활비", "저축", "가계부", "외벌이", "맞벌이", "1인가구", "1인 가구"],
    "가족과 돈": ["축의금", "결혼", "배우자", "부부", "부모", "자녀", "비상금"],
    "투자 선택과 결과": ["주식", "투자", "ETF", "배당", "손실", "수익", "대출 상환"],
    "노후 현금흐름": ["노후", "은퇴", "연금", "퇴직금", "생활비 지원"],
    "직업과 보수": ["월급", "연봉", "성과급", "보수", "채용", "야간", "초과근무"],
    "자산과 주거비": ["순자산", "중산층", "월세", "주거비", "주택연금", "부채"],
}
SIGNALS = {
    "생활 상황": ("외벌이", "맞벌이", "직장인", "부부", "부모", "자녀", "은퇴", "가족", "1인가구", "1인 가구"),
    "선택·갈등": ("고민", "갈등", "후회", "부담", "부족", "공개", "지원", "상환", "손절", "포기"),
    "결과·비교": ("평균", "중앙값", "차이", "비교", "손실", "수익", "늘었", "줄었", "달라", "계산"),
}
MONEY = re.compile(r"\d[\d,.]*\s*(?:억|만|천)?\s*원|\d[\d,.]*\s*%")


def assess(title, text="", policy=None):
    policy = policy or {}
    topics = policy.get("topic_families", DEFAULT_TOPICS)
    # Cap body inspection so a long report does not gain unbounded matches.
    material = title + "\n" + text[:12000]
    families = [name for name, words in topics.items() if any(w in material for w in words)]
    signals = [name for name, words in SIGNALS.items() if any(w in material for w in words)]
    if MONEY.search(material):
        signals.append("구체금액·비율")
    weights = policy.get("editorial_weights", {})
    defaults = {"생활 상황": 2, "선택·갈등": 3, "결과·비교": 2, "구체금액·비율": 2}
    score = min(len(families), 2) + sum(weights.get(s, defaults[s]) for s in signals)
    return {"score": score, "families": families, "signals": signals,
            "note": "키워드 기반 편집 적합도 추정이며 사실 검증·조회수 예측이 아님"}
