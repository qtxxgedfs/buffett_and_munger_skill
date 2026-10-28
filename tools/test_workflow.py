import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path
import json
import os
import official_filings as filings
from task_log import timed
from pdf_ingest import parse_pages, extract_native


class WorkflowTests(unittest.TestCase):
    def row(self, title):
        return dict(code='601318', company='中国平安', title=title, disclosure_date='2026-08-21', pdf_url='https://example.test/a.pdf')

    def test_reports(self):
        self.assertEqual(filings.report_kind(self.row('中国平安2026年中期报告')), 'issuer_report')
        self.assertEqual(filings.report_kind(self.row('中国平安2026年中期报告摘要')), 'issuer_summary')
        self.assertEqual(filings.report_kind(self.row('中国平安：平安银行股份有限公司2026年半年度报告摘要')), 'forwarded_or_notice')
        self.assertEqual(filings.report_kind(self.row('中国平安关于披露平安银行2026年第一季度报告的公告')), 'forwarded_or_notice')
        self.assertEqual(filings.report_kind(self.row('某子公司2026年年度报告')), 'subject_unverified')

    def test_no_summary_match(self):
        row = self.row('中国平安2026年中期报告')
        backup = self.row('中国平安2026年中期报告摘要')
        filings.attach_alternates([row], [backup])
        self.assertNotIn('alternate_pdf_url', row)
        backup['title'] = row['title']
        filings.attach_alternates([row], [backup])
        self.assertIn('alternate_pdf_url', row)

    def test_html_fallback(self):
        from unittest.mock import Mock
        bad = Mock(content=b'<html>challenge</html>', status_code=200)
        good = Mock(content=b'%PDF-1.4 test', status_code=200)
        bad.raw.retries.history = good.raw.retries.history = ()
        session = Mock()
        session.get.side_effect = [bad, good]
        row = self.row('中国平安2026年中期报告')
        row['alternate_pdf_url'] = 'https://example.test/backup.pdf'
        with TemporaryDirectory() as tmp, patch.object(filings, 'new_session', return_value=session):
            filings.download_rows([row], Path(tmp))
            self.assertEqual(row['download_status'], '已下载')
            self.assertEqual(session.get.call_count, 2)
            self.assertEqual(len(row['download_attempts']), 1)

    def test_timing_failure(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'log.jsonl'
            with patch.dict(os.environ, {'INVEST_LOG': str(path)}):
                with self.assertRaises(ValueError):
                    with timed('failed'):
                        raise ValueError('test')
            events = [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()]
            self.assertEqual([x['event'] for x in events], ['start', 'end'])
            self.assertGreaterEqual(events[1]['elapsed_seconds'], 0)
            self.assertEqual(events[1]['details']['error'], 'test')

    def test_pages(self):
        self.assertEqual(parse_pages('1-3,2,5', 5), [0, 1, 2, 4])
        with self.assertRaises(ValueError):
            parse_pages('1-6', 5)


if __name__ == '__main__':
    unittest.main()
