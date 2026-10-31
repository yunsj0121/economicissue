import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from economicissue.cli import finish
from economicissue.voice import narrative_review
from economicissue.writer import SCHEMA, validate
from test_pipeline import fixture
from test_publication import publication_fixture


def plan():
    return {
        "focus": "한 달의 생활비만으로 평소 살림을 판단할 수 있는지에 대한 고민",
        "source_ids": ["s1"],
        "thought_flow": "한 달 지출을 보고 연간 비정기 지출까지 고려하는 판단으로 이어짐",
        "reflection_paragraphs": [2],
        "ending_mode": "남은 고민",
        "ending_reason": "일반론을 반복하지 않고 해당 가구의 조건에 관한 궁금증을 남김",
        "self_review": "2번 의견의 판단 이유를 점검하고 중복 조언을 줄임",
    }


class VoiceTests(unittest.TestCase):
    def test_new_schema_requires_plan_but_legacy_draft_still_builds(self):
        self.assertIn("narrative", SCHEMA["required"])
        post, sources = fixture()
        validate(post, sources, 3)
        self.assertEqual(narrative_review(post)["status"], "missing_plan")
        post["narrative"] = plan()
        validate(post, sources, 3)
        # Connected notes are still a model's self-report, not a quality pass.
        self.assertEqual(narrative_review(post)["status"], "needs_editor_review")

    def test_plan_rejects_invented_sources_and_non_opinion_anchors(self):
        post, sources = fixture()
        post["narrative"] = plan()
        invalid = (
            {"source_ids": ["invented"]}, {"source_ids": []},
            {"reflection_paragraphs": [0]}, {"reflection_paragraphs": [3]},
            {"reflection_paragraphs": [True]}, {"reflection_paragraphs": [1]},
            {"reflection_paragraphs": [2, 2]}, {"reflection_paragraphs": []},
            {"focus": " "}, {"self_review": ""}, {"ending_mode": "자동 체크리스트"},
        )
        for fields in invalid:
            broken = copy.deepcopy(post)
            broken["narrative"].update(fields)
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                validate(broken, sources, 3)

    def test_bundle_preserves_editor_notes_without_publishing_them(self):
        post, sources, policy = publication_fixture()
        post["narrative"] = plan()
        old = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                finish({"post": post}, {"sources": sources}, policy, [])
                folder = next(Path("output").iterdir())
                review = json.loads((folder / "review.json").read_text())
                notes = review["narrative_review"]
                self.assertEqual(notes["model_notes"], post["narrative"])
                self.assertTrue(notes["checks"])
                for name in ("post.txt", "copyable_post.md", "preview.html"):
                    text = (folder / name).read_text()
                    self.assertNotIn(post["narrative"]["focus"], text)
                    self.assertNotIn("needs_editor_review", text)
            finally:
                os.chdir(old)


if __name__ == "__main__":
    unittest.main()
