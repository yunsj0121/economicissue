import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from economicissue.delivery import write_delivery
from economicissue.formatting import format_post, mobile_text
from economicissue.render import capture_source, HIGHLIGHT_RECTS, underline_capture
from test_pipeline import fixture


class DeliveryTests(unittest.TestCase):
    def test_mobile_copy_keeps_numbers_urls_and_question(self):
        text = '연 3.5%입니다. 다음 문장입니다.어떤 차이일까요? 확인합니다.'
        self.assertEqual(mobile_text(text),
                         '연 3.5%입니다\n다음 문장입니다\n어떤 차이일까요?\n확인합니다')
        self.assertEqual(mobile_text('주소 https://example.com/a.b?q=3.5. 다음 문장.'),
                         '주소 https://example.com/a.b?q=3.5\n다음 문장')
        self.assertTrue(all(len(line) <= 32 for line in mobile_text('가' * 70).splitlines()))

    def test_format_is_idempotent_without_mutating_draft(self):
        post, _ = fixture()
        formatted = format_post(post)
        self.assertTrue(post['paragraphs'][0]['text'].endswith('.'))
        self.assertFalse(formatted['paragraphs'][0]['text'].endswith('.'))
        self.assertEqual(format_post(formatted), formatted)

    def test_body_capture_requires_highlights_before_browser(self):
        with self.assertRaisesRegex(ValueError, 'highlights'):
            capture_source({'card': 2, 'selector': '#body', 'rights': 'fixture'},
                           {'url': 'https://example.com'}, Path('unused.png'))

    def test_gallery_preserves_final_order_and_user_alt_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            files = ['01_thumbnail.png', '02_body.png', '03_body.png']
            for name in files:
                Image.new('RGB', (30, 30), 'white').save(directory / name)
            Image.new('RGB', (30, 30), 'black').save(directory / 'unrelated.png')
            write_delivery(directory, '<테스트 제목>', files)
            delivery = json.loads((directory / 'delivery.json').read_text())
            self.assertEqual(delivery['order'], files)
            self.assertEqual(delivery['presentation'], 'native_multi_image_gallery')
            self.assertTrue(all(i['alt_text'] is None for i in delivery['images']))
            page = (directory / 'gallery.html').read_text()
            self.assertNotIn('unrelated.png', page)
            self.assertIn('&lt;테스트 제목&gt;', page)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch()
                tab = browser.new_page(viewport={'width': 390, 'height': 844})
                tab.goto((directory / 'gallery.html').as_uri())
                self.assertEqual(tab.locator('nav button').count(), 3)
                tab.locator('nav button').nth(2).click()
                self.assertEqual(tab.locator('#position').inner_text(), '3 / 3')
                with tab.expect_download() as event:
                    tab.locator('#download').click()
                self.assertEqual(event.value.suggested_filename, '03_body.png')
                browser.close()

    def test_wrapped_source_text_underline_and_invalid_phrase(self):
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(java_script_enabled=False)
            page = context.new_page()
            page.set_content('<article style="width:300px;font:24px sans-serif">'
                             'The household <b>income rose significantly</b> this year according to the report'
                             '</article>')
            target = page.locator('article')
            phrase = 'household income rose significantly this year'
            rects = target.evaluate(HIGHLIGHT_RECTS, [phrase])
            self.assertGreater(len({round(r[1]) for r in rects}), 1)
            image = Path(tmp) / 'capture.png'
            target.screenshot(path=str(image))
            box = target.bounding_box()
            underline_capture(image, rects, box['width'], box['height'])
            with Image.open(image) as im:
                self.assertTrue(any(pixel == (227, 38, 54) for pixel in im.getdata()))
            for invalid in ['missing phrase', 'o']:
                with self.assertRaises(Exception):
                    target.evaluate(HIGHLIGHT_RECTS, [invalid])
            browser.close()
