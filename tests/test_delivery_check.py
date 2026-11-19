import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from economicissue.delivery import delivery_check, write_delivery


class DeliveryCheckTests(unittest.TestCase):
    def setUp(self):
        bundle = tempfile.TemporaryDirectory()
        self.addCleanup(bundle.cleanup)
        self.directory = Path(bundle.name)
        self.files = ["01_thumbnail.png", "02_body.png", "03_body.png"]
        for name in self.files:
            Image.new("RGB", (30, 30), "white").save(self.directory / name)
        self.reviews = [{"image": name, "type": "capture"} for name in self.files[1:]]
        self.write_plan()

    def write_plan(self):
        (self.directory / "image_review.json").write_text(json.dumps(self.reviews))
        write_delivery(self.directory, "제목", self.files, {"cards": [{}, {}], "thumbnail": "표지"})
        self.plan = json.loads((self.directory / "delivery.json").read_text())

    def test_missing_and_corrupt_png_are_reported_by_filename(self):
        (self.directory / self.files[1]).unlink()
        (self.directory / self.files[2]).write_bytes(b"invalid png")
        status = delivery_check(self.directory)
        self.assertEqual([row["file_status"] for row in status["images"]],
                         ["validated", "invalid", "invalid"])
        self.assertIn("누락", status["images"][1]["reason"])
        self.assertIn("읽을 수 없습니다", status["images"][2]["reason"])
        self.assertEqual(status["attachment_status"], "pending")
        with self.assertRaisesRegex(ValueError, "02_body.png"):
            self.write_plan()

    def test_order_must_match_the_post(self):
        with self.assertRaisesRegex(ValueError, "수 또는 순서"):
            write_delivery(self.directory, "제목", self.files[:2], {"cards": [{}, {}]})
        with self.assertRaisesRegex(ValueError, "수 또는 순서"):
            write_delivery(self.directory, "제목", self.files[::-1])

    def test_partial_attachment_and_unsupported_tool(self):
        observations = {}
        for item, method in zip(self.plan["images"][:2],
                                ("image_gen_result_return", "native_png_attachment")):
            observations[item["path"]] = {
                "content_reviewed": True, "attachment": "success",
                "receipt": {"method": method, "sha256": item["sha256"],
                            "tool": "fixture.tool", "result_ref": item["path"] + "-receipt"},
            }
        observations[self.files[2]] = {"content_reviewed": True, "attachment": "unsupported"}
        status = delivery_check(self.directory, observations)
        self.assertEqual(status["reported_attached"], 2)
        self.assertEqual(status["missing_attachments"], [self.files[2]])
        self.assertEqual(status["images"][2]["attachment"], "unsupported")
        self.assertEqual(status["mobile_display"], "unverified")
        self.assertEqual(status["mobile_bulk_save"], "unverified")
        self.assertEqual(status["attachment_status"], "pending")
        observations[self.files[2]]["attachment"] = "success"
        self.assertEqual(delivery_check(self.directory, observations)["reported_attached"], 2)
        observations[self.files[1]]["receipt"]["method"] = "view_image"
        self.assertEqual(delivery_check(self.directory, observations)["reported_attached"], 1)

    def test_failed_capture_does_not_become_a_generation_job(self):
        self.reviews[0].update(type="capture_failed", reason="timeout")
        self.write_plan()
        jobs = json.loads((self.directory / "image-generation.json").read_text())["jobs"]
        self.assertEqual([job["image_index"] for job in jobs], [1])
        row = delivery_check(self.directory)["images"][1]
        self.assertEqual(row["file_status"], "capture_unavailable")
        self.assertEqual(row["reason"], "timeout")
