import copy
import unittest
from economicissue.writer import validate
from test_pipeline import fixture


class HashtagTests(unittest.TestCase):
    def test_rejects_missing_wrong_count_duplicates_and_malformed_tags(self):
        post, sources = fixture()
        valid = post['hashtags']
        validate(post, sources, 3)
        invalid = [None, valid[:19], valid + ['#추가'], valid[:19] + [valid[0]],
                   valid[:19] + ['태그'], valid[:19] + ['#공백 태그'],
                   valid[:19] + ['#태그!'], valid[:19] + [42],
                   ['#ETF', '#etf'] + valid[:18]]
        for tags in invalid:
            with self.subTest(tags=tags):
                broken = copy.deepcopy(post)
                if tags is None:
                    broken.pop('hashtags')
                else:
                    broken['hashtags'] = tags
                with self.assertRaisesRegex(ValueError, '해시태그'):
                    validate(broken, sources, 3)


if __name__ == '__main__':
    unittest.main()
