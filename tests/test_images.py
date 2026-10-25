import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from economicissue.images import square_image, IMAGE_SIZE
from economicissue.delivery import write_delivery


class SquareImageTests(unittest.TestCase):
    def test_wide_and_tall_captures_keep_edges_and_highlight_with_padding(self):
        with tempfile.TemporaryDirectory() as tmp:
            for size, offset in [((1080, 200), (0, 440)), ((200, 1080), (440, 0))]:
                path = Path(tmp) / 'capture.png'
                original = Image.new('RGB', size, '#e32636')
                original.save(path)
                square_image(path)
                with Image.open(path) as result:
                    self.assertEqual(result.size, IMAGE_SIZE)
                    self.assertEqual(result.getpixel(offset), (227, 38, 54))
                    self.assertEqual(result.getpixel((offset[0] + size[0] - 1, offset[1] + size[1] - 1)), (227, 38, 54))
                    self.assertEqual(result.getpixel((0, 0)), (255, 255, 255))
                before = path.read_bytes()
                square_image(path)
                self.assertEqual(path.read_bytes(), before)

    def test_gallery_normalizes_external_thumbnail_and_body_before_embedding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            names = ['01.png', '02.png', '03.png']
            for name, size in zip(names, [(1600, 1000), (300, 1200), (700, 200)]):
                Image.new('RGB', size, 'navy').save(root / name)
            write_delivery(root, '제목', names)
            for name in names:
                with Image.open(root / name) as im:
                    self.assertEqual(im.size, IMAGE_SIZE)
            info = json.loads((root / 'delivery.json').read_text())
            self.assertEqual(info['aspect_ratio'], '1:1')
            self.assertEqual(info['order'], names)


if __name__ == '__main__':
    unittest.main()
