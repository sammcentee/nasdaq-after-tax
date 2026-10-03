"""Independent economic and causal checks for annual tax optimization.

Small synthetic paths have deliberately known outcomes. These checks import
the production engine but not its tests, fixtures, or tax settlement function.
Run from the project with .venv/bin/python <this file>.
"""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

import pandas as pd

H = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(H / "model"))
from direct_stock_backtest import BacktestConfig, run_backtest


def prices(days, **series):
    return pd.DataFrame([
        dict(date=d, security_id=s, price_eur=p, dividend_eur=0.)
        for s, path in series.items() for d, p in zip(days, path, strict=True)
    ])


def targets(**weights):
    return pd.DataFrame([
        dict(effective_date="2018-01-01", available_date="2018-01-01",
             security_id=s, weight=w) for s, w in weights.items()
    ])


def config(days, **changes):
    base = BacktestConfig(
        start=days[0], end=days[-1], contribution_dates=(days[0],),
        monthly_contribution=10000., harvest=False, fx_fee=0., half_spread=0.,
        gain_harvest=True, gain_harvest_reinvest="same_security",
        gain_harvest_ranking="efficient", gain_review_dates=tuple(days[1:-1]),
    )
    return replace(base, **changes)


def sales(result, reason):
    t = result.transactions
    return t.loc[t.event.eq("sell") & t.reason.eq(reason)]


class IndependentTaxOptimizationChecks(unittest.TestCase):
    def test_repeated_reviews_do_not_reuse_exemption_and_flat_repurchase_saves_exact_tax(self):
        days = ["2020-01-02", "2020-11-02", "2020-12-02", "2021-01-04"]
        p, w = prices(days, A=[100, 200, 200, 200]), targets(A=1.)
        c = config(days)
        opt = run_backtest(p, w, c)
        old = run_backtest(p, w, replace(c, gain_harvest=False))
        gains = sales(opt, "gain_harvest")
        self.assertEqual(len(gains), 1)
        self.assertAlmostEqual(gains.realized_gain_eur.sum(), 1270.)
        self.assertAlmostEqual(opt.summary["final_cash"] - old.summary["final_cash"], 1270. * .33)
        y = opt.yearly_tax.set_index("year")
        self.assertAlmostEqual(y.loc[2020, "exemption_used"], 1270.)
        self.assertAlmostEqual(y.loc[2021, "exemption_used"], 1270.)

    def test_same_year_round_trip_has_no_permanent_terminal_tax_advantage(self):
        days = ["2020-01-02", "2020-11-02", "2020-12-31"]
        p, w = prices(days, A=[100, 200, 200]), targets(A=1.)
        c = config(days)
        opt = run_backtest(p, w, c)
        old = run_backtest(p, w, replace(c, gain_harvest=False))
        self.assertAlmostEqual(opt.summary["final_cash"], old.summary["final_cash"])
        self.assertAlmostEqual(opt.summary["total_cgt"], (10000.-1270.)*.33)

    def test_unused_exemption_is_not_carried_from_earlier_year(self):
        days = ["2019-01-02", "2019-12-02", "2020-12-02", "2021-01-04"]
        r = run_backtest(prices(days, A=[100, 100, 200, 200]), targets(A=1.), config(days))
        gain_sales = sales(r, "gain_harvest")
        self.assertEqual(gain_sales.date.tolist(), [pd.Timestamp("2020-12-02")])
        self.assertAlmostEqual(gain_sales.realized_gain_eur.sum(), 1270.)
        self.assertAlmostEqual(r.yearly_tax.set_index("year").loc[2019, "exemption_used"], 0.)

    def test_current_losses_are_used_before_exemption(self):
        days = ["2020-01-02", "2020-12-02", "2021-01-04"]
        c = config(days, monthly_contribution=20000., harvest=True,
                   harvest_review_dates=(days[1],), harvest_loss_fraction=0.,
                   harvest_min_loss_eur=1.)
        r = run_backtest(prices(days, A=[100, 200, 200], B=[100, 80, 80]),
                         targets(A=.5, B=.5), c)
        y = r.yearly_tax.set_index("year").loc[2020]
        self.assertAlmostEqual(y.losses_eur, 2000.)
        self.assertAlmostEqual(y.gains_eur, 3270.)
        self.assertAlmostEqual(y.exemption_used, 1270.)
        self.assertAlmostEqual(y.tax_due, 0.)

    def test_carried_losses_must_also_be_realized_through_before_exemption(self):
        days = ["2020-01-02", "2020-12-02", "2021-01-04", "2021-12-02", "2022-01-03"]
        c = config(days, monthly_contribution=20000., harvest=True,
                   harvest_review_dates=(days[1],), harvest_loss_fraction=0.,
                   harvest_min_loss_eur=1., gain_review_dates=(days[3],))
        r = run_backtest(prices(days, A=[100, 100, 100, 200, 200], B=[100, 80, 80, 80, 80]),
                         targets(A=.5, B=.5), c)
        y = r.yearly_tax.set_index("year")
        self.assertAlmostEqual(y.loc[2020, "loss_carry_forward"], 2000.)
        self.assertAlmostEqual(y.loc[2021, "gains_eur"], 3270.)
        self.assertAlmostEqual(y.loc[2021, "brought_forward_loss_eur"], 2000.)
        self.assertAlmostEqual(y.loc[2021, "exemption_used"], 1270.)
        self.assertAlmostEqual(y.loc[2021, "loss_carry_forward"], 0.)

    def test_later_loss_is_not_anticipated_and_can_erase_earlier_exemption_use(self):
        days = ["2020-01-02", "2020-11-02", "2020-12-02", "2021-01-04"]
        c = config(days, monthly_contribution=20000., harvest=True,
                   harvest_review_dates=(days[2],), harvest_loss_fraction=0.,
                   harvest_min_loss_eur=1., gain_review_dates=(days[1],))
        r = run_backtest(prices(days, A=[100, 200, 200, 200], B=[100, 100, 80, 80]),
                         targets(A=.5, B=.5), c)
        self.assertAlmostEqual(sales(r, "gain_harvest").realized_gain_eur.sum(), 1270.)
        y = r.yearly_tax.set_index("year").loc[2020]
        self.assertAlmostEqual(y.exemption_used, 0.)
        self.assertAlmostEqual(y.loss_carry_forward, 730.)

    def test_fees_reduce_final_cash_and_are_not_reported_as_tax_alpha(self):
        days = ["2020-01-02", "2020-11-02", "2020-12-31"]
        p, w = prices(days, A=[100, 200, 200]), targets(A=1.)
        c = config(days, fx_fee=.0015)
        opt = run_backtest(p, w, c)
        old = run_backtest(p, w, replace(c, gain_harvest=False))
        self.assertGreater(opt.summary["transaction_costs"], old.summary["transaction_costs"])
        self.assertLess(opt.summary["final_cash"], old.summary["final_cash"])
        extra_cost = opt.summary["transaction_costs"] - old.summary["transaction_costs"]
        self.assertAlmostEqual(old.summary["final_cash"] - opt.summary["final_cash"], extra_cost*(1-.33))

    def test_loss_cost_hurdle_can_reject_tiny_deferral_and_preserves_review_dates(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-03", "2021-01-04"]
        p, w = prices(days, A=[100, 99, 99, 99]), targets(A=1.)
        c = config(days, gain_harvest=False, harvest=True, fx_fee=.0015,
                   harvest_review_dates=(days[1],), harvest_loss_fraction=0.,
                   harvest_min_loss_eur=1., harvest_cost_multiple=0.)
        loose = run_backtest(p, w, c)
        strict = run_backtest(p, w, replace(c, harvest_cost_multiple=2.))
        self.assertEqual(sales(loose, "harvest").date.tolist(), [pd.Timestamp(days[1])])
        self.assertTrue(sales(strict, "harvest").empty)

    def test_conservative_reentry_blocks_same_class_for_29_days(self):
        days = ["2020-01-02", "2020-11-02", "2020-11-20", "2020-12-01", "2021-01-04"]
        c = config(days, gain_harvest_reinvest="underweights", gain_review_dates=(days[1],),
                   investment_frequency="daily")
        r = run_backtest(prices(days, A=[100, 200, 200, 200, 200]), targets(A=1.), c)
        purchases = r.transactions.loc[r.transactions.event.eq("buy"), "date"].tolist()
        self.assertEqual(purchases, [pd.Timestamp(days[0]), pd.Timestamp(days[3])])

    def test_immediate_repurchase_stops_before_a_losing_fifo_lot(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-03", "2021-01-04"]
        c = config(days, monthly_contribution=1000., contribution_dates=tuple(days[:2]),
                   gain_review_dates=(days[2],))
        r = run_backtest(prices(days, A=[100, 200, 150, 150]), targets(A=1.), c)
        gain_sales = sales(r, "gain_harvest")
        self.assertEqual(len(gain_sales), 1)
        self.assertAlmostEqual(gain_sales.iloc[0].units, 10.)
        self.assertAlmostEqual(gain_sales.iloc[0].realized_gain_eur, 500.)
        matched = r.transactions.loc[r.transactions.event.eq("lot_disposal") & r.transactions.reason.eq("gain_harvest")]
        self.assertEqual(len(matched), 1)
        self.assertAlmostEqual(matched.iloc[0].basis_eur, 1000.)
        replacements = r.transactions.loc[r.transactions.event.eq("buy") & r.transactions.reason.eq("gain_repurchase")]
        self.assertAlmostEqual(replacements.iloc[0].units, 10.)

    def test_whole_share_rounding_cannot_exceed_annual_headroom(self):
        days = ["2020-01-02", "2020-11-02", "2020-12-02", "2021-01-04"]
        c = config(days, fractional_shares=False)
        r = run_backtest(prices(days, A=[100, 200, 200, 200]), targets(A=1.), c)
        gain_sales = sales(r, "gain_harvest")
        self.assertAlmostEqual(gain_sales.units.sum(), 12.)
        self.assertAlmostEqual(gain_sales.realized_gain_eur.sum(), 1200.)
        self.assertAlmostEqual(r.yearly_tax.set_index("year").loc[2020, "exemption_used"], 1200.)

    def test_loss_prefix_is_eligible_despite_profitable_whole_position(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-03", "2021-01-04"]
        c = config(days, monthly_contribution=1000., contribution_dates=tuple(days[:2]),
                   gain_harvest=False, harvest=True, harvest_lot_mode="fifo_prefix",
                   harvest_review_dates=(days[2],), harvest_loss_fraction=.05,
                   harvest_min_loss_eur=25.)
        # Old basis 1000 -> 950; new basis 1000 -> 1900. Whole holding gains 850.
        p, w = prices(days, A=[100, 50, 95, 95]), targets(A=1.)
        prefix = run_backtest(p, w, c)
        whole = run_backtest(p, w, replace(c, harvest_lot_mode="position"))
        self.assertTrue(sales(whole, "harvest").empty)
        loss_sales = sales(prefix, "harvest")
        self.assertEqual(len(loss_sales), 1)
        self.assertAlmostEqual(loss_sales.iloc[0].units, 10.)
        self.assertAlmostEqual(loss_sales.iloc[0].basis_eur, 1000.)
        self.assertAlmostEqual(loss_sales.iloc[0].realized_gain_eur, -50.)

    def test_profitable_oldest_lot_prevents_cherry_picking_a_later_loss(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-03", "2021-01-04"]
        c = config(days, monthly_contribution=1000., contribution_dates=tuple(days[:2]),
                   gain_harvest=False, harvest=True, harvest_lot_mode="fifo_prefix",
                   harvest_review_dates=(days[2],), harvest_loss_fraction=0.,
                   harvest_min_loss_eur=1.)
        # Old shares gain 1000; younger shares lose 500. They cannot be picked.
        r = run_backtest(prices(days, A=[50, 200, 100, 100]), targets(A=1.), c)
        self.assertTrue(sales(r, "harvest").empty)

    def test_hybrid_replaces_current_gain_shares_but_does_not_repurchase_departures(self):
        days = ["2020-01-02", "2020-12-02", "2021-01-04"]
        c = config(days, monthly_contribution=2000., gain_harvest_reinvest="hybrid",
                   gain_harvest_ranking="overweight")
        m = pd.DataFrame([dict(effective_date="2020-11-01", available_date="2020-10-31",
                               security_id="B", is_member=False)])
        r = run_backtest(prices(days, A=[100, 200, 200], B=[100, 150, 150]),
                         targets(A=.5, B=.5), c, membership=m)
        gain_sales = sales(r, "gain_harvest")
        self.assertEqual(gain_sales.security_id.tolist(), ["B", "A"])
        self.assertAlmostEqual(gain_sales.realized_gain_eur.sum(), 1270.)
        replacements = r.transactions.loc[r.transactions.event.eq("buy") & r.transactions.reason.eq("gain_repurchase")]
        self.assertEqual(replacements.security_id.tolist(), ["A"])
        self.assertEqual(r.daily.iloc[1].holdings, {"A": 10.})

    def test_combined_mode_preserves_whole_loss_and_adds_eligible_prefix_loss(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-03", "2021-01-04"]
        c = config(days, monthly_contribution=1000., contribution_dates=tuple(days[:2]),
                   gain_harvest=False, harvest=True, harvest_lot_mode="position_or_fifo_prefix",
                   harvest_review_dates=(days[2],), harvest_loss_fraction=.05,
                   harvest_min_loss_eur=25.)
        # Oldest lot wins but total holding loses: preserve full-position sale.
        whole_loss = run_backtest(prices(days, A=[50, 200, 60, 60]), targets(A=1.), c)
        self.assertAlmostEqual(sales(whole_loss, "harvest").iloc[0].units, 25.)
        self.assertAlmostEqual(sales(whole_loss, "harvest").iloc[0].realized_gain_eur, -500.)
        # Total holding wins but old prefix loses: the additional rule applies.
        prefix_loss = run_backtest(prices(days, A=[100, 50, 95, 95]), targets(A=1.), c)
        self.assertAlmostEqual(sales(prefix_loss, "harvest").iloc[0].units, 10.)
        self.assertAlmostEqual(sales(prefix_loss, "harvest").iloc[0].realized_gain_eur, -50.)


if __name__ == "__main__":
    unittest.main(verbosity=2)
