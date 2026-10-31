import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from economicissue.cli import finish
from economicissue.sources import canonical, compact
from economicissue.writer import generate, validate
from economicissue.render import render


def fixture():
    sources = [{"id": "s1", "title": "가상 테스트 자료", "url": "https://example.com/report",
                "text": "테스트에만 사용하는 내용", "hash": "abc", "published": "2026-01-01"}]
    post = {"ready": True, "reason": "", "topic_key": "fixture-2026", "title": "생활비를 살펴볼 때",
            "thumbnail": "생활비 점검\n어디부터 할까?", "warnings": [],
            "paragraphs": [{"kind": "fact", "text": "테스트를 위한 사실 문단입니다.", "source_ids": ["s1"]},
                           {"kind": "opinion", "text": "조건을 살펴볼 필요가 있겠습니다.", "source_ids": []}],
            "cards": [{"title": "기준 확인", "text": "조사 대상을 먼저 확인합니다.", "source_ids": ["s1"], "after": 1},
                      {"title": "조건 비교", "text": "다른 조건도 함께 살펴봅니다.", "source_ids": ["s1"], "after": 2}]}
    return post, sources


class PipelineTests(unittest.TestCase):
    def test_compact_preserves_order_and_budget(self):
        result = compact("도입 문맥\n무관한 이야기\n저축 관련 근거\n생활비 관련 근거", ["저축", "생활비"], 25)
        self.assertLessEqual(len(result), 25)
        self.assertTrue(result.startswith("도입 문맥"))
        self.assertIn("저축", result)
        self.assertNotIn("무관한", result)

    def test_url_tracking_removed_but_article_id_kept(self):
        self.assertEqual(canonical("https://example.com/view?id=7&utm_source=x#part"),
                         "https://example.com/view?id=7")

    def test_rejects_missing_citation_and_bad_placement(self):
        post, sources = fixture()
        for modify in [lambda p: p["paragraphs"][0].update(source_ids=[]),
                       lambda p: p["cards"][0].update(after=99),
                       lambda p: p["cards"][0].update(source_ids=["invented"]),
                       lambda p: p.update(thumbnail=""),
                       lambda p: p["paragraphs"].append(p["paragraphs"][0])]:
            broken = copy.deepcopy(post)
            modify(broken)
            with self.assertRaises(ValueError):
                validate(broken, sources, 3)

    def test_cached_generation_does_not_call_api(self):
        post, sources = fixture()
        response = {"status": "completed", "usage": {"input_tokens": 100, "output_tokens": 80},
                    "output": [{"content": [{"type": "output_text", "text": json.dumps(post)}]}]}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), \
             patch("economicissue.writer.request", return_value=(json.dumps(response).encode(), "https://api.openai.com")) as api:
            policy = {"image_count": 3, "max_output_tokens": 500}
            first = generate(sources, policy, tmp)
            sources[0]["retrieved"] = "new retrieval time must not cause another model call"
            second = generate(sources, policy, tmp)
            self.assertEqual(first, second)
            self.assertEqual(api.call_count, 1)

    def test_bundle_and_partial_failure_cleanup(self):
        post, sources = fixture()
        policy = {"image_count": 3, "duplicate_days": 45, "capture": False}
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                with patch("economicissue.cli.render", side_effect=ValueError("render failed")):
                    with self.assertRaises(ValueError):
                        finish({"post": post}, {"sources": sources}, policy, [])
                self.assertEqual(list(Path("output").iterdir()), [])
                self.assertFalse(Path("state/history.json").exists())
                finish({"post": post}, {"sources": sources}, policy, [])
                folders = list(Path("output").iterdir())
                self.assertEqual(len(folders), 1)
                manifest = json.loads((folders[0] / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(len(manifest["images"]), 3)
                self.assertTrue((folders[0] / manifest["generation_jobs"]).is_file())
                self.assertNotIn('gallery', manifest)
                self.assertEqual(manifest['delivery_status'], 'pending_generation_and_native_attachment')
                delivery = json.loads((folders[0] / manifest["delivery"]).read_text(encoding="utf-8"))
                self.assertEqual(delivery["order"], manifest["images"])
                for name in manifest["images"]:
                    with Image.open(folders[0] / name) as im:
                        self.assertEqual(im.size, (1080, 1080))
                text = (folders[0] / "post.txt").read_text(encoding="utf-8")
                self.assertIn("[이미지 02_body.png]", text)
                self.assertIn("테스트를 위한 사실 문단입니다\n", text)
                self.assertNotIn("사실 문단입니다.", text)
                with self.assertRaises(ValueError):
                    finish({"post": post}, {"sources": sources}, policy, [])
            finally:
                os.chdir(original)

    def test_thumbnail_capture_replaces_background_without_extra_files(self):
        post, sources = fixture()
        def fake_capture(spec, source, path):
            Image.new("RGB", (700, 600), "#555555").save(path)
        with tempfile.TemporaryDirectory() as tmp, patch("economicissue.render.capture_source", fake_capture):
            files = render(post, sources, tmp, [{"card": 1, "source_id": "s1",
                           "selector": "#photo", "rights": "fixture"}])
            self.assertEqual(len(files), 3)
            self.assertEqual(len(list(Path(tmp).glob("*.png"))), 3)


if __name__ == "__main__":
    unittest.main()

