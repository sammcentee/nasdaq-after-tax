"""Contribution timing and purchasing-power checks against official CPI inputs."""
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contributions import INFLATION_FILE, _load_cpi, build_cpi_schedule


class CpiContributionTests(unittest.TestCase):
    def setUp(self):
        self.dates = pd.date_range("2010-09-30", periods=192, freq="BME")

    def test_study_amounts_and_anniversary_months(self):
        schedule = build_cpi_schedule(self.dates)
        self.assertEqual(len(schedule), 192)
        self.assertEqual(schedule.date.iloc[-1], pd.Timestamp("2026-08-31"))
        self.assertEqual(schedule.contribution_eur.iloc[0], 1000)
        self.assertEqual(schedule.contribution_eur.iloc[-1], 1301.28)
        for _, group in schedule.groupby("review_date"):
            self.assertEqual(len(group), 12)
            self.assertEqual(group.contribution_eur.nunique(), 1)
        review = schedule[schedule.date == "2012-09-28"].iloc[0]
        self.assertEqual(review.review_date, pd.Timestamp("2012-09-28"))
        self.assertEqual(review.reference_month, "2012-08")
        self.assertTrue((schedule.cpi_published_date < schedule.review_date).all())

    def test_deflation_reduces_payments_and_unrounded_base_avoids_drift(self):
        schedule = build_cpi_schedule(self.dates)
        amounts = schedule.groupby("reference_month").contribution_eur.first()
        self.assertLess(amounts["2016-08"], amounts["2015-08"])
        self.assertLess(amounts["2020-08"], amounts["2019-08"])
        cpi = _load_cpi()
        for row in cpi.itertuples():
            expected = (Decimal("1000") * Decimal(str(row.cpi_index)) / Decimal("101.9"))
            expected = expected.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            self.assertEqual(amounts[row.reference_month], float(expected))

    def test_future_cpi_cannot_change_earlier_contributions(self):
        original = build_cpi_schedule(self.dates)
        changed = _load_cpi()
        changed.loc[changed.reference_month == "2025-08", "cpi_index"] *= 10
        with patch("contributions._load_cpi", return_value=changed):
            result = build_cpi_schedule(self.dates)
        pd.testing.assert_frame_equal(original.iloc[:180], result.iloc[:180])
        self.assertNotEqual(original.contribution_eur.iloc[-1], result.contribution_eur.iloc[-1])

    def test_cpi_on_or_after_review_is_rejected(self):
        for release in ("2011-09-30", "2011-10-01"):
            changed = _load_cpi()
            changed.loc[changed.reference_month == "2011-08", "cpi_published_date"] = pd.Timestamp(release)
            with self.subTest(release=release), patch("contributions._load_cpi", return_value=changed):
                with self.assertRaisesRegex(ValueError, "not published before review"):
                    build_cpi_schedule(self.dates)

    def test_missing_year_and_nonmonthly_dates_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "No archived August CPI"):
            build_cpi_schedule(pd.date_range("2010-09-30", periods=193, freq="BME"))
        with self.assertRaisesRegex(ValueError, "consecutive months"):
            build_cpi_schedule(self.dates.delete(3))

    def test_cpi_inputs_match_recorded_hashes_and_api_selection(self):
        folder = INFLATION_FILE.parent
        provenance = json.loads((folder / "provenance.json").read_text())
        for file_key, hash_key in (("csv_file", "csv_sha256"), ("api_snapshot_file", "api_snapshot_sha256")):
            self.assertEqual(hashlib.sha256((folder / provenance[file_key]).read_bytes()).hexdigest(), provenance[hash_key])
        api = json.loads((folder / provenance["api_snapshot_file"]).read_text())
        months = api["dimension"]["TLIST(M1)"]["category"]["index"]
        bases = api["dimension"]["C02071V02502"]["category"]["index"]
        for row in _load_cpi().itertuples():
            offset = months.index(row.reference_month.replace("-", "")) * len(bases) + bases.index("010")
            self.assertEqual(row.cpi_index, api["value"][offset])


if __name__ == "__main__":
    unittest.main()
