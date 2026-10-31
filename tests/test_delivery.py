import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from PIL import Image
from economicissue.delivery import write_delivery, write_image_gallery
from economicissue.browser import launch
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
        self.assertEqual(mobile_text('가' * 70), '가' * 70)

    def test_complete_sentences_and_paragraph_spacing_survive_formatting(self):
        sentence = '퇴직하고 월급은 끊겼는데 국민연금을 받기까지 몇 년이 남았다면 연금을 조금 일찍 받고 싶어질 수 있어요'
        text = sentence + '.\n\n월 수령액과 누적 수령액은 함께 비교해야 해요.'
        expected = sentence + '\n\n월 수령액과 누적 수령액은 함께 비교해야 해요'
        self.assertEqual(mobile_text(text), expected)
        post, _ = fixture()
        post['paragraphs'][0]['text'] = text
        formatted = format_post(post)
        self.assertEqual(formatted['paragraphs'][0]['text'], expected)
        self.assertEqual(formatted['thumbnail'], post['thumbnail'])

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
            self.assertEqual(delivery['delivery_status'], 'pending_generation_and_native_attachment')
            self.assertEqual(delivery['required_generated_image_results'], 3)
            self.assertEqual(delivery['required_original_capture_attachments'], 0)
            self.assertFalse(delivery['manifest_is_delivery_receipt'])
            self.assertFalse((directory / 'gallery.html').exists())
            self.assertFalse((directory / 'images.zip').exists())
            write_image_gallery(directory, '<테스트 제목>', files)
            with zipfile.ZipFile(directory / 'images.zip') as archive:
                self.assertEqual(archive.namelist(), files)
                self.assertEqual(archive.read(files[0]), (directory / files[0]).read_bytes())
            page = (directory / 'gallery.html').read_text()
            self.assertNotIn('unrelated.png', page)
            self.assertIn('&lt;테스트 제목&gt;', page)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = launch(p.chromium)
                tab = browser.new_page(viewport={'width': 390, 'height': 844})
                tab.route('https://example.com/gallery', lambda route: route.fulfill(body=page, content_type='text/html'))
                tab.goto('https://example.com/gallery')
                self.assertEqual(tab.locator('nav button').count(), 3)
                tab.locator('nav button').nth(2).click()
                self.assertEqual(tab.locator('#position').inner_text(), '3 / 3')
                with tab.expect_download() as event:
                    tab.locator('#download').click()
                self.assertEqual(event.value.suggested_filename, '03_body.png')
                with tab.expect_download() as all_event:
                    tab.locator('#download-all').click()
                self.assertEqual(all_event.value.suggested_filename, 'images.zip')
                with zipfile.ZipFile(all_event.value.path()) as archive:
                    self.assertEqual(archive.namelist(), files)
                browser.close()

    def test_real_captures_are_excluded_from_generation_and_kept_as_originals(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            files = ['01_thumbnail.png', '02_body.png', '03_body.png']
            for name in files:
                Image.new('RGB', (30, 30), 'white').save(directory / name)
            raw = directory / 'raw-captures' / files[1]
            raw.parent.mkdir()
            raw.write_bytes((directory / files[1]).read_bytes())
            digest = hashlib.sha256(raw.read_bytes()).hexdigest()
            review = [{'image':files[0],'type':'text_layout'},
                      {'image':files[1],'type':'capture','url':'https://example.com/report',
                       'source_id':'s1','selector':'#real-table','raw_path':'raw-captures/'+files[1],
                       'raw_sha256':digest},
                      {'image':files[2],'type':'chart'}]
            (directory / 'image_review.json').write_text(json.dumps(review))
            post, _ = fixture()
            write_delivery(directory, post['title'], files, post)
            plan = json.loads((directory / 'delivery.json').read_text())
            jobs = json.loads((directory / 'image-generation.json').read_text())['jobs']
            self.assertEqual([job['image_index'] for job in jobs], [1, 3])
            self.assertEqual(plan['required_generated_image_results'], 2)
            self.assertEqual(plan['required_original_capture_attachments'], 1)
            capture = plan['images'][1]
            self.assertEqual(capture['asset_type'], 'source_capture')
            self.assertFalse(capture['image_generation_allowed'])
            self.assertEqual(capture['raw_sha256'], digest)
            self.assertEqual(raw.read_bytes(), (directory / files[1]).read_bytes())
            self.assertEqual([group['image_indices'] for group in plan['gallery_groups']], [[1, 3], [2]])
            self.assertTrue(all(job['tool'] == 'image_gen.imagegen' for job in jobs))
            self.assertTrue(all('original_result_ref' not in item for item in plan['images']))
            review[1]['type'] = 'capture_failed'
            (directory / 'image_review.json').write_text(json.dumps(review))
            write_delivery(directory, post['title'], files, post)
            plan = json.loads((directory / 'delivery.json').read_text())
            self.assertEqual(plan['required_original_capture_attachments'], 0)

    def test_wrapped_source_text_underline_and_invalid_phrase(self):
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
            browser = launch(p.chromium)
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
