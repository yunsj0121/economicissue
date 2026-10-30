import copy
import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from economicissue.cli import finish, main
from economicissue.formatting import format_post
from economicissue.quality import check_publication, publication_text
from economicissue.topics import choose, make_choices, recent
from economicissue.writer import validate
from economicissue.browser import assert_content, content_hash, inspect_page, launch
from economicissue.render import draw_image
from test_pipeline import fixture


def publication_fixture():
    post, sources = fixture()
    post['hashtags'] = ['#생활비' + str(i) for i in range(20)]
    post['paragraphs'] = [
        {'kind': 'fact', 'source_ids': ['s1'], 'text': '가계 지출은 같은 금액이어도 가구 구성과 주거 조건에 따라 부담이 달라집니다. 저축을 줄이기 전에 고정비와 비정기 지출을 함께 확인하는 것이 좋아요.'},
        {'kind': 'opinion', 'source_ids': [], 'text': '이번 달 지출만으로 평소 생활을 판단하기는 어려워요. 일 년 동안 드는 비용을 월별로 나누면 비교하기 편합니다.'},
        {'kind': 'opinion', 'source_ids': [], 'text': '가족과 함께 쓰는 돈은 목적과 분담 기준을 먼저 정해보세요. 소득 차이가 있다면 같은 금액보다 각자의 부담을 함께 살펴볼 수 있죠.'},
        {'kind': 'opinion', 'source_ids': [], 'text': '남는 돈의 사용 시기도 중요합니다. 가까운 시일에 필요한 돈과 오래 보관할 수 있는 돈을 구분해 보세요.'}]
    post['cards'] = [
        {'visual': 'table', 'title': '지출을 나누는 기준', 'text': '실제 통계가 아닌 지출 점검 기준입니다', 'source_ids': ['s1'], 'after': 1,
         'columns': ['항목', '확인할 내용'], 'rows': [['고정비', '매달 반복되는지'], ['비정기 지출', '언제 필요한지']]},
        {'visual': 'explanation', 'title': '가족과 합의할 것', 'text': '공동 지출의 목적과 분담 기준을 함께 정해요', 'source_ids': ['s1'], 'after': 3}]
    sources[0]['text'] = '지출은 고정비와 비정기 지출로 나누어 확인합니다. 공동 지출의 목적과 분담 기준을 정합니다. 10 20'
    policy = {'image_count': 3, 'duplicate_days': 45, 'capture': False, 'hashtag_count': 20,
              'blank_line_between_sentences': True, 'spread_images': True, 'mixed_visuals': True,
              'minimum_data_images': 1}
    return post, sources, policy


class PublicationTests(unittest.TestCase):
    def test_spacing_tags_count_and_failed_length(self):
        post, sources, policy = publication_fixture()
        post = format_post(post, policy)
        text = publication_text(post)
        policy['length'] = {'min': len(text), 'max': len(text), 'target': len(text)}
        self.assertIn('달라집니다\n\n저축', text)
        self.assertEqual(check_publication(post, policy)['characters_with_spaces'], len(text))
        validate(post, sources, 3, policy)
        broken = copy.deepcopy(post); broken['hashtags'][1] = broken['hashtags'][0]
        with self.assertRaisesRegex(ValueError, '해시태그'):
            validate(broken, sources, 3, policy)
        policy['length']['min'] = len(text) + 1
        with self.assertRaisesRegex(ValueError, '자로 수정'):
            validate(post, sources, 3, policy)
        self.assertEqual(format_post(post, policy), post)

    def test_evidence_and_table_numbers_must_exist(self):
        post, sources, _ = publication_fixture()
        post['cards'][0].update(columns=['항목', '금액'], rows=[['생활비', '10'], ['저축', '20']])
        validate(post, sources, 3)
        post['cards'][0]['rows'][0][1] = '100'
        with self.assertRaisesRegex(ValueError, '원문'):
            validate(post, sources, 3)
        post['cards'][0].update(visual='evidence', capture_id='invented')
        with self.assertRaisesRegex(ValueError, '캡처 영역'):
            validate(post, sources, 3)
        sources[0]['capture_candidates'] = [{'id': 'actual'}]
        post['cards'][0]['capture_id'] = 'actual'
        validate(post, sources, 3)

    def test_bundle_has_tags_last_preview_and_selection_lock(self):
        post, sources, policy = publication_fixture()
        old = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                selection = {'title': post['title'], 'topic_key': post['topic_key']}
                brief = {'sources': sources, 'selection': selection}
                wrong = copy.deepcopy(post); wrong['title'] = '다른 제목'
                with self.assertRaisesRegex(ValueError, '선택한'):
                    finish({'post': wrong}, brief, policy, [])
                finish({'post': post}, brief, policy, [])
                folder = next(Path('output').iterdir())
                text = (folder / 'post.txt').read_text()
                self.assertEqual(text.splitlines()[-1], ' '.join(post['hashtags']))
                self.assertIn('자료 출처', text)
                preview = (folder / 'preview.html').read_text()
                self.assertLess(preview.index('자료 출처'), preview.index('#생활비0'))
                self.assertEqual(json.loads((folder / 'review.json').read_text())['hashtag_count'], 20)
                review = json.loads((folder / 'image_review.json').read_text())
                self.assertEqual([s['type'] for s in review], ['text_layout', 'table', 'explanation'])
            finally:
                os.chdir(old)

    def test_material_changes_and_stale_choices_are_rejected(self):
        now = datetime.now(timezone.utc)
        source = {'id': 'r1', 'url': 'https://example.com/a', 'title': '생활비 사연', 'text': '원문',
                  'published': (now - timedelta(days=1)).isoformat(), 'date_verified': True}
        research = {'sources': [source]}
        choices = [{'title': f'생활비 선택 {i}', 'angle': '비교 관점', 'root_source_id': 'r1', 'source_ids': ['r1']} for i in range(10)]
        policy = {'title_candidate_count': 10, 'max_age_days': 7, 'source_limit': 4}
        with patch('economicissue.topics.complete', return_value={'post': {'candidates': choices}}):
            bundle = make_choices(research, policy, '.cache')
        selected, _ = choose(bundle, research, 3, policy)
        self.assertEqual(selected['title'], '생활비 선택 2')
        self.assertEqual(bundle['candidates'][0]['topic_key'], selected['topic_key'])
        altered = copy.deepcopy(research); altered['sources'][0]['text'] = '바뀐 내용'
        with self.assertRaisesRegex(ValueError, '묶음이 다릅니다'):
            choose(bundle, altered, 3, policy)
        self.assertFalse(recent({**source, 'date_verified': False}, 7, now))
        self.assertFalse(recent({**source, 'published': (now - timedelta(days=8)).isoformat()}, 7, now))
        self.assertFalse(recent({**source, 'published': (now + timedelta(days=1)).isoformat()}, 7, now))

    def test_draft_never_generates_without_selection(self):
        with patch('sys.argv', ['economicissue', 'draft']), patch('economicissue.cli.generate') as generate:
            with self.assertRaises(SystemExit):
                main()
            generate.assert_not_called()

    def test_thumbnail_keeps_edges_of_evidence(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            background = Path(tmp) / 'evidence.png'
            evidence = Image.new('RGB', (800, 200), 'white')
            for x in range(50):
                for y in range(200):
                    evidence.putpixel((x, y), (255, 0, 0)); evidence.putpixel((799-x, y), (0, 0, 255))
            evidence.save(background)
            output = Path(tmp) / 'thumb.png'
            draw_image(output, '생활비\n어디서 늘었나', '', '설명용 테스트', True, background)
            with Image.open(output) as im:
                self.assertEqual(im.size, (1080, 1080))
                colors = set(im.getdata())
                self.assertIn((255, 0, 0), colors); self.assertIn((0, 0, 255), colors)

    def test_block_screens_are_not_evidence(self):
        for text in ['로그인이 필요합니다 ' * 100, '삭제된 게시물입니다 ' * 100, 'Access denied ' * 100]:
            with self.assertRaises(ValueError):
                assert_content(text)
        self.assertEqual(content_hash('핵심  내용\n입니다'), content_hash('핵심 내용 입니다'))

    def test_browser_reads_dynamic_article_and_actual_selectors(self):
        from playwright.sync_api import sync_playwright
        article = '<article id="story"><p>' + '가족 생활비를 함께 확인하고 저축 목표를 비교합니다. ' * 15 + '</p><p>' + '공동 지출의 목적과 분담을 정합니다. ' * 4 + '</p></article>'
        markup = '<meta property="article:published_time" content="2026-10-29T10:00:00+09:00"><h1>가계 지출</h1><main id="root"></main><script>document.querySelector("main").innerHTML=' + json.dumps(article) + '</script>'
        from economicissue.browser import guarded_context
        def fixture_context(browser, allowed):
            context = browser.new_context()
            context.route('https://example.com/**', lambda route: route.fulfill(body=markup, content_type='text/html; charset=utf-8'))
            return context
        with patch('economicissue.browser.guarded_context', fixture_context), patch('economicissue.sources.public_url'):
            data = inspect_page('https://example.com/article', {}, lambda url: True)
        self.assertTrue(data['browser_verified'])
        self.assertIn('가족 생활비', data['text'])
        self.assertEqual(data['published'], '2026-10-29T10:00:00+09:00')
        self.assertTrue(data['capture_candidates'])
        self.assertTrue(data['capture_candidates'][0]['selector'].startswith('#story'))


class FullDefaultPolicyTests(unittest.TestCase):
    def test_default_policy_bundle_and_portable_preview(self):
        from PIL import Image
        policy = json.loads(Path('policy.json').read_text())
        post = json.loads(Path('tests/fixtures/publication.json').read_text())
        source = {'id': 's1', 'title': '기능 검증용 가상 가계 점검 자료',
                  'url': 'https://example.com/test-fixture', 'hash': 'fixture', 'text': '실제 통계가 아닌 검증용 가상 예시입니다'}
        old = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                finish({'post': post}, {'sources': [source]}, policy, [])
                folder = next(Path('output').iterdir())
                manifest = json.loads((folder / 'manifest.json').read_text())
                self.assertEqual(len(manifest['images']), 5)
                review = json.loads((folder / 'review.json').read_text())
                self.assertTrue(1400 <= review['characters_with_spaces'] <= 1600)
                self.assertEqual(review['hashtag_count'], 20)
                with Image.open(folder / '01_thumbnail.png') as im:
                    self.assertEqual(im.size, (1080, 1080))
                page = (folder / 'preview.html').read_text()
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    browser = launch(p.chromium)
                    tab = browser.new_page(viewport={'width': 390, 'height': 844})
                    tab.route('https://example.com/preview', lambda route: route.fulfill(body=page, content_type='text/html; charset=utf-8'))
                    tab.goto('https://example.com/preview')
                    self.assertEqual(tab.locator('img').count(), 5)
                    self.assertLessEqual(tab.evaluate('document.documentElement.scrollWidth'), 390)
                    self.assertTrue(tab.locator('p').last.inner_text().startswith('#생활비'))
                    browser.close()
            finally:
                os.chdir(old)

    def test_real_capture_and_changed_content_rejection(self):
        from economicissue.render import capture_source
        from PIL import Image
        text = '가족 생활비를 함께 확인하고 저축 목표를 비교합니다. ' * 12
        markup = '<article style="width:650px;font:24px sans-serif"><p id="excerpt">' + text + '</p><p>' + '자료를 확인하는 단계입니다. ' * 20 + '</p></article>'
        def fixture_context(browser, allowed):
            context = browser.new_context(viewport={'width': 1000, 'height': 900})
            context.route('https://example.com/**', lambda route: route.fulfill(body=markup, content_type='text/html; charset=utf-8'))
            return context
        spec = {'card': 2, 'selector': '#excerpt', 'rights': '테스트용 자체 작성 자료',
                'text_hash': content_hash(text), 'highlights': ['가족 생활비를 함께 확인하고 저축 목표를 비교합니다. ' * 12]}
        with tempfile.TemporaryDirectory() as tmp, patch('economicissue.browser.guarded_context', fixture_context), \
             patch('economicissue.sources.Collector.allowed', return_value=True), patch('economicissue.sources.public_url'), \
             patch('economicissue.render.public_url'):
            path = Path(tmp) / 'capture.png'
            capture_source(spec, {'url': 'https://example.com/article'}, path)
            with Image.open(path) as im:
                self.assertTrue(any(p == (227, 38, 54) for p in im.convert('RGB').getdata()))
            with self.assertRaisesRegex(ValueError, '원문이 변경'):
                capture_source({**spec, 'text_hash': 'stale'}, {'url': 'https://example.com/article'}, path)


if __name__ == '__main__':
    unittest.main()
