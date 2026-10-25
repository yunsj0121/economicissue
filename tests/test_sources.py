import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from economicissue.direct import balanced, date_iso, discover_direct, kosis_data, parse_feed, parse_listing
from economicissue.sources import Collector, discover


class SourceTests(unittest.TestCase):
    def test_hana_js_links_dates_and_duplicates(self):
        markup = '''<ul><li><a href="javascript:goPage('/boardDetail.do?hmpeSeqNo=7&amp;menuId=MN1000', '');">
        <p class="tit ellips02">���� �ҵ�� ����</p></a><div class="date">2026-10-20</div>
        <a href="/boardDetail.do?hmpeSeqNo=7&amp;menuId=MN1000"></a></li></ul>'''
        source = {"id": "hana", "kind": "report", "url": "https://www.hanaif.re.kr/boardList.do",
                  "detail_pattern": r"/boardDetail\.do\?hmpeSeqNo="}
        rows = parse_listing(markup, source)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "���� �ҵ�� ����")
        self.assertTrue(rows[0]["published"].startswith("2026-10-20"))
        self.assertIn("hmpeSeqNo=7&menuId=MN1000", rows[0]["url"])

    def test_kb_real_href_and_title(self):
        source = {"id": "kb", "kind": "report", "url": "https://www.kbfg.com/kbresearch/report/reportList.do",
                  "detail_pattern": r"/reportView\.do\?reportId="}
        rows = parse_listing('<li><a href="reportView.do?reportId=3">�ҵ� ������</a>2026-10-19</li>', source)
        self.assertEqual(rows[0]["url"], "https://www.kbfg.com/kbresearch/report/reportView.do?reportId=3")

    def test_rss_http_upgrade_cdata_and_real_dates(self):
        source = {"id": "kosis", "kind": "statistics", "url": "https://kosis.kr/rss/themes_rss.jsp"}
        feed = b'''<rss><channel><item><title>Income</title><link>http://kosis.kr/view?id=1</link>
        <description><![CDATA[<p>Source details</p>]]></description>
        <pubDate>Mon, 19 Oct 2026 19:46:14 +0900</pubDate></item></channel></rss>'''
        row = parse_feed(feed, source)[0]
        self.assertEqual(row["url"], "https://kosis.kr/view?id=1")
        self.assertIn("Source details", row["summary"])
        self.assertTrue(row["published"].startswith("2026-10-19"))

    def test_failed_provider_is_isolated_and_visible(self):
        class Fake:
            policy = {"direct_sources": [
                {"id": "fail", "url": "https://fail.test", "kind": "report", "format": "rss"},
                {"id": "ok", "url": "https://ok.test", "kind": "report", "format": "rss"}]}
            def fetch_public(self, url):
                if "fail" in url:
                    raise OSError("offline")
                return b'<rss><channel><item><title>Income</title><link>https://ok.test/report</link></item></channel></rss>', url
        rows, statuses = discover_direct(Fake())
        self.assertEqual(len(rows), 1)
        self.assertEqual([s["status"] for s in statuses], ["failed", "ok"])

    def test_balanced_selection_includes_official_sources(self):
        rows = [{"provider": "blind", "score": 99} for _ in range(10)] + [{"provider": "hana", "score": 1}]
        self.assertEqual([r["provider"] for r in balanced(rows, 3, 6)], ["blind", "hana", "blind"])

    def test_direct_discovery_needs_no_naver_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = json.loads(Path("policy.json").read_text(encoding="utf-8"))
            collector = Collector(policy, tmp)
            rows = [{"url": "https://example.com/report", "title": "��Ȱ�� ����", "provider": "hana", "kind": "report"}]
            with patch("economicissue.direct.discover_direct", return_value=(rows, [])), \
                 patch.object(collector, "search", side_effect=AssertionError("Naver must not be called")):
                found, errors = discover(collector)
            self.assertEqual(len(found), 1)
            self.assertFalse(errors)

    def test_kosis_key_not_returned_with_records(self):
        def fetch(url):
            self.assertIn("apiKey=secret", url)
            return b'[{"PRD_DE":"2025","DT":"10","UNIT_NM":"percent"}]', url
        records = kosis_data({"userStatsId": "issued/id", "prdSe": "Y", "newEstPrdCnt": 1}, "secret", fetch)
        self.assertNotIn("secret", json.dumps(records))
        self.assertEqual(date_iso("not a date"), "")

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "dependency installed in CI")
    def test_pdf_extraction_includes_page_reference(self):
        from pypdf import PdfWriter
        from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
        writer = PdfWriter()
        page = writer.add_blank_page(width=600, height=800)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(("BT /F1 12 Tf 50 700 Td (" + "Sample income report. " * 30 + ") Tj ET").encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
        buffer = io.BytesIO()
        writer.write(buffer)
        with tempfile.TemporaryDirectory() as tmp:
            text, pages = Collector({}, tmp).pdf_text(buffer.getvalue())
        self.assertIn("[PDF p.1]", text)
        self.assertEqual(pages, 1)


if __name__ == "__main__":
    unittest.main()
