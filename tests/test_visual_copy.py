import tempfile
import unittest
from pathlib import Path

from PIL import Image

from economicissue.formatting import format_post, visual_text
from economicissue.render import draw_image, font_path, thumbnail_layout


class VisualCopyTests(unittest.TestCase):
    def test_remove_production_notes_preserves_figures_conditions_and_sources(self):
        text = ('보고서 수치를 재구성한 표입니다\n'
                '3억 원 · 30년 · 연 4% 가정\n'
                '월 143.2만 원 · 실제 적용 금리가 아님\n'
                '하나금융연구소 · 2026.10.26')
        self.assertEqual(visual_text(text),
                         '3억 원 · 30년 · 연 4% 가정\n'
                         '월 143.2만 원\n하나금융연구소 · 2026.10.26')
        self.assertEqual(visual_text('원문 기준 재구성한 표입니다.'), '')
        self.assertEqual(visual_text('자료 발췌 · 해설'), '')

    def test_manual_draft_uses_same_card_copy_rules(self):
        post = {'title': '대출 비교', 'thumbnail': '월 상환액 비교',
                'paragraphs': [{'text': '3억 원을 30년간 갚는다고 가정합니다.'}],
                'cards': [{'title': '월 상환액', 'text':
                           '3억 원 · 30년\n원문 기준 재구성한 표입니다'}]}
        formatted = format_post(post)
        self.assertEqual(formatted['cards'][0]['text'], '3억 원 · 30년')
        self.assertIn('가정합니다', formatted['paragraphs'][0]['text'])

    def test_large_thumbnail_type_keeps_complete_evidence_panel_clear(self):
        font, lines, step = thumbnail_layout('대출이 걱정돼\n집을 미룬다면', font_path())
        self.assertGreater(font.size, 80)
        self.assertLessEqual(len(lines), 3)
        self.assertLessEqual(max(150 + i * step + font.getbbox(line)[3]
                                 for i, line in enumerate(lines)), 450)
        with tempfile.TemporaryDirectory() as tmp:
            background = Path(tmp) / 'evidence.png'
            Image.new('RGB', (920, 470), '#00ff00').save(background)
            output = Path(tmp) / 'thumb.png'
            draw_image(output, '대출이 걱정돼\n집을 미룬다면', '', '', True, background)
            with Image.open(output) as im:
                self.assertEqual(im.size, (1080, 1080))
                self.assertEqual(im.getpixel((80, 490)), (0, 255, 0))
                self.assertEqual(im.getpixel((999, 959)), (0, 255, 0))


if __name__ == '__main__':
    unittest.main()
