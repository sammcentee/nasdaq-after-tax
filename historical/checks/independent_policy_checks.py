"""Independent causal and tax-accounting checks; synthetic, not market evidence."""
from pathlib import Path
import sys
import unittest

import pandas as pd

H = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(H / "model"))
from direct_stock_backtest import run_backtest
from test_direct_stock_backtest import config, fixture, weights


def membership(*rows):
    return pd.DataFrame(rows, columns=["effective_date", "available_date", "security_id", "is_member"])


class IndependentExitPolicyChecks(unittest.TestCase):
    def test_late_notice_cannot_sell_early_and_overrides_stale_fund_weight(self):
        days = ["2020-01-02", "2020-02-03", "2020-02-04", "2020-03-02"]
        p = fixture(days, {"A": [100, 200, 200, 200]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        m = membership(("2020-01-01", "2020-01-01", "A", True),
                       ("2020-02-01", "2020-02-03", "A", False))
        c = config(exit_policy="sell_all", exit_review_dates=tuple(days[1:3]))
        r = run_backtest(p, w, c, membership=m)
        sales = r.transactions.query("event=='sell' and reason=='policy_exit'")
        self.assertEqual(sales.date.tolist(), [pd.Timestamp("2020-02-04")])
        self.assertEqual(r.daily.iloc[1].holdings, {"A": 10})
        self.assertEqual(r.daily.iloc[2].holdings, {})

    def test_same_annual_exemption_cannot_be_reused_at_later_review(self):
        days = ["2020-01-02", "2020-02-03", "2020-04-01", "2020-05-01"]
        p = fixture(days, {"A": [100, 300, 300, 300], "B": [100, 300, 300, 300]})
        w = weights("2020-01-01", "2020-01-01", A=.5, B=.5)
        m = membership(("2020-01-01", "2020-01-01", "A", True),
                       ("2020-01-01", "2020-01-01", "B", True),
                       ("2020-02-01", "2020-02-01", "A", False),
                       ("2020-02-01", "2020-02-01", "B", False))
        c = config(end=days[-1], cgt_exemption=1270, exit_policy="tax_budget",
                   exit_review_dates=tuple(days[1:3]), liquidate_at_end=False)
        r = run_backtest(p, w, c, membership=m)
        sales = r.transactions.query("event=='sell' and reason=='policy_exit'")
        self.assertEqual(sales.security_id.tolist(), ["A"])
        self.assertEqual(r.daily.iloc[-1].holdings, {"B": 5})
        self.assertEqual(r.summary["exit_policy_positive_incremental_cgt_eur"], 0)

    def test_same_day_merger_termination_does_not_invent_outside_successor(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100, None, None], "B": [100, 100, 100]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        m = membership(("2020-01-01", "2020-01-01", "A", True),
                       ("2020-02-03", "2020-02-02", "A", False))
        e = pd.DataFrame([dict(date=days[1], security_id="A", event_type="stock_exchange",
                              successor_id="B", ratio=1, tax_treatment="rollover")])
        c = config(exit_policy="sell_all", exit_review_dates=(days[1],), liquidate_at_end=False)
        r = run_backtest(p, w, c, e, membership=m)
        self.assertEqual(r.daily.iloc[1].holdings, {"B": 10})
        self.assertEqual(r.daily.iloc[1].out_of_index_weight, 0)
        self.assertEqual(r.daily.iloc[1].unknown_membership_weight, 1)

    def test_partial_disposal_uses_oldest_lot_cost_not_average(self):
        days = ["2020-01-02", "2020-03-02", "2020-04-02", "2020-05-04"]
        p = fixture(days, {"A": [100, 200, 300, 300]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        m = membership(("2020-01-01", "2020-01-01", "A", True),
                       ("2020-04-01", "2020-04-01", "A", False))
        c = config(end=days[-1], contribution_dates=tuple(days[:2]),
                   exit_policy="gradual", exit_fraction=.25, exit_review_dates=(days[2],))
        r = run_backtest(p, w, c, membership=m)
        sales = r.transactions.query("event=='sell' and reason=='policy_exit'")
        self.assertEqual(len(sales), 1)
        self.assertAlmostEqual(sales.iloc[0].units, 3.75)
        self.assertAlmostEqual(sales.iloc[0].basis_eur, 375)
        self.assertAlmostEqual(sales.iloc[0].realized_gain_eur, 750)
        self.assertAlmostEqual(r.transactions.query("event=='lot_disposal'").basis_eur.sum(), 2000)

    def test_nontradable_forward_mark_cannot_trigger_policy_exit(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100, 200, 200]})
        p["tradable"] = [True, False, True]
        w = weights("2020-01-01", "2020-01-01", A=1)
        m = membership(("2020-01-01", "2020-01-01", "A", True),
                       ("2020-02-01", "2020-02-01", "A", False))
        c = config(exit_policy="sell_all", exit_review_dates=(days[1],))
        r = run_backtest(p, w, c, membership=m)
        self.assertEqual(r.summary["exit_policy_sales"], 0)
        self.assertEqual(r.summary["exit_policy_skips"]["no_fresh_tradable_quote"], 1)

    def test_reentry_cancels_known_departure_before_review(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02", "2020-04-01"]
        p = fixture(days, {"A": [100, 200, 200, 200]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        m = membership(("2020-01-01", "2020-01-01", "A", True),
                       ("2020-02-01", "2020-02-01", "A", False),
                       ("2020-02-28", "2020-02-28", "A", True))
        c = config(end=days[-1], exit_policy="sell_all", exit_review_dates=(days[2],))
        r = run_backtest(p, w, c, membership=m)
        self.assertEqual(r.summary["exit_policy_sales"], 0)
        self.assertEqual(r.daily.iloc[1].out_of_index_weight, 1)
        self.assertEqual(r.daily.iloc[2].out_of_index_weight, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
