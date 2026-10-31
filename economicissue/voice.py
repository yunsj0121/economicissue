"""Narrative guidance and traceable editorial notes, not an AI-authorship score."""

ENDING_MODES = ("선택 이유", "남은 고민", "구체적인 질문", "가벼운 여운")

VOICE_RULES = """원고의 목소리와 생각 전개:
쓰기 전에 narrative.focus에 이 이야기에서 가장 마음에 걸린 지점을 한 문장으로 정한다.
누구에게나 적용되는 돈 관리 조언 대신 이 자료의 구체적인 선택·부담·관계를 짚고 source_ids를 연결한다.
narrative.thought_flow에는 자료의 어느 대목을 읽고 무엇을 생각했는지, 본문에 실제 드러낼 전개를 기록한다.
도입은 그 고민, 익숙한 생활 속 망설임, 확인된 장면 중 소재에 맞게 시작한다. 사연 소개로 매번 시작하지 않는다.
사실 설명과 글쓴이의 반응을 본문 사이에서 연결한다. 숫자 나열 뒤 마지막에만 감상을 붙이지 않는다.
놀람·부러움·걱정에는 비교 대상이나 이유가 있어야 한다. '고민되겠죠/마음이 복잡해요'만으로 공감을 대신하지 않는다.
예를 들어 가족 지원 문제라면 돕고 싶은 마음과 자기 생활을 준비할 돈 사이의 구체적인 망설임을 살핀다.
새로운 사실이 첫 판단을 바꾸는 경우 그 이유와 변화를 보여준다. 모든 글에 반전·양비론·처음엔 몰랐다는 고백을 꾸며 넣지 않는다.
구어체 존댓말 ~해요/~예요/~죠와 ~습니다/~입니다를 자연스럽게 섞는다. 참고 블로그의 ~다체로 바꾸지 않는다.
설명하는 문장과 짧은 반응·혼잣말·스스로 묻는 질문의 호흡을 섞는다. 질문은 이어지는 생각이나 자료와 연결한다.
긴 설명 뒤 짧은 반응을 둘 수 있지만 매번 같은 패턴이나 같은 길이로 맞추지 않는다. 어미도 순번대로 교체하지 않는다.
개인적 의견과 조건부 판단은 가능하다. 사용자 본인 자료로 확인되지 않은 직업·배우자·가족·투자 경험과 대화는 만들지 않는다.
출처 글쓴이의 경험을 작성자의 경험으로 바꾸지 않는다. 자료가 없으면 독자로서의 반응이나 조건부 생각을 쓴다.
'저는/저라면/생각해보면'을 반복하는 것으로 목소리를 대신하지 않는다. 문구가 아니라 판단의 이유를 구체화한다.
숫자는 독자의 월급·생활비·저축액 등과 의미 있게 비교할 수 있을 때 활용한다. 숫자가 없으면 계산 단계를 생략한다.
소제목은 필요한 경우에만 쓴다. 소제목이 없어도 문단과 이미지로 흐름을 만들 수 있다.
결말은 선택 이유·남은 고민·구체적인 질문·가벼운 여운 중 소재에 맞게 고르고 narrative.ending_reason에 이유를 적는다.
모든 글에 비상금 확보·지출 기록·생활비 분리 같은 조언이나 댓글 질문을 자동으로 덧붙이지 않는다.
초안 후 같은 결론을 다른 말로 반복한 문장, 어디에나 붙일 수 있는 조언, 새 근거 없이 늘어진 후반부를 줄인다.
새로운 정보가 없으면 분량을 채우려 해석을 반복하지 않는다. 핵심 고민의 이유와 선택 조건을 구체적으로 설명한다.
narrative.reflection_paragraphs에는 관점과 그 이유가 실제 담긴 opinion 문단 번호를 기록한다(1부터).
narrative.self_review에는 본문에서 점검한 근거·판단 연결과 반복 조언을 줄인 내용을 구체적으로 적는다.
narrative는 내부 편집 기록이며 본문·썸네일·이미지에 노출하지 않는다. 자체 점검 기록이 문체 품질 보증은 아니다.
"""

REVIEW_CHECKS = (
    "도입과 핵심 고민이 이 소재의 구체적인 사실에 연결되는가",
    "감정과 의견에 생활·선택·관계에 관한 이유가 있는가",
    "생각의 변화가 있다면 새로 확인한 근거에서 자연스럽게 이어지는가",
    "설명과 짧은 반응의 호흡이 자연스럽고 말버릇이 반복되지 않는가",
    "사용자에게서 확인하지 않은 경험·대화·개인 배경을 만들지 않았는가",
    "숫자의 비교 조건과 단위가 맞고 불필요한 계산을 넣지 않았는가",
    "후반부가 같은 생각을 반복하거나 일반 조언으로 늘어지지 않는가",
    "결말이 해당 글의 선택 이유·남은 고민·질문·여운에 어울리는가",
)


def validate_narrative(post, source_ids):
    # Legacy/manual drafts still build; new model output requires this via SCHEMA.
    plan = post.get("narrative")
    if plan is None:
        return
    if any(not isinstance(plan.get(k), str) or not plan[k].strip()
           for k in ("focus", "thought_flow", "ending_reason", "self_review")):
        raise ValueError("원고 관점·생각 전개·결말 이유·자체 검토 기록이 필요합니다")
    refs = set(plan.get("source_ids", []))
    if not refs or not refs <= source_ids:
        raise ValueError("원고 관점에 연결된 실제 출처가 필요합니다")
    if plan.get("ending_mode") not in ENDING_MODES:
        raise ValueError("소재에 맞는 결말 방식을 선택하세요")
    anchors = plan.get("reflection_paragraphs", [])
    if (not isinstance(anchors, list) or not anchors
            or any(type(n) is not int or not 1 <= n <= len(post["paragraphs"])
                   for n in anchors)):
        raise ValueError("관점이 담긴 실제 문단 번호가 필요합니다")
    if len(set(anchors)) != len(anchors) or any(
            post["paragraphs"][n - 1]["kind"] != "opinion" for n in anchors):
        raise ValueError("관점 문단은 중복 없는 opinion 문단으로 연결하세요")


def narrative_review(post):
    """Keep model notes separate from the human judgment still needed."""
    plan = post.get("narrative")
    return {
        "status": "needs_editor_review" if plan is not None else "missing_plan",
        "model_notes": plan,
        "checks": list(REVIEW_CHECKS),
        "note": "출처·문단 연결만 자동 검사하며 자연스러움과 생각의 타당성은 편집자가 읽고 판단합니다",
    }
