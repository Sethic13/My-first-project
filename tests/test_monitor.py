import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import monitor


def ticket(event="10-26-26", price=2000):
    return {"productId": "monday-product", "productEventId": event,
            "name": "LineSkip (Mon)", "date": "2026-10-26T04:00:00.000Z",
            "pricePennies": price, "type": "LineSkip"}


def page(passes, venue=monitor.VENUE_ID):
    data = {"props": {"pageProps": {"venue": {"id": venue}, "passes": passes}}}
    return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(data) + '</script>'


class MonitorTests(unittest.TestCase):
    def test_fetch_reports_http_failure_without_logging_response(self):
        response = Mock(returncode=22, stdout="sensitive response\n403")
        with patch('monitor.subprocess.run', return_value=response):
            with self.assertRaisesRegex(ValueError, r"curl exit 22, HTTP 403") as error:
                monitor.fetch_passes()
        self.assertNotIn('sensitive response', str(error.exception))

    def test_fetch_parses_success_with_status_suffix(self):
        response = Mock(returncode=0, stdout=page([ticket()]) + '\n200')
        with patch('monitor.subprocess.run', return_value=response):
            self.assertEqual(len(monitor.fetch_passes()), 1)

    def test_email_test_does_not_fetch_lineleap(self):
        with patch('sys.argv', ['monitor.py', '--test-email']), \
                patch('monitor.fetch_passes') as fetch, \
                patch('monitor.send_alert') as send:
            monitor.main()
        fetch.assert_not_called()
        send.assert_called_once_with({}, test=True)

    def test_extracts_only_lineskip(self):
        parsed = monitor.parse_passes(page([ticket(), dict(ticket(), type="Cover")]))
        self.assertEqual(len(parsed), 1)
        self.assertEqual(next(iter(parsed.values()))["pricePennies"], 2000)

    def test_invalid_responses_fail(self):
        for html in ("Maintenance", page([], venue="wrong"), page(None),
                     page([dict(ticket(), pricePennies=None)])):
            with self.subTest(html=html), self.assertRaises(ValueError):
                monitor.parse_passes(html)

    def test_release_detection_and_price_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            notify = Mock()
            def run(items):
                monitor.check(path, fetch=lambda: monitor.parse_passes(page(items)), notify=notify)
            run([ticket()])
            notify.assert_not_called()
            run([ticket(price=3000)])
            notify.assert_not_called()
            run([ticket(), ticket(event="10-27-26")])
            self.assertEqual(notify.call_count, 1)
            self.assertEqual(len(notify.call_args.args[0]), 1)
            run([])
            run([ticket(), ticket(event="10-27-26")])
            self.assertEqual(notify.call_count, 1)

    def test_failed_email_is_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            monitor.check(path, fetch=lambda: {})
            before = path.read_text()
            fetch = lambda: monitor.parse_passes(page([ticket()]))
            with self.assertRaises(RuntimeError):
                monitor.check(path, fetch=fetch, notify=Mock(side_effect=RuntimeError("offline")))
            self.assertEqual(path.read_text(), before)
            notify = Mock()
            monitor.check(path, fetch=fetch, notify=notify)
            notify.assert_called_once()

    def test_dry_run_leaves_no_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            notify = Mock()
            monitor.check(path, dry_run=True, fetch=lambda: {}, notify=notify)
            self.assertFalse(path.exists())
            notify.assert_not_called()

    def test_corrupt_state_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text('{"version": 2}')
            with self.assertRaises(ValueError):
                monitor.load_state(path)


if __name__ == "__main__":
    unittest.main()
