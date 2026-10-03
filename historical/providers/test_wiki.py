"""Synthetic archive tests; no licensed market data fixtures."""
import csv
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from wiki import FIELDS, extract_archive


class WikiArchiveTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.archive = self.root / "source.zip"

    def tearDown(self):
        self.folder.cleanup()

    def write_archive(self, rows, fields=FIELDS):
        text = io.StringIO()
        writer = csv.DictWriter(text, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr("WIKI_PRICES.csv", text.getvalue())

    def row(self, symbol="TEST", day="2011-01-03"):
        values = {key: "1" for key in FIELDS}
        values.update(ticker=symbol, date=day, close="100", adj_close="25",
                      **{"ex-dividend": "0.25", "split_ratio": "4"})
        return values

    def test_preserves_raw_prices_dividends_and_split_ratios(self):
        self.write_archive([self.row()])
        result = extract_archive(self.archive, self.root / "out", ["TEST"], "2010-01-01", "2012-01-01")
        with (self.root / "out/TEST.csv").open() as stream:
            row = next(csv.DictReader(stream))
        self.assertEqual([row[k] for k in ["close", "adj_close", "ex-dividend", "split_ratio"]],
                         ["100", "25", "0.25", "4"])
        self.assertFalse(result["ready_for_study"])
        self.assertEqual(len(result["files"]["TEST.csv"]["sha256"]), 64)

    def test_filters_dates_and_symbols_without_hiding_source_bounds(self):
        self.write_archive([self.row(day="2009-01-02"), self.row(),
                            self.row(day="2018-03-01"), self.row(symbol="OTHER")])
        result = extract_archive(self.archive, self.root / "out", ["TEST", "MISSING"], "2010-01-01", "2012-01-01")
        self.assertEqual(result["archive_rows"], 4)
        self.assertEqual(result["bounds"]["TEST"],
                         {"source_rows": 3, "first": "2009-01-02", "last": "2018-03-01"})
        self.assertEqual(result["files"]["TEST.csv"]["rows"], 1)
        self.assertEqual(result["files"]["MISSING.csv"]["rows"], 0)
        self.assertFalse((self.root / "out/OTHER.csv").exists())

    def test_rejects_wrong_schema(self):
        self.write_archive([], fields=["date", "close"])
        with self.assertRaisesRegex(ValueError, "columns"):
            extract_archive(self.archive, self.root / "out", ["TEST"], "2010-01-01", "2012-01-01")

    def test_rejects_invalid_interval_and_output_symbols(self):
        for symbols, start, end in [(["TEST"], "2012-01-01", "2010-01-01"),
                                    (["../TEST"], "2010-01-01", "2012-01-01")]:
            with self.subTest(symbols=symbols, start=start):
                with self.assertRaises(ValueError):
                    extract_archive(self.archive, self.root / "out", symbols, start, end)


if __name__ == "__main__":
    unittest.main()
