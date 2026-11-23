import tempfile
import unittest
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from economicissue.images import square_image
from economicissue.render import render
from test_pipeline import fixture


class SquareImagesTests(unittest.TestCase):
    def test_delivery_capture_is_square_and_both_originals_are_preserved(self):
        post, sources = fixture()
        def capture(spec, source, path):
            raw = path.parent / 'raw-captures' / path.name
            raw.parent.mkdir(parents=True, exist_ok=True)
            Image.new('RGB', (600, 300), 'white').save(raw)
            Image.new('RGB', (600, 300), 'red').save(path)
        with tempfile.TemporaryDirectory() as tmp, patch('economicissue.render.capture_source', capture):
            root = Path(tmp)
            files = render(post, sources, root, [{'card': 2, 'source_id': 's1', 'rights': 'fixture'}])
            review = json.loads((root / 'image_review.json').read_text())
            item = next(row for row in review if row['image'] == files[1])
            for name in ('raw', 'marked'):
                original = root / item[name + '_path']
                self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), item[name + '_sha256'])
                with Image.open(original) as image:
                    self.assertEqual(image.size, (600, 300))
            with Image.open(root / files[1]) as image:
                self.assertEqual(image.size, (1080, 1080))

    def test_wide_and_tall_images_keep_edges_and_become_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            for size, origin in [((1080, 200), (0, 440)), ((200, 1080), (440, 0))]:
                path = Path(tmp) / 'capture.png'
                Image.new('RGB', size, '#e32636').save(path)
                square_image(path)
                with Image.open(path) as image:
                    self.assertEqual(image.size, (1080, 1080))
                    self.assertEqual(image.getpixel(origin), (227, 38, 54))
                    self.assertEqual(image.getpixel((origin[0]+size[0]-1, origin[1]+size[1]-1)), (227, 38, 54))
                    self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
                before = path.read_bytes()
                square_image(path)
                self.assertEqual(path.read_bytes(), before)
