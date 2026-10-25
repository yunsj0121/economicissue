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
from .writer import RULES, SCHEMA, generate, validate
from .render import render

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
                raise ValueError("KOSIS_API_KEY �ʿ�")
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
    for candidate in candidates[:policy.get("fetch_limit", 12)]:
        if candidate["url"] in used or len(evidence) >= policy["source_limit"] or budget < 300:
            continue
        try:
            source = collector.extract(candidate["url"])
            source["published"] = source["published"] or candidate.get("published", "")
            if source["published"]:
                normalized = date_iso(source["published"])
                published = datetime.fromisoformat(normalized) if normalized else None
                if published is None:
                    raise ValueError("���� ��¥ �ؼ� �Ұ�")
                if published.tzinfo is None:
                    published = published.replace(tzinfo=KST)
                age = (datetime.now(KST) - published).days
                maximum = policy["max_age_days"] if candidate["kind"] in {"news", "community"} else policy.get("report_age_days", 120)
                if candidate["kind"] != "manual" and (age < 0 or age > maximum):
                    continue
            digest = fingerprint(source["text"])
            if source["url"] in used or digest in hashes:
                continue
            excerpt = compact(source["text"], policy["keywords"], min(budget, policy["source_chars"]))
            budget -= len(excerpt)
            source.update(id=f"s{len(evidence)+1}", kind=candidate["kind"], provider=candidate.get("provider", "manual"),
                          hash=digest, text=excerpt, date_verified=bool(source["published"]))
            source["title"] = source["title"] or candidate["title"]
            evidence.append(source)
            hashes.add(digest)
        except (OSError, ValueError, ImportError) as e:
            errors.append(f"{candidate['url']}: {type(e).__name__}")
    write("output/collection_status.json", {"providers": collector.statuses, "errors": errors,
          "candidates": len(candidates), "extracted": len(evidence)})
    if not evidence:
        write("output/collection_errors.json", errors)
        raise ValueError("Ȯ�� ������ ������ �����ϴ�. output/collection_status.json���� ��ó�� ���¸� Ȯ���ϼ���")
    brief = {"created": datetime.now(KST).isoformat(), "sources": evidence,
             "card_count": policy["image_count"] - 1, "collection_errors": errors}
    write("output/brief.json", brief)
    Path("output/instructions.txt").write_text(RULES, encoding="utf-8")
    write("output/schema.json", SCHEMA)
    print(f"���� {len(evidence)}�� / �ٰ� {sum(len(s['text']) for s in evidence)}��: output/brief.json")
    return brief


def finish(result, brief, policy, captures):
    post, sources = result["post"], brief["sources"]
    validate(post, sources, policy["image_count"])
    # The brief can be passed to a model without retrieving entire documents again.
    used_ids = {sid for p in post["paragraphs"] + post["cards"] for sid in p["source_ids"]}
    cited = [s for s in sources if s["id"] in used_ids]
    if not cited:
        raise ValueError("����� ��ó�� �����ϴ�")
    digest = fingerprint(post["topic_key"])[:12]
    destination = Path("output") / digest
    history = recent_history("state/history.json", policy["duplicate_days"])
    if destination.exists() or any(r["topic_key"] == post["topic_key"] for r in history):
        raise ValueError("�̹� ������ �����Դϴ�. ���� ����� Ȯ���ϼ���")
    if captures and not policy["capture"]:
        raise ValueError("ĸó ������ Ȱ��ȭ�ؾ� �մϴ�")
    # Publish only a complete bundle; a failed render leaves no partial final set.
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="bundle-", dir="output"))
    try:
        files = render(post, sources, staging, captures)
        body = "\n\n".join(p["text"].strip() for p in post["paragraphs"])
        lines = [post["title"], "", "[�̹��� 01_thumbnail.png]", ""]
        for number, paragraph in enumerate(post["paragraphs"], 1):
            lines.extend([paragraph["text"].strip(), ""])
            for i, card in enumerate(post["cards"], 2):
                if card["after"] == number:
                    lines.extend([f"[�̹��� {i:02d}_body.png]", ""])
        lines += ["�ڷ� ��ó", ""] + [f"{s['id']}: {s['title']}\n{s['url']}" for s in cited]
        (staging / "post.txt").write_text("\n".join(lines), encoding="utf-8")
        write(staging / "review.json", {"characters_with_spaces": len(body),
              "warnings": post["warnings"], "usage": result.get("usage", {}),
              "model": result.get("model", "manual"),
              "note": "��ó ���ᡤ������ �ڵ� �˻�. �ǹ� ��ġ�� ĸó �̿� ������ �Խ� �� ���� �ʿ�.",
              "captures": captures})
        write(staging / "sources.json", [{k: v for k, v in s.items() if k != "text"} for s in cited])
        write(staging / "draft.json", post)
        write(staging / "manifest.json", {"topic_key": post["topic_key"], "images": files, "post": "post.txt"})
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    history.append({"date": datetime.now(KST).isoformat(), "topic_key": post["topic_key"],
                    "urls": [s["url"] for s in cited], "hashes": [s["hash"] for s in cited]})
    write("state/history.json", history)
    print(f"�ϼ�: {destination}/post.txt / �̹��� {len(files)}��")


def main():
    parser = argparse.ArgumentParser(description="�̽� Ž�� �� ���� �� �̹��� ��Ű��")
    parser.add_argument("command", choices=["prepare", "build", "run"])
    parser.add_argument("--policy", default="policy.json")
    parser.add_argument("--url", action="append", default=[], help="�ڵ� Ž�� ��� ����� ���� ����; �ݺ� ����")
    parser.add_argument("--brief", default="output/brief.json")
    parser.add_argument("--draft", help="���� �ۼ� JSON; build���� �ʼ�")
    parser.add_argument("--captures", help="������ ī���� ĸó ���� JSON ����")
    args = parser.parse_args()
    try:
        policy = read(args.policy)
        if not policy or policy["image_count"] not in (3, 4):
            raise ValueError("policy.json�� �̹��� ����(3 �Ǵ� 4)�� Ȯ���ϼ���")
        if args.command in ("prepare", "run"):
            brief = prepare(args, policy)
            if args.command == "prepare":
                return
            result = generate(brief["sources"], policy, ".cache")
        else:
            if not args.draft:
                raise ValueError("build���� --draft draft.json�� �ʿ��մϴ�")
            brief = read(args.brief)
            if not brief:
                raise ValueError("���� prepare�� �ٰ� �ڷḦ �غ��ϼ���")
            result = {"post": read(args.draft)}
        finish(result, brief, policy, read(args.captures, []) if args.captures else [])
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"�ߴ�: {error}\n")


if __name__ == "__main__":
    main()
