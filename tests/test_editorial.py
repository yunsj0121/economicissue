import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from economicissue.cli import prepare
from economicissue.direct import discover_direct
from economicissue.editorial import assess
from economicissue.formatting import format_post
from economicissue.writer import validate, generate
from test_pipeline import fixture


class EditorialTests(unittest.TestCase):
    def test_money_dilemma_beats_repeated_keywords_and_numbers_alone(self):
        weak = assess("생활비 저축 연금 노후 월급 정리 " * 50)
        strong = assess("외벌이 가족 생활비 450만원, 저축이 부족해 고민입니다")
        self.assertGreater(strong["score"], weak["score"])
        self.assertNotIn("구체금액·비율", assess("2026년 10월 25일 안내")["signals"])
        self.assertIn("가족과 돈", assess("부모 생활비 지원 고민")["families"])

    def test_prepare_reads_later_body_before_filling_source_limit(self):
        policy = json.loads(Path("policy.json").read_text())
        policy.update(source_limit=1, evidence_chars=800, source_chars=600)
        rows = [{"url": "https://example.com/" + name, "title": name, "kind": "report"}
                for name in ("weak", "strong")]

        class FakeCollector:
            statuses = []
            def __init__(self, *args):
                pass
            def extract(self, url):
                text = ("생활비 통계 안내\n" if url.endswith("weak") else
                        "외벌이 부부 생활비 450만원\n저축이 부족해 고민합니다\n선택에 따라 차이가 있습니다\n")
                return {"url": url, "title": "자료", "text": text * 12, "published": ""}

        old = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                with patch("economicissue.cli.Collector", FakeCollector), \
                     patch("economicissue.cli.discover", return_value=(rows, [])):
                    brief = prepare(SimpleNamespace(url=[]), policy)
                self.assertTrue(brief["sources"][0]["url"].endswith("strong"))
                self.assertLessEqual(sum(len(s["text"]) for s in brief["sources"]), 800)
                candidates = json.loads(Path("output/topic_candidates.json").read_text())
                self.assertEqual(len(candidates), 2)
                self.assertEqual(sum(c["selected_for_brief"] for c in candidates), 1)
                self.assertIn("후보 3개", Path("output/instructions.txt").read_text())
            finally:
                os.chdir(old)

    def test_curated_official_page_must_be_fetched_before_becoming_candidate(self):
        class Fake:
            policy = {"direct_sources": [{"id": "official", "kind": "official", "format": "page",
                       "url": "https://example.com/pension", "title": "연금 선택"}]}
            def fetch_public(self, url):
                raise OSError("unavailable")
        rows, statuses = discover_direct(Fake())
        self.assertEqual(rows, [])
        self.assertEqual(statuses[0]["status"], "failed")

    def test_title_plan_requires_distinct_styles_and_final_choice(self):
        post, sources = fixture()
        post["title"] = "생활비를 살펴볼 때."
        post["editorial"] = {"situation": "외벌이 생활비", "question": "어디서 줄일까", "reason": "자기 상황과 비교 가능",
            "source_ids": ["s1"], "title_candidates": [
                {"style": "비교형", "title": post["title"]},
                {"style": "결과형", "title": "생활비를 계산했습니다"},
                {"style": "선택형", "title": "생활비 어디서 줄일까?"}]}
        validate(format_post(post), sources, 3)
        for modify in (lambda p: p.update(title="후보에 없는 제목"),
                       lambda p: p["editorial"]["title_candidates"][1].update(style="비교형"),
                       lambda p: p["editorial"].update(source_ids=["invented"])):
            broken = copy.deepcopy(post)
            modify(broken)
            with self.assertRaises(ValueError):
                validate(format_post(broken), sources, 3)

    def test_changed_editorial_policy_invalidates_model_cache(self):
        post, sources = fixture()
        response = {"status": "completed", "output": [{"content": [{"type": "output_text", "text": json.dumps(post)}]}]}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), \
             patch("economicissue.writer.request", return_value=(json.dumps(response).encode(), "")) as api:
            policy = {"image_count": 3, "max_output_tokens": 500, "topic_families": {"생활비": []}}
            generate(sources, policy, tmp)
            generate(sources, policy, tmp)
            generate(sources, {**policy, "topic_families": {"가족": []}}, tmp)
            self.assertEqual(api.call_count, 2)


if __name__ == "__main__":
    unittest.main()
