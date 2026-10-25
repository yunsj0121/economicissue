import argparse
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .sources import Collector, compact, discover, request
from .direct import date_iso, kosis_data
from .writer import SCHEMA, generate, validate, writing_rules
from .editorial import assess, SIGNALS
from .render import render
from .formatting import format_post
from .delivery import write_delivery

KST = timezone(timedelta(hours=9))


def read(path, default=None):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def fingerprint(text):
    return hashlib.sha256("".join(text.split()).encode()).hexdigest()


def recent_history(path, days):
    cutoff = (datetime.now(KST) - timedelta(days=days)).isoformat()
    return [r for r in read(path, []) if r["date"] >= cutoff]


def prepare(args, policy):
    collector = Collector(policy, ".cache")
    candidates, errors = discover(collector, args.url)
    history = recent_history("state/history.json", policy["duplicate_days"])
    used = {u for r in history for u in r["urls"]}
    hashes = {h for r in history for h in r["hashes"]}
    evidence, budget = [], policy["evidence_chars"]
    for series in policy.get("kosis_series", []):
        try:
            key = os.getenv("KOSIS_API_KEY")
            if not key:
                raise ValueError("KOSIS_API_KEY 필요")
            records = kosis_data(series, key, request)
            text = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
            excerpt = compact(text, policy["keywords"], min(budget, policy["source_chars"]))
            digest = fingerprint(text)
            if digest in hashes or len(evidence) >= policy["source_limit"] or budget < 300:
                continue
            evidence.append({"id": f"s{len(evidence)+1}", "provider": "kosis-api", "kind": "statistics",
                             "title": series["title"], "url": series["source_url"], "hash": digest,
                             "text": excerpt, "published": "", "retrieved": datetime.now(KST).isoformat()})
            budget -= len(excerpt)
        except (OSError, ValueError, KeyError) as e:
            errors.append("KOSIS API: " + type(e).__name__)
    pool = []
    for candidate in candidates[:policy.get("fetch_limit", 12)]:
        if candidate["url"] in used:
            continue
        try:
            source = collector.extract(candidate["url"])
            source["published"] = source["published"] or candidate.get("published", "")
            if source["published"]:
                normalized = date_iso(source["published"])
                published = datetime.fromisoformat(normalized) if normalized else None
                if published is None:
                    raise ValueError("원문 날짜 해석 불가")
                if published.tzinfo is None:
                    published = published.replace(tzinfo=KST)
                age = (datetime.now(KST) - published).days
                maximum = policy["max_age_days"] if candidate["kind"] in {"news", "community"} else policy.get("report_age_days", 120)
                if candidate["kind"] != "manual" and (age < 0 or age > maximum):
                    continue
            digest = fingerprint(source["text"])
            if source["url"] in used or digest in hashes:
                continue
            source["title"] = source["title"] or candidate["title"]
            source.update(kind=candidate["kind"], provider=candidate.get("provider", "manual"),
                          hash=digest, date_verified=bool(source["published"]),
                          editorial=assess(source["title"], source["text"], policy))
            pool.append(source)
            hashes.add(digest)
        except (OSError, ValueError, ImportError) as e:
            errors.append(f"{candidate['url']}: {type(e).__name__}")
    ranked = sorted(pool, key=lambda s: s["editorial"]["score"], reverse=True)
    for source in ranked:
        if len(evidence) >= policy["source_limit"] or budget < 300:
            break
        keywords = policy["keywords"] + [word for words in SIGNALS.values() for word in words]
        excerpt = compact(source["text"], keywords, min(budget, policy["source_chars"]))
        source = {**source, "id": f"s{len(evidence)+1}", "text": excerpt}
        evidence.append(source)
        budget -= len(excerpt)
    write("output/topic_candidates.json", [{"url": s["url"], "title": s["title"],
          "provider": s["provider"], "kind": s["kind"], "editorial": s["editorial"],
          "selected_for_brief": any(e["url"] == s["url"] for e in evidence)} for s in ranked])
    write("output/collection_status.json", {"providers": collector.statuses, "errors": errors,
          "candidates": len(candidates), "extracted": len(evidence)})
    if not evidence:
        write("output/collection_errors.json", errors)
        raise ValueError("확인 가능한 원문이 없습니다. output/collection_status.json에서 출처별 상태를 확인하세요")
    brief = {"created": datetime.now(KST).isoformat(), "sources": evidence,
             "card_count": policy["image_count"] - 1, "collection_errors": errors}
    write("output/brief.json", brief)
    Path("output/instructions.txt").write_text(writing_rules(policy), encoding="utf-8")
    write("output/schema.json", SCHEMA)
    print(f"원문 {len(evidence)}개 / 근거 {sum(len(s['text']) for s in evidence)}자: output/brief.json")
    return brief


def finish(result, brief, policy, captures):
    post, sources = format_post(result["post"]), brief["sources"]
    validate(post, sources, policy["image_count"])
    # The brief can be passed to a model without retrieving entire documents again.
    used_ids = {sid for p in post["paragraphs"] + post["cards"] for sid in p["source_ids"]}
    cited = [s for s in sources if s["id"] in used_ids]
    if not cited:
        raise ValueError("사용한 출처가 없습니다")
    digest = fingerprint(post["topic_key"])[:12]
    destination = Path("output") / digest
    history = recent_history("state/history.json", policy["duplicate_days"])
    if destination.exists() or any(r["topic_key"] == post["topic_key"] for r in history):
        raise ValueError("이미 제작한 주제입니다. 기존 결과를 확인하세요")
    if captures and not policy["capture"]:
        raise ValueError("캡처 설정을 활성화해야 합니다")
    # Publish only a complete bundle; a failed render leaves no partial final set.
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="bundle-", dir="output"))
    try:
        files = render(post, sources, staging, captures)
        body = "\n\n".join(p["text"].strip() for p in post["paragraphs"])
        lines = [post["title"], "", "[이미지 01_thumbnail.png]", ""]
        for number, paragraph in enumerate(post["paragraphs"], 1):
            lines.extend([paragraph["text"].strip(), ""])
            for i, card in enumerate(post["cards"], 2):
                if card["after"] == number:
                    lines.extend([f"[이미지 {i:02d}_body.png]", ""])
        lines += ["자료 출처", ""] + [f"{s['id']}: {s['title']}\n{s['url']}" for s in cited]
        (staging / "post.txt").write_text("\n".join(lines), encoding="utf-8")
        write(staging / "review.json", {"characters_with_spaces": len(body),
              "warnings": post["warnings"], "usage": result.get("usage", {}),
              "model": result.get("model", "manual"),
              "editorial": post.get("editorial", {}),
              "note": "출처 연결·형식은 자동 검사. 의미 일치와 캡처 이용 조건은 게시 전 검토 필요.",
              "captures": captures})
        write(staging / "sources.json", [{k: v for k, v in s.items() if k != "text"} for s in cited])
        write(staging / "draft.json", post)
        write_delivery(staging, post["title"], files)
        write(staging / "manifest.json", {"topic_key": post["topic_key"], "images": files,
              "post": "post.txt", "delivery": "delivery.json", "gallery": "gallery.html"})
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    history.append({"date": datetime.now(KST).isoformat(), "topic_key": post["topic_key"],
                    "urls": [s["url"] for s in cited], "hashes": [s["hash"] for s in cited]})
    write("state/history.json", history)
    print(f"완성: {destination}/post.txt / 이미지 {len(files)}장")


def main():
    parser = argparse.ArgumentParser(description="이슈 탐색 → 원고 → 이미지 패키지")
    parser.add_argument("command", choices=["prepare", "build", "run"])
    parser.add_argument("--policy", default="policy.json")
    parser.add_argument("--url", action="append", default=[], help="자동 탐색 대신 사용할 실제 원문; 반복 가능")
    parser.add_argument("--brief", default="output/brief.json")
    parser.add_argument("--draft", help="수동 작성 JSON; build에서 필수")
    parser.add_argument("--captures", help="선택한 카드의 캡처 명세 JSON 파일")
    args = parser.parse_args()
    try:
        policy = read(args.policy)
        if not policy or policy["image_count"] not in (3, 4):
            raise ValueError("policy.json과 이미지 개수(3 또는 4)를 확인하세요")
        if args.command in ("prepare", "run"):
            brief = prepare(args, policy)
            if args.command == "prepare":
                return
            result = generate(brief["sources"], policy, ".cache")
        else:
            if not args.draft:
                raise ValueError("build에는 --draft draft.json이 필요합니다")
            brief = read(args.brief)
            if not brief:
                raise ValueError("먼저 prepare로 근거 자료를 준비하세요")
            result = {"post": read(args.draft)}
        finish(result, brief, policy, read(args.captures, []) if args.captures else [])
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"중단: {error}\n")


if __name__ == "__main__":
    main()

