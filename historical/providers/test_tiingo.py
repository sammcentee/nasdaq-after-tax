"""Synthetic-only tests: no Tiingo account, market data or network calls."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from tiingo import TiingoClient, TiingoError, main, normalize_daily


def row(day="2020-01-02", close=100, dividend=0, split=1, adjusted=49):
    return {"date": day + "T00:00:00.000Z", "close": close,
            "divCash": dividend, "splitFactor": split, "adjClose": adjusted}


class TiingoTests(unittest.TestCase):
    def test_raw_split_and_dividend_do_not_double_count_return(self):
        frame = normalize_daily([row("2020-01-03", 49, 1, 2), row()])
        self.assertEqual(list(frame.columns), ["date", "close", "dividend", "split"])
        self.assertEqual(frame.close.tolist(), [100, 49])
        units = frame.iloc[1].split
        closing_value_plus_dividend = units * (frame.iloc[1].close + frame.iloc[1].dividend)
        self.assertEqual(closing_value_plus_dividend, frame.iloc[0].close)
        self.assertEqual(frame.date.dt.strftime("%Y-%m-%d").tolist(), ["2020-01-02", "2020-01-03"])

    def test_rejects_incomplete_and_invalid_observations(self):
        incomplete = row()
        del incomplete["divCash"]
        for rows in ([incomplete], [row(), row()], [row(close=float("nan"))],
                     [row(split=0)], [row(dividend=-1)], [row(close=-1)]):
            with self.subTest(rows=rows), self.assertRaises(TiingoError):
                normalize_daily(rows)
        self.assertTrue(normalize_daily([]).empty)

    @patch("tiingo.requests.get")
    def test_token_only_in_authorization_header_and_raw_prices(self, get):
        get.return_value = Mock(status_code=200, json=lambda: [row()])
        with patch.dict(os.environ, {"TIINGO_API_KEY": "synthetic-private-token"}):
            frame = TiingoClient().daily("BRK-A", "2020-01-01", "2020-01-05")
        args, kwargs = get.call_args
        self.assertNotIn("synthetic-private-token", args[0])
        self.assertNotIn("synthetic-private-token", json.dumps(kwargs["params"]))
        self.assertEqual(kwargs["headers"]["Authorization"], "Token synthetic-private-token")
        self.assertEqual(frame.iloc[0].close, 100)

    @patch("tiingo.requests.get")
    def test_errors_never_include_response_body_or_token(self, get):
        get.return_value = Mock(status_code=403, text="synthetic-private-token")
        with self.assertRaises(TiingoError) as raised:
            TiingoClient("synthetic-private-token").metadata("AAA")
        self.assertIn("HTTP 403", str(raised.exception))
        self.assertNotIn("synthetic-private-token", str(raised.exception))
        get.return_value.json.assert_not_called()

    @patch("tiingo.requests.get")
    def test_invalid_symbol_and_dates_do_not_make_requests(self, get):
        client = TiingoClient("test-token")
        for symbol, start, end in [("AAA?token=secret", "2020-01-01", "2020-01-03"),
                                   ("AAA", "2020-01-03", "2020-01-01"),
                                   ("AAA", "invalid", "2020-01-01")]:
            with self.assertRaises(TiingoError):
                client.daily(symbol, start, end)
        get.assert_not_called()

    @patch("tiingo.requests.get")
    def test_out_of_requested_range_rejected(self, get):
        get.return_value = Mock(status_code=200, json=lambda: [row("2021-01-02")])
        with self.assertRaises(TiingoError):
            TiingoClient("test-token").daily("AAA", "2020-01-01", "2020-01-05")

    @patch("tiingo.requests.get")
    def test_missing_credentials_fail_without_network(self, get):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(TiingoError):
            TiingoClient()
        get.assert_not_called()

    @patch("tiingo.requests.get")
    def test_private_key_file_is_supported_without_printing_token(self, get):
        get.side_effect = [Mock(status_code=200, json=lambda: {}),
                           Mock(status_code=200, json=lambda: [])]
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.key"
            path.write_text("file-test-token\n", encoding="utf-8")
            with patch("sys.argv", ["tiingo.py", "--symbols", "AAA", "--start", "2020-01-01",
                                    "--end", "2020-01-05", "--key-file", str(path)]), redirect_stdout(output):
                self.assertEqual(main(), 0)
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Token file-test-token")
        self.assertNotIn("file-test-token", output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["symbols_without_prices"], 1)

    @patch("tiingo.requests.get")
    def test_missing_symbol_does_not_prevent_checking_remaining_symbols(self, get):
        get.side_effect = [Mock(status_code=404), Mock(status_code=200, json=lambda: {}),
                           Mock(status_code=200, json=lambda: [row()])]
        output = io.StringIO()
        with patch.dict(os.environ, {"TIINGO_API_KEY": "test-token"}), patch("sys.argv", [
                "tiingo.py", "--symbols", "MISSING", "AAA", "--start", "2020-01-01",
                "--end", "2020-01-05"]), redirect_stdout(output):
            self.assertEqual(main(), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["symbols_not_found"], 1)
        self.assertEqual(result["symbols_with_prices"], 1)

    @patch("tiingo.requests.get")
    def test_probe_only_emits_aggregate_counts_and_never_claims_identity(self, get):
        get.side_effect = [
            Mock(status_code=200, json=lambda: {"ticker": "AAA", "name": "Synthetic replacement issuer",
                                               "startDate": "2020-01-02", "endDate": "2020-01-03"}),
            Mock(status_code=200, json=lambda: [row()]),
        ]
        output = io.StringIO()
        with patch.dict(os.environ, {"TIINGO_API_KEY": "test-token"}), patch("sys.argv", [
                "tiingo.py", "--symbols", "AAA", "--start", "2010-09-01", "--end", "2020-01-05"]), redirect_stdout(output):
            self.assertEqual(main(), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["symbols_with_prices"], 1)
        self.assertEqual(result["metadata_starts_after_requested_start"], 1)
        self.assertEqual(result["issuer_identities_verified"], 0)
        self.assertFalse(result["ready_for_study"])
        for value in ["AAA", "Synthetic replacement issuer", "test-token", "100"]:
            self.assertNotIn(value, output.getvalue())


if __name__ == "__main__":
    unittest.main()
