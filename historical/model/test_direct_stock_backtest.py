"""Synthetic fixtures only: these tests are not an actual Nasdaq-100 replay."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from direct_stock_backtest import (BacktestConfig, DataIntegrityError,
                                   compare_harvesting, run_backtest,
                                   scheduled_contributions)


def fixture(dates, paths, dividends=None):
    return pd.DataFrame([
        dict(date=day, security_id=security, price_eur=path[i],
             dividend_eur=(dividends or {}).get((day, security), 0.0))
        for security, path in paths.items() for i, day in enumerate(dates)
    ])


def weights(effective, available, **targets):
    return pd.DataFrame([dict(effective_date=effective, available_date=available,
                              security_id=s, weight=w) for s, w in targets.items()])


def config(start="2020-01-02", end="2020-03-02", **overrides):
    defaults = dict(start=start, end=end, contribution_dates=(start,),
                    fx_fee=0.0, half_spread=0.0, cgt_exemption=0.0,
                    harvest=False)
    defaults.update(overrides)
    return BacktestConfig(**defaults)


class DirectStockBacktestTests(unittest.TestCase):
    def test_default_schedule_is_192_monthly_deposits(self):
        dates = scheduled_contributions(BacktestConfig())
        self.assertEqual(len(dates), 192)
        self.assertEqual(dates[0], pd.Timestamp("2010-09-30"))
        self.assertEqual(dates[-1], pd.Timestamp("2026-08-31"))

    def test_variable_contributions_post_each_due_amount_on_next_session(self):
        days = ["2020-01-31", "2020-02-03", "2020-03-02", "2020-04-01"]
        scheduled = (days[0], "2020-02-01", "2020-02-02", "2020-02-29", "2020-03-31")
        amounts = (1000.0, 550.0, 550.0, 900.0, 0.0)
        p = fixture(days, {"A": [100, 110, 90, 120]})
        w = weights("2020-01-30", "2020-01-30", A=1)
        c = config(days[0], days[-1], contribution_dates=tuple(reversed(scheduled)),
                   contribution_amounts=amounts)
        r = run_backtest(p, w, c)
        deposits = r.transactions.query("event == 'contribution'")
        self.assertEqual(deposits.cash_eur.tolist(), list(amounts))
        self.assertEqual(deposits.scheduled_date.tolist(), list(pd.to_datetime(scheduled)))
        self.assertEqual(deposits.date.tolist(), list(pd.to_datetime(
            [days[0], days[1], days[1], days[2], days[3]])))
        self.assertEqual(r.daily.contributions_eur.tolist(), [1000, 2100, 3000, 3000])
        self.assertEqual(r.transactions.query("event == 'buy'").units.tolist(), [10, 10, 10])
        self.assertEqual(r.summary["contribution_count"], 5)
        self.assertEqual(r.summary["contributions"], 3000)
        self.assertAlmostEqual(r.summary["total_cgt"], 600 * .33)
        self.assertAlmostEqual(r.summary["final_cash"], 3600 - 600 * .33)

    def test_future_contribution_cannot_change_prefix_or_replace_zero_amount(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02", "2020-04-01"]
        p = fixture(days, {"A": [100, 110, 90, 120]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        c = config(days[0], days[-1], contribution_dates=tuple(days[:3]),
                   contribution_amounts=(0.0, 1100.0, 900.0))
        original = run_backtest(p, w, c)
        changed = run_backtest(p, w, replace(c, contribution_amounts=(0.0, 1100.0, 90000.0)))
        self.assertEqual(original.daily.iloc[0].contributions_eur, 0)
        self.assertEqual(original.daily.iloc[0].holdings, {})
        for name in ("transactions", "daily"):
            first, second = getattr(original, name), getattr(changed, name)
            pd.testing.assert_frame_equal(first[first.date < days[2]].reset_index(drop=True),
                                          second[second.date < days[2]].reset_index(drop=True))

    def test_constant_contribution_tuple_matches_existing_default(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100, 110, 120]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        c = config(contribution_dates=tuple(days[:2]))
        original = run_backtest(p, w, c)
        explicit = run_backtest(p, w, replace(c, contribution_amounts=(1000.0, 1000.0)))
        self.assertEqual(original.summary, explicit.summary)
        for name in ("transactions", "daily", "yearly_tax", "lots"):
            pd.testing.assert_frame_equal(getattr(original, name), getattr(explicit, name))

    def test_invalid_contribution_amounts_fail_before_replay(self):
        days = ["2020-01-02", "2020-03-02"]
        p = fixture(days, {"A": [100, 100]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        for amounts in ((), (1000.0, 1000.0), (-1.0,), (float("nan"),),
                        (float("inf"),), (float("-inf"),)):
            with self.subTest(amounts=amounts), self.assertRaises(ValueError):
                run_backtest(p, w, config(contribution_amounts=amounts))

    def test_winners_retained_after_deletion_and_new_cash_buys_current_member(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100, 200, 250], "B": [100, 100, 100]})
        w = pd.concat([weights("2020-01-01", "2020-01-01", A=1),
                       weights("2020-02-01", "2020-02-02", B=1)])
        r = run_backtest(p, w, config(harvest=True, contribution_dates=tuple(days[:-1])))
        sells = r.transactions.query("event == 'sell'")
        self.assertTrue((sells.reason == "final_liquidation").all())
        buys = r.transactions.query("event == 'buy'")
        self.assertEqual(buys.security_id.tolist(), ["A", "B"])
        self.assertEqual(r.daily.iloc[1].holdings["A"], 10)
        self.assertAlmostEqual(r.summary["final_cash"], 3500-1500*.33)

    def test_same_day_weights_cannot_influence_trade(self):
        days = ["2020-01-02", "2020-01-03", "2020-03-02"]
        p = fixture(days, {"A": [100]*3, "B": [100]*3})
        w = pd.concat([weights("2020-01-01", "2020-01-01", A=1),
                       weights("2020-01-02", "2020-01-02", B=1)])
        r = run_backtest(p, w, config(contribution_dates=tuple(days[:2])))
        buys = r.transactions.query("event == 'buy'")
        self.assertEqual(buys.security_id.tolist(), ["A", "B"])
        self.assertTrue((buys.weight_available_date < buys.date).all())

    def test_no_initial_known_weights_fails(self):
        p = fixture(["2020-01-02", "2020-03-02"], {"A": [100, 100]})
        with self.assertRaisesRegex(DataIntegrityError, "previously available"):
            run_backtest(p, weights("2020-01-02", "2020-01-02", A=1), config())

    def test_future_price_shock_and_future_weights_preserve_prefix(self):
        days = ["2020-01-02", "2020-01-30", "2020-01-31", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100, 96, 90, 89, 95], "B": [100, 105, 110, 115, 120]})
        w = weights("2020-01-01", "2020-01-01", A=.5, B=.5)
        c = config(harvest=True, harvest_frequency="daily", liquidate_at_end=False)
        original = run_backtest(p, w, c)
        shocked = p.copy()
        shocked.loc[shocked.date > "2020-01-31", "price_eur"] *= 100
        future_w = pd.concat([w, weights("2020-01-20", "2020-02-02", A=1)])
        other = run_backtest(shocked, future_w, c)
        truncated = run_backtest(p[p.date <= "2020-01-31"], w, c)
        for result in (other, truncated):
            for name in ("transactions", "daily"):
                first = getattr(original, name)
                second = getattr(result, name)
                pd.testing.assert_frame_equal(
                    first[first.date <= "2020-01-31"].reset_index(drop=True),
                    second[second.date <= "2020-01-31"].reset_index(drop=True),
                    check_dtype=False)

    def test_harvest_threshold_and_29_day_prior_purchase_rule(self):
        days = ["2020-01-02", "2020-01-30", "2020-01-31", "2020-03-02"]
        p = fixture(days, {"A": [100, 80, 80, 80], "B": [100]*4})
        w = weights("2020-01-01", "2020-01-01", A=.5, B=.5)
        r = run_backtest(p, w, config(harvest=True, harvest_frequency="daily"))
        sales = r.transactions.query("event == 'sell' and reason == 'harvest'")
        self.assertEqual(len(sales), 1)
        self.assertEqual(sales.iloc[0].date, pd.Timestamp("2020-01-31"))
        self.assertEqual(sales.iloc[0].realized_gain_eur, -100)
        # Sale proceeds remain actual proceeds: no immediate €33 loss rebate.
        self.assertEqual(r.daily.iloc[2].value_eur, 900)
        self.assertEqual(r.daily.iloc[2].cgt_paid_eur, 0)

    def test_same_legal_class_alias_observes_post_sale_blackout(self):
        days = ["2020-01-02", "2020-01-31", "2020-02-28", "2020-02-29", "2020-03-02"]
        p = fixture(days, {"A": [100, 80, 80, 80, 80], "AA": [80]*5})
        w = pd.concat([weights("2020-01-01", "2020-01-01", A=1),
                       weights("2020-02-01", "2020-02-01", AA=1)])
        m = pd.DataFrame([dict(security_id=s, share_class="LEGAL_A") for s in ("A", "AA")])
        r = run_backtest(p, w, config(harvest=True, harvest_frequency="daily", investment_frequency="daily"), metadata=m)
        buys = r.transactions.query("event == 'buy'")
        self.assertEqual(buys.security_id.tolist(), ["A", "AA"])
        self.assertEqual(buys.iloc[1].date, pd.Timestamp("2020-02-29"))

    def test_small_loss_below_either_threshold_is_not_harvested(self):
        p = fixture(["2020-01-02", "2020-02-03", "2020-03-02"], {"A": [100, 98, 110]})
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1),
                         config(harvest=True, harvest_frequency="daily"))
        self.assertEqual(r.transactions.query("event == 'sell'").reason.tolist(), ["final_liquidation"])

    def test_harvest_sells_entire_aggregate_loss_position_including_all_lots(self):
        days = ["2020-01-02", "2020-03-02", "2020-04-02", "2020-05-04"]
        p = fixture(days, {"A": [100, 200, 120, 180]})
        c = config(end=days[-1], contribution_dates=tuple(days[:2]),
                   harvest=True, harvest_frequency="daily")
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), c)
        sell = r.transactions.query("event == 'sell' and reason == 'harvest'").iloc[0]
        self.assertEqual(sell.units, 15)
        self.assertEqual(sell.basis_eur, 2000)
        self.assertEqual(sell.realized_gain_eur, -200)
        details = r.transactions.query("event == 'lot_disposal' and reason == 'harvest'")
        self.assertEqual(details.realized_gain_eur.tolist(), [200, -400])
        self.assertAlmostEqual(r.summary["unutilized_loss"], 200)

    def test_overlapping_alias_ids_cannot_bypass_same_class_lot_identification(self):
        p = fixture(["2020-01-02", "2020-03-02"], {"A": [100]*2, "AA": [100]*2})
        w = weights("2020-01-01", "2020-01-01", A=.5, AA=.5)
        m = pd.DataFrame([dict(security_id=s, share_class="LEGAL_A") for s in ("A", "AA")])
        with self.assertRaisesRegex(DataIntegrityError, "Overlapping security IDs"):
            run_backtest(p, w, config(), metadata=m)

    def test_dividend_withholding_credited_once_and_reinvestment_has_basis(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100]*3}, {(days[1], "A"): 10.0})
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), config(investment_frequency="daily"))
        dividend = r.transactions.query("event == 'dividend'").iloc[0]
        self.assertAlmostEqual(dividend.gross_eur, 100)
        self.assertAlmostEqual(dividend.withholding_eur, 15)
        self.assertAlmostEqual(dividend.irish_top_up_eur, 37.35)
        self.assertAlmostEqual(r.summary["total_dividend_tax"], 52.35)
        self.assertAlmostEqual(r.summary["final_cash"], 1047.65)
        self.assertAlmostEqual(r.summary["total_cgt"], 0)
        self.assertAlmostEqual(r.transactions.query("event == 'buy'").basis_eur.sum(), 1047.65)

    def test_two_sided_fx_fees_and_basis_assumption_sensitivity(self):
        p = fixture(["2020-01-02", "2020-03-02"], {"A": [100, 200]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        c = config(fx_fee=.0015)
        r = run_backtest(p, w, c)
        proceeds = 1000/1.0015*2*.9985
        self.assertAlmostEqual(r.summary["final_cash"], proceeds-(proceeds-1000)*.33)
        self.assertAlmostEqual(r.transactions.query("event == 'buy'").iloc[0].basis_eur, 1000)
        sensitivity = run_backtest(p, w, replace(c, acquisition_costs_in_basis=False))
        self.assertGreater(sensitivity.summary["total_cgt"], r.summary["total_cgt"])

    def test_default_dividends_wait_for_monthly_investment(self):
        days = ["2020-01-02", "2020-01-15", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100]*4}, {(days[1], "A"): 10})
        c = config(contribution_dates=(days[0], days[2]))
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), c)
        self.assertEqual(r.transactions.query("event == 'buy'").date.tolist(),
                         [pd.Timestamp(days[0]), pd.Timestamp(days[2])])
        self.assertAlmostEqual(r.daily.iloc[1].cash_eur, 47.65)
        self.assertAlmostEqual(r.transactions.query("event == 'buy'").iloc[1].cash_outlay_eur, 1047.65)

    def test_minimum_order_retains_small_dividends_as_cash(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100]*3}, {(days[1], "A"): .1})
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1),
                         config(investment_frequency="daily"))
        self.assertEqual(len(r.transactions.query("event == 'buy'")), 1)
        self.assertAlmostEqual(r.daily.iloc[1].cash_eur, .4765)

    def test_membership_deletion_stops_new_buys_without_causing_sale(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100, 110, 120], "B": [100]*3})
        w = weights("2020-01-01", "2020-01-01", A=.5, B=.5)
        m = pd.DataFrame([dict(effective_date="2020-02-01", security_id="A", is_member=False),
                          dict(effective_date="2020-02-01", security_id="UNWEIGHTED_NEW_MEMBER", is_member=True)])
        r = run_backtest(p, w, config(contribution_dates=tuple(days[:2])), membership=m)
        later_buys = r.transactions[(r.transactions.event == "buy") &
                                   (r.transactions.date == pd.Timestamp("2020-02-03"))]
        self.assertEqual(later_buys.security_id.tolist(), ["B"])
        self.assertEqual(r.daily.iloc[1].holdings["A"], 5)
        self.assertTrue((r.transactions.query("event == 'sell'").reason == "final_liquidation").all())
        self.assertGreater(r.daily.iloc[1].cash_eur, 0)

    def test_integer_shares_leave_cash_and_pay_costs(self):
        p = fixture(["2020-01-02", "2020-03-02"], {"A": [300, 300]})
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1),
                         config(fractional_shares=False, fx_fee=.0015))
        self.assertEqual(r.transactions.query("event == 'buy'").iloc[0].units, 3)
        self.assertAlmostEqual(r.summary["final_cash"], 997.3)

    def test_loss_bank_used_before_annual_exemption(self):
        days = ["2019-12-02", "2020-01-03", "2020-12-31", "2021-01-04"]
        p = fixture(days, {"A": [100, 80, None, None], "B": [80, 80, 80, 103]})
        w = pd.concat([weights("2019-12-01", "2019-12-01", A=1),
                       weights("2020-01-02", "2020-01-02", B=1)])
        e = pd.DataFrame([dict(date="2020-01-03", security_id="A", event_type="cash_merger", cash_eur_per_share=80)])
        r = run_backtest(p, w, config(days[0], days[-1], monthly_contribution=10000, cgt_exemption=1270), e)
        final = r.yearly_tax.iloc[-1]
        self.assertAlmostEqual(final.gains_eur, 2300)
        self.assertAlmostEqual(final.losses_used, 2000)
        self.assertAlmostEqual(final.exemption_used, 300)
        self.assertAlmostEqual(final.loss_carry_forward, 0)
        self.assertAlmostEqual(r.summary["final_cash"], 10300)

    def test_cash_merger_reserves_tax_without_selling_winners(self):
        days = ["2020-01-02", "2020-02-03", "2021-01-04"]
        p = fixture(days, {"A": [100, None, None], "B": [100, 100, 100]})
        w = pd.concat([weights("2020-01-01", "2020-01-01", A=1),
                       weights("2020-02-01", "2020-02-02", B=1)])
        e = pd.DataFrame([dict(date="2020-02-03", security_id="A", event_type="cash_merger", cash_eur_per_share=200)])
        r = run_backtest(p, w, config(end=days[-1]), e)
        self.assertAlmostEqual(r.daily.iloc[1].cash_eur, 330)
        self.assertAlmostEqual(r.daily.iloc[1].cgt_reserve_eur, 330)
        self.assertAlmostEqual(r.summary["final_cash"], 1670)
        self.assertEqual(r.transactions.query("event == 'sell'").reason.tolist(), ["cash_merger", "final_liquidation"])

    def test_split_preserves_basis(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100, 50, 60]})
        e = pd.DataFrame([dict(date=days[1], security_id="A", event_type="split", ratio=2)])
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), config(), e)
        self.assertEqual(r.daily.iloc[1].holdings["A"], 20)
        self.assertAlmostEqual(r.summary["final_cash"], 1200-200*.33)
        self.assertIn("split", r.transactions.query("event == 'lot_disposal'").iloc[0].lineage)

    def test_stock_exchange_requires_explicit_rollover(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100, None, None], "B": [200, 200, 250]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        e = pd.DataFrame([dict(date=days[1], security_id="A", event_type="stock_exchange", ratio=.5, successor_id="B")])
        with self.assertRaisesRegex(DataIntegrityError, "rollover"):
            run_backtest(p, w, config(), e)
        e["tax_treatment"] = "rollover"
        r = run_backtest(p, w, config(), e)
        self.assertEqual(r.daily.iloc[1].holdings, {"B": 5})
        self.assertAlmostEqual(r.summary["final_cash"], 1250-250*.33)

    def test_spinoff_retained_with_explicit_basis_allocation(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100, 80, 90], "B": [20, 20, 30]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        e = pd.DataFrame([dict(date=days[1], security_id="A", event_type="spinoff", ratio=1,
                              successor_id="B", basis_fraction=.2, tax_treatment="rollover")])
        r = run_backtest(p, w, config(), e)
        self.assertEqual(r.daily.iloc[1].holdings, {"A": 10, "B": 10})
        self.assertAlmostEqual(r.transactions.query("event == 'sell'").basis_eur.sum(), 1000)
        self.assertAlmostEqual(r.summary["final_cash"], 1200-200*.33)

    def test_missing_delisting_price_hard_fails_instead_of_fabricating_sale(self):
        days = pd.bdate_range("2020-01-02", periods=9).strftime("%Y-%m-%d").tolist()
        p = fixture(days, {"A": [100]+[None]*8, "B": [100]*9})
        with self.assertRaisesRegex(DataIntegrityError, "Missing/stale held price"):
            run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), config(end=days[-1]))

    def test_final_liquidation_cannot_use_stale_quote(self):
        p = fixture(["2020-01-02", "2020-03-02"], {"A": [100, None], "B": [100, 100]})
        with self.assertRaisesRegex(DataIntegrityError, "Fresh final"):
            run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), config())

    def test_unresolved_mixed_merger_hard_fails(self):
        p = fixture(["2020-01-02", "2020-03-02"], {"A": [100, 100]})
        e = pd.DataFrame([dict(date="2020-03-02", security_id="A", event_type="mixed_cash_stock_cvr")])
        with self.assertRaisesRegex(DataIntegrityError, "unsupported action"):
            run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), config(), e)

    def test_mixed_merger_cash_part_disposal_and_rollover_conserve_basis(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100, None, None], "B": [100, 100, 150]})
        e = pd.DataFrame([dict(date=days[1], security_id="A", event_type="mixed_merger",
                              cash_eur_per_share=50, successor_id="B", ratio=1,
                              stock_value_eur_per_old_share=100, tax_treatment="rollover")])
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1),
                         config(reinvest_after_disposal=False), e)
        self.assertEqual(r.daily.iloc[1].holdings, {"B": 10})
        partial = r.transactions.query("event=='lot_disposal' and reason=='mixed_merger'")
        self.assertAlmostEqual(partial.basis_eur.sum(), 1000/3)
        final = r.transactions.query("event=='lot_disposal' and reason=='final_liquidation'")
        self.assertAlmostEqual(final.basis_eur.sum(), 2000/3)
        self.assertAlmostEqual(r.summary['total_cgt'], 330)
        self.assertAlmostEqual(r.summary['final_cash'], 1670)

    def test_explicit_missing_weight_stays_cash_without_renormalization(self):
        p = fixture(["2020-01-02", "2020-03-02"], {"A": [100, 200]})
        w = weights("2020-01-01", "2020-01-01", A=.75, __CASH__=.25)
        r = run_backtest(p, w, config())
        self.assertAlmostEqual(r.daily.iloc[0].cash_eur, 250)
        self.assertAlmostEqual(r.daily.iloc[0].holdings['A'], 7.5)
        self.assertAlmostEqual(r.summary['final_cash'], 1750-750*.33)

    def test_missing_target_policy_reserves_cash_and_keeps_held_gap_checks(self):
        p = fixture(["2020-01-02", "2020-03-02"], {"A": [100, 200]})
        w = weights("2020-01-01", "2020-01-01", A=.5, B=.5)
        r = run_backtest(p, w, config(missing_target_policy="reserve_cash"))
        self.assertAlmostEqual(r.daily.iloc[0].cash_eur, 500)
        self.assertAlmostEqual(r.summary['final_cash'], 1500-500*.33)

    def test_cash_dividend_before_same_day_merger_is_not_lost(self):
        p = fixture(["2020-01-02", "2020-03-02"], {"A": [100, 100]})
        e = pd.DataFrame([
            dict(date="2020-03-02", security_id="A", event_type="cash_dividend", cash_eur_per_share=10),
            dict(date="2020-03-02", security_id="A", event_type="cash_merger", cash_eur_per_share=100)])
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), config(), e)
        self.assertAlmostEqual(r.summary['final_cash'], 1047.65)
        self.assertAlmostEqual(r.summary['total_dividend_tax'], 52.35)

    def test_contingent_right_survives_parent_merger_and_taxed_when_paid(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100, 100, 100]})
        e = pd.DataFrame([
            dict(date=days[1], security_id="A", event_type="contingent_right", successor_id="RIGHT", ratio=1),
            dict(date=days[1], security_id="A", event_type="cash_merger", cash_eur_per_share=100),
            dict(date=days[2], security_id="RIGHT", event_type="contingent_cash", cash_eur_per_share=10)])
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1),
                         config(reinvest_after_disposal=False), e)
        self.assertAlmostEqual(r.summary["final_cash"], 1067)
        self.assertAlmostEqual(r.summary["total_cgt"], 33)
        self.assertEqual(r.summary["unpaid_contingent_right_units"], {})

    def test_nontradable_valuation_cannot_support_harvesting(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100, 50, 110]})
        p["tradable"] = [True, False, True]
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1),
                         config(harvest_frequency="daily"))
        self.assertEqual(len(r.transactions.query("event=='sell' and reason=='harvest'")), 0)
        self.assertAlmostEqual(r.summary["final_cash"], 1067)
        p.loc[p.date.eq(days[-1]), "tradable"] = False
        with self.assertRaisesRegex(DataIntegrityError, "Fresh final"):
            run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), config())

    def test_economic_harvest_comparison_includes_final_tax_and_exposure_changes(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100, 80, 200], "B": [100]*3})
        w = weights("2020-01-01", "2020-01-01", A=.5, B=.5)
        result = compare_harvesting(p, w, config(harvest_frequency="daily"))
        self.assertAlmostEqual(result["baseline"].summary["final_cash"], 1335)
        self.assertAlmostEqual(result["harvested"].summary["final_cash"], 900)
        self.assertAlmostEqual(result["incremental_after_tax_eur"], -435)
        self.assertAlmostEqual(result["harvested"].summary["unutilized_loss"], 100)
        self.assertTrue(result["harvested"].daily.iloc[-1].holdings == {})


class DepartedHoldingPolicyTests(unittest.TestCase):
    @staticmethod
    def deleted(day, *securities, available=None):
        rows = [dict(effective_date=day, security_id=s, is_member=False) for s in securities]
        if available is not None:
            for row in rows:
                row["available_date"] = available
        return pd.DataFrame(rows)

    def test_gradual_exit_uses_partial_fifo_and_preserves_unsold_basis(self):
        days = ["2020-01-02", "2020-01-31", "2020-03-02", "2020-04-02"]
        p = fixture(days, {"A": [100, 200, 150, 150]})
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1),
                         config(end=days[-1], contribution_dates=tuple(days[:2]),
                                exit_policy="gradual", exit_fraction=.8,
                                exit_review_dates=(days[2],), liquidate_at_end=False,
                                reinvest_after_disposal=False),
                         membership=self.deleted("2020-02-01", "A"))
        sale = r.transactions.query("event=='sell' and reason=='policy_exit'").iloc[0]
        self.assertAlmostEqual(sale.units, 12)
        self.assertAlmostEqual(sale.basis_eur, 1400)
        self.assertAlmostEqual(sale.realized_gain_eur, 400)
        details = r.transactions.query("event=='lot_disposal' and reason=='policy_exit'")
        self.assertEqual(details.units.tolist(), [10, 2])
        self.assertAlmostEqual(r.lots.basis_eur.sum(), 600)
        self.assertEqual(r.daily.iloc[-1].holdings, {"A": 3})

    def test_zero_tax_budget_sells_loss_before_gain_using_only_known_losses(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100, 80, 80], "B": [100, 120, 120]})
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=.5, B=.5),
                         config(exit_policy="tax_budget", exit_review_dates=(days[1],),
                                liquidate_at_end=False, reinvest_after_disposal=False),
                         membership=self.deleted("2020-02-01", "A", "B"))
        sales = r.transactions.query("event=='sell' and reason=='policy_exit'")
        self.assertEqual(sales.security_id.tolist(), ["A", "B"])
        self.assertAlmostEqual(r.summary["exit_policy_positive_incremental_cgt_eur"], 0)
        self.assertAlmostEqual(r.summary["final_value"], 1000)

    def test_zero_tax_budget_does_not_reuse_annual_exemption_at_later_review(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02", "2020-04-02"]
        p = fixture(days, {"A": [100, 120, 120, 120], "B": [100, 120, 120, 120]})
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=.5, B=.5),
                         config(end=days[-1], monthly_contribution=2000, cgt_exemption=250,
                                exit_policy="tax_budget", exit_review_dates=tuple(days[1:3]),
                                liquidate_at_end=False, reinvest_after_disposal=False),
                         membership=self.deleted("2020-02-01", "A", "B"))
        sales = r.transactions.query("event=='sell' and reason=='policy_exit'")
        self.assertEqual(sales.security_id.tolist(), ["A"])
        self.assertEqual(r.summary["exit_policy_skips"]["annual_tax_budget"], 2)

    def test_tax_budget_has_no_later_loss_refund_and_resets_next_year(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02", "2021-01-04", "2021-02-01"]
        p = fixture(days, {"A": [100, 110, 110, 110, 110],
                           "B": [100, 110, 110, 110, 110], "C": [100, 100, 90, 90, 90]})
        m = pd.concat([self.deleted("2020-02-01", "A", "B"), self.deleted("2020-03-01", "C")])
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1/3, B=1/3, C=1/3),
                         config(end=days[-1], monthly_contribution=3000,
                                exit_policy="tax_budget", exit_annual_tax_budget_eur=33,
                                exit_review_dates=tuple(days[1:4]), liquidate_at_end=False,
                                reinvest_after_disposal=False), membership=m)
        sales = r.transactions.query("event=='sell' and reason=='policy_exit'")
        self.assertEqual(sales.security_id.tolist(), ["A", "C", "B"])
        self.assertEqual(sales.date.tolist(), list(pd.to_datetime(days[1:4])))
        self.assertAlmostEqual(r.summary["exit_policy_positive_incremental_cgt_eur"], 66)
        self.assertAlmostEqual(r.summary["exit_policy_current_year_budget_used_eur"], 33)

    def test_grace_age_starts_when_known_and_reentry_resets_it(self):
        days = ["2020-01-02", "2020-02-03", "2020-02-10", "2020-02-17", "2020-02-24", "2020-03-02", "2020-04-02"]
        p = fixture(days, {"A": [100]*len(days)})
        m = pd.DataFrame([
            dict(effective_date="2020-02-01", security_id="A", is_member=False),
            dict(effective_date="2020-02-08", security_id="A", is_member=True),
            dict(effective_date="2020-02-15", security_id="A", is_member=False)])
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1),
                         config(end=days[-1], exit_policy="sell_all", exit_grace_days=10,
                                exit_review_dates=tuple(days[1:-1]), liquidate_at_end=False,
                                reinvest_after_disposal=False), membership=m)
        sale = r.transactions.query("event=='policy_exit'").iloc[0]
        self.assertEqual(sale.date, pd.Timestamp("2020-03-02"))
        self.assertEqual(sale.outside_since, pd.Timestamp("2020-02-17"))
        self.assertEqual(sale.outside_age_days, 14)

    def test_future_membership_and_same_day_publication_do_not_trigger_exit(self):
        days = ["2020-01-02", "2020-02-03", "2020-02-04", "2020-03-02"]
        p = fixture(days, {"A": [100]*4})
        m = self.deleted("2020-01-03", "A", available="2020-02-03")
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1),
                         config(exit_policy="sell_all", exit_review_dates=tuple(days[1:3])), membership=m)
        sale = r.transactions.query("event=='policy_exit'").iloc[0]
        self.assertEqual(sale.date, pd.Timestamp("2020-02-04"))
        self.assertEqual(r.daily.iloc[1].out_of_index_value_eur, 0)
        altered = pd.concat([m, pd.DataFrame([dict(effective_date="2020-02-05", available_date="2020-02-05", security_id="A", is_member=True)])])
        other = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1),
                            config(exit_policy="sell_all", exit_review_dates=tuple(days[1:3])), membership=altered)
        for field_name in ("transactions", "daily"):
            a, b = getattr(r, field_name), getattr(other, field_name)
            pd.testing.assert_frame_equal(a[a.date <= days[2]], b[b.date <= days[2]])

    def test_announced_holiday_review_executes_next_session_without_contribution(self):
        days = ["2020-01-02", "2020-01-31", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100]*4})
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1),
                         config(exit_policy="sell_all", exit_review_dates=("2020-02-01",)),
                         membership=self.deleted("2020-01-31", "A"))
        sale = r.transactions.query("event=='policy_exit'").iloc[0]
        self.assertEqual(sale.date, pd.Timestamp("2020-02-03"))
        self.assertEqual(sale.scheduled_date, pd.Timestamp("2020-02-01"))
        self.assertEqual(r.summary["contribution_count"], 1)

    def test_loss_only_removes_small_loser_but_retains_winner(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100, 99, 99], "B": [100, 101, 101]})
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=.5, B=.5),
                         config(harvest=True, exit_policy="loss_only", exit_review_dates=(days[1],),
                                liquidate_at_end=False, reinvest_after_disposal=False),
                         membership=self.deleted("2020-02-01", "A", "B"))
        self.assertEqual(r.transactions.query("event=='sell'").security_id.tolist(), ["A"])
        self.assertEqual(r.daily.iloc[-1].holdings, {"B": 5})

    def test_policy_respects_recent_purchase_and_nontradable_price(self):
        days = ["2020-01-02", "2020-01-30", "2020-01-31", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100]*5})
        p["tradable"] = [True, True, False, True, True]
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1),
                         config(exit_policy="sell_all", exit_review_dates=tuple(days[1:-1])),
                         membership=self.deleted("2020-01-29", "A"))
        self.assertEqual(r.transactions.query("event=='policy_exit'").date.tolist(), [pd.Timestamp("2020-02-03")])
        self.assertEqual(r.summary["exit_policy_skips"], {"recent_class_purchase": 1, "no_fresh_tradable_quote": 1})

    def test_unknown_action_child_is_retained_and_separately_measured(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02", "2020-04-02"]
        p = fixture(days, {"A": [100, 80, 80, 80], "B": [20]*4})
        e = pd.DataFrame([dict(date=days[1], security_id="A", event_type="spinoff",
                              successor_id="B", ratio=1, basis_fraction=.2, tax_treatment="rollover")])
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1),
                         config(end=days[-1], exit_policy="sell_all", exit_review_dates=(days[2],),
                                liquidate_at_end=False), events=e)
        self.assertEqual(r.summary["exit_policy_sales"], 0)
        self.assertAlmostEqual(r.daily.iloc[2].unknown_membership_value_eur, 200)
        self.assertAlmostEqual(r.daily.iloc[2].unknown_membership_weight, .2)
        self.assertAlmostEqual(r.daily.iloc[2].out_of_index_value_eur, 0)

    def test_stock_successor_inherits_prior_outside_status_but_same_day_deletion_does_not(self):
        days = ["2020-01-02", "2020-02-03", "2020-02-04", "2020-03-02"]
        p = fixture(days, {"A": [100]*4, "B": [100]*4})
        e = pd.DataFrame([dict(date=days[2], security_id="A", event_type="stock_exchange",
                              successor_id="B", ratio=1, tax_treatment="rollover")])
        c = config(exit_policy="sell_all", exit_review_dates=(days[2],), liquidate_at_end=False)
        inherited = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), c, e,
                                  membership=self.deleted(days[1], "A"))
        same_day = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), c, e,
                               membership=self.deleted(days[2], "A"))
        self.assertEqual(inherited.summary["exit_policy_sales"], 1)
        inherited_sale = inherited.transactions.query("event=='policy_exit'").iloc[0]
        self.assertEqual(inherited_sale.outside_since, pd.Timestamp(days[1]))
        self.assertEqual(inherited_sale.outside_age_days, 1)
        self.assertEqual(same_day.summary["exit_policy_sales"], 0)
        self.assertEqual(same_day.daily.iloc[-1].unknown_membership_value_eur, 1000)

    def test_gradual_fraction_below_minimum_order_stays_held(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100]*3})
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1),
                         config(exit_policy="gradual", exit_fraction=.0005,
                                exit_review_dates=(days[1],), liquidate_at_end=False),
                         membership=self.deleted("2020-02-01", "A"))
        self.assertEqual(r.summary["exit_policy_sales"], 0)
        self.assertEqual(r.summary["exit_policy_skips"], {"below_minimum_order": 1})
        self.assertEqual(r.daily.iloc[-1].holdings, {"A": 10})

    def test_partial_loss_embargo_propagates_to_rollover_successor(self):
        days = ["2020-01-02", "2020-02-03", "2020-02-04", "2020-03-02", "2020-03-03", "2020-03-04"]
        p = fixture(days, {"A": [100, 90, 90, 90, 90, 90], "B": [90]*6})
        w = pd.concat([weights("2020-01-01", "2020-01-01", A=1),
                       weights("2020-02-04", "2020-02-03", B=1)])
        m = pd.concat([self.deleted("2020-02-01", "A"),
                       pd.DataFrame([dict(effective_date="2020-02-04", security_id="B", is_member=True)])])
        e = pd.DataFrame([dict(date=days[2], security_id="A", event_type="stock_exchange",
                              successor_id="B", ratio=1, tax_treatment="rollover")])
        r = run_backtest(p, w, config(end=days[-1], exit_policy="gradual", exit_fraction=.5,
                                      exit_review_dates=(days[1],), liquidate_at_end=False,
                                      investment_frequency="daily"), e, membership=m)
        buys = r.transactions.query("event=='buy' and security_id=='B'")
        self.assertEqual(buys.date.tolist(), [pd.Timestamp("2020-03-03")])
        receipt = r.transactions.query("event=='automatic_receipt_during_loss_block'")
        self.assertEqual(len(receipt), 1)
        self.assertEqual(receipt.iloc[0].blocked_until, pd.Timestamp("2020-03-03"))


class ProactiveTaxHarvestTests(unittest.TestCase):
    def gain_config(self, days, **kwargs):
        values = dict(end=days[-1], cgt_exemption=1270., gain_harvest=True,
                      gain_review_dates=(days[1],), gain_harvest_reinvest="same_security")
        values.update(kwargs)
        return config(**values)

    def test_fifo_loss_prefix_harvests_older_loss_in_profitable_position(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-04", "2020-04-03"]
        p = fixture(days, {"A": [200, 100, 150, 150]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        c = config(end=days[-1], contribution_dates=tuple(days[:2]), harvest=True,
                   harvest_review_dates=(days[2],), harvest_lot_mode="fifo_prefix",
                   liquidate_at_end=False)
        r = run_backtest(p, w, c)
        whole = run_backtest(p, w, replace(c, harvest_lot_mode="position"))
        sale = r.transactions.query("event=='sell' and reason=='harvest'").iloc[0]
        self.assertAlmostEqual(sale.units, 5)
        self.assertAlmostEqual(sale.realized_gain_eur, -250)
        self.assertAlmostEqual(r.daily.iloc[2].holdings["A"], 10)
        self.assertEqual(len(whole.transactions.query("event=='sell'")), 0)
        self.assertAlmostEqual(r.lots.basis_eur.sum(), 1000)

    def test_fifo_loss_prefix_cannot_skip_older_winner_to_select_later_loss(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-04", "2020-04-03"]
        p = fixture(days, {"A": [100, 200, 150, 150]})
        c = config(end=days[-1], contribution_dates=tuple(days[:2]), harvest=True,
                   harvest_review_dates=(days[2],), harvest_lot_mode="fifo_prefix",
                   liquidate_at_end=False)
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), c)
        self.assertEqual(len(r.transactions.query("event=='sell'")), 0)
        self.assertAlmostEqual(r.daily.iloc[-1].holdings["A"], 15)

    def test_fifo_loss_threshold_uses_prefix_basis_not_whole_position(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-04", "2020-04-03"]
        p = fixture(days, {"A": [200, 100, 188, 188]})
        c = config(end=days[-1], contribution_dates=tuple(days[:2]), harvest=True,
                   harvest_review_dates=(days[2],), harvest_lot_mode="fifo_prefix",
                   harvest_loss_fraction=.05, harvest_min_loss_eur=25, liquidate_at_end=False)
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), c)
        sale = r.transactions.query("event=='sell' and reason=='harvest'").iloc[0]
        self.assertAlmostEqual(sale.realized_gain_eur, -60)
        self.assertAlmostEqual(sale.basis_eur, 1000)

    def test_combined_loss_mode_preserves_aggregate_loss_with_profitable_first_lot(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-04", "2020-04-03"]
        p = fixture(days, {"A": [100, 200, 120, 120]})
        c = config(end=days[-1], contribution_dates=tuple(days[:2]), harvest=True,
                   harvest_review_dates=(days[2],), harvest_lot_mode="position_or_fifo_prefix",
                   liquidate_at_end=False)
        w = weights("2020-01-01", "2020-01-01", A=1)
        r = run_backtest(p, w, c)
        prefix = run_backtest(p, w, replace(c, harvest_lot_mode="fifo_prefix"))
        sale = r.transactions.query("event=='sell' and reason=='harvest'").iloc[0]
        self.assertAlmostEqual(sale.units, 15)
        self.assertAlmostEqual(sale.realized_gain_eur, -200)
        self.assertEqual(len(prefix.transactions.query("event=='sell'")), 0)

    def test_hybrid_exits_departed_before_immediately_replacing_current_winner(self):
        days = ["2020-01-02", "2020-06-01", "2020-12-31"]
        p = fixture(days, {"A": [100, 300, 300], "B": [100, 300, 300]})
        w = pd.concat([weights("2020-01-01", "2020-01-01", A=.5, B=.5),
                       weights("2020-05-01", "2020-05-01", B=1)])
        m = pd.DataFrame([dict(effective_date="2020-05-01", security_id="A", is_member=False)])
        c = self.gain_config(days, gain_harvest_reinvest="hybrid", liquidate_at_end=False)
        r = run_backtest(p, w, c, membership=m)
        details = r.transactions.query("event=='gain_harvest'")
        self.assertEqual(details.security_id.tolist(), ["A", "B"])
        self.assertEqual(details.reinvest.tolist(), ["underweights", "same_security"])
        self.assertEqual(details.realized_gain_eur.tolist(), [1000., 270.])
        replacements = r.transactions.query("event=='buy' and reason=='gain_repurchase'")
        self.assertEqual(replacements.security_id.tolist(), ["B"])
        self.assertEqual(r.daily.iloc[-1].holdings, {"B": 10.})

    def test_hybrid_allows_mixed_departed_fifo_but_current_replacement_stops_at_loss(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-04", "2020-04-03"]
        p = fixture(days, {"A": [200, 100, 150, 150], "B": [100, 200, 150, 150]})
        w = pd.concat([weights("2020-01-01", "2020-01-01", A=.5, B=.5),
                       weights("2020-03-01", "2020-03-01", B=1)])
        m = pd.DataFrame([dict(effective_date="2020-03-01", security_id="A", is_member=False)])
        c = self.gain_config(days, contribution_dates=tuple(days[:2]),
                             gain_review_dates=(days[2],), gain_harvest_reinvest="hybrid",
                             liquidate_at_end=False)
        r = run_backtest(p, w, c, membership=m)
        a = r.transactions.query("event=='lot_disposal' and reason=='gain_harvest' and security_id=='A'")
        b = r.transactions.query("event=='lot_disposal' and reason=='gain_harvest' and security_id=='B'")
        self.assertTrue((a.realized_gain_eur < 0).any())
        self.assertTrue((a.realized_gain_eur > 0).any())
        self.assertTrue((b.realized_gain_eur >= 0).all())
        self.assertEqual(len(b), 1)
        self.assertEqual(r.transactions.query("event=='buy' and reason=='gain_repurchase'").security_id.tolist(), ["B"])

    def test_annual_gain_reset_preserves_exposure_and_saves_exact_exemption_tax(self):
        days = ["2020-01-02", "2020-12-15", "2021-01-15"]
        p = fixture(days, {"A": [100, 400, 400]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        c = self.gain_config(days)
        r, baseline = run_backtest(p, w, c), run_backtest(p, w, replace(c, gain_harvest=False))
        sale = r.transactions.query("event=='sell' and reason=='gain_harvest'").iloc[0]
        self.assertAlmostEqual(sale.realized_gain_eur, 1270)
        self.assertAlmostEqual(r.daily.iloc[1].holdings["A"], 10)
        self.assertAlmostEqual(r.summary["final_cash"]-baseline.summary["final_cash"], 1270*.33)
        self.assertEqual(r.yearly_tax.exemption_used.tolist(), [1270., 1270.])

    def test_multiple_reviews_do_not_reuse_current_year_exemption(self):
        days = ["2020-01-02", "2020-06-01", "2020-08-03", "2020-12-31"]
        p = fixture(days, {"A": [100, 500, 600, 600], "B": [100, 500, 600, 600]})
        c = self.gain_config(days, gain_review_dates=tuple(days[1:]), liquidate_at_end=False)
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=.5, B=.5), c)
        self.assertAlmostEqual(r.summary["gain_harvest_realized_pnl_eur"], 1270)
        self.assertAlmostEqual(r.daily.iloc[-1].cgt_exemption_used_this_year_eur, 1270)
        self.assertAlmostEqual(r.daily.iloc[-1].gain_harvest_headroom_eur, 0)

    def test_carried_losses_are_consumed_before_annual_exemption(self):
        days = ["2020-01-02", "2020-02-03", "2021-01-04", "2021-02-03"]
        p = fixture(days, {"A": [100, 100, 400, 400], "L": [100]*4})
        e = pd.DataFrame([dict(date=days[1], security_id="L", event_type="cash_merger", cash_eur_per_share=0.)])
        c = self.gain_config(days, cgt_exemption=100, gain_review_dates=(days[2],), liquidate_at_end=False)
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=.5, L=.5), c, e)
        self.assertAlmostEqual(r.yearly_tax.iloc[0].loss_carry_forward, 500)
        sale = r.transactions.query("event=='gain_harvest'").iloc[0]
        self.assertAlmostEqual(sale.realized_gain_eur, 600)
        self.assertAlmostEqual(sale.exemption_used_after_eur, 100)
        self.assertAlmostEqual(r.daily.iloc[-1].cgt_reserve_eur, 0)

    def test_same_day_losses_harvested_before_gains_without_future_losses(self):
        days = ["2020-01-02", "2020-06-01", "2020-12-31"]
        p = fixture(days, {"A": [100, 400, 400], "L": [100, 40, 40]})
        c = self.gain_config(days, cgt_exemption=100, harvest=True,
                             harvest_review_dates=(days[1],), liquidate_at_end=False)
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=.5, L=.5), c)
        sells = r.transactions.query("event=='sell'")
        self.assertEqual(sells.reason.tolist(), ["harvest", "gain_harvest"])
        self.assertAlmostEqual(sells.iloc[0].realized_gain_eur, -300)
        self.assertAlmostEqual(sells.iloc[1].realized_gain_eur, 400)

    def test_later_losses_can_erase_earlier_exemption_use(self):
        days = ["2020-01-02", "2020-06-01", "2020-12-01", "2021-01-04"]
        p = fixture(days, {"A": [100, 400, 400, 400], "L": [100]*4})
        e = pd.DataFrame([dict(date=days[2], security_id="L", event_type="cash_merger", cash_eur_per_share=0.)])
        c = self.gain_config(days, cgt_exemption=100, liquidate_at_end=False)
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=.5, L=.5), c, e)
        self.assertAlmostEqual(r.summary["gain_harvest_exemption_increments_eur"], 100)
        self.assertAlmostEqual(r.yearly_tax.iloc[0].exemption_used, 0)
        self.assertAlmostEqual(r.summary["cgt_exemption_used_total_eur"], 0)

    def test_immediate_replacement_stops_before_first_losing_fifo_lot(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-04", "2020-04-03"]
        p = fixture(days, {"A": [100, 200, 150, 150]})
        c = self.gain_config(days, contribution_dates=tuple(days[:2]),
                             gain_review_dates=(days[2],), liquidate_at_end=False)
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), c)
        lots = r.transactions.query("event=='lot_disposal' and reason=='gain_harvest'")
        self.assertEqual(len(lots), 1)
        self.assertAlmostEqual(lots.iloc[0].units, 10)
        self.assertAlmostEqual(lots.iloc[0].realized_gain_eur, 500)
        self.assertAlmostEqual(r.daily.iloc[-1].holdings["A"], 15)

    def test_underweight_mode_uses_actual_fifo_mixed_lot_gain_and_loss(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-04", "2020-03-05"]
        p = fixture(days, {"A": [200, 100, 150, 150]})
        c = self.gain_config(days, cgt_exemption=200, contribution_dates=tuple(days[:2]),
                             gain_review_dates=(days[2],), gain_harvest_reinvest="underweights",
                             liquidate_at_end=False)
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), c)
        lots = r.transactions.query("event=='lot_disposal' and reason=='gain_harvest'")
        self.assertEqual(lots.realized_gain_eur.tolist(), [-250., 450.])
        self.assertAlmostEqual(r.daily.iloc[-1].cgt_exemption_used_this_year_eur, 200)
        self.assertAlmostEqual(r.daily.iloc[-1].holdings["A"], 1)

    def test_fees_included_in_partial_gain_target_and_replacement_basis(self):
        days = ["2020-01-02", "2020-12-15", "2021-01-15"]
        p = fixture(days, {"A": [100, 300, 300]})
        c = self.gain_config(days, fx_fee=.0015, liquidate_at_end=False)
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), c)
        sale = r.transactions.query("event=='sell' and reason=='gain_harvest'").iloc[0]
        buy = r.transactions.query("event=='buy' and reason=='gain_repurchase'").iloc[0]
        self.assertAlmostEqual(sale.realized_gain_eur, 1270)
        self.assertAlmostEqual(buy.cash_outlay_eur, sale.net_proceeds_eur)
        self.assertAlmostEqual(r.lots.basis_eur.sum(), 2270)
        self.assertLess(buy.units, sale.units)
        self.assertAlmostEqual(r.daily.iloc[-1].cash_eur, 0)

    def test_gain_review_date_rolls_forward_and_28_day_purchase_blocks(self):
        days = ["2020-01-02", "2020-01-30", "2020-01-31", "2020-03-02"]
        p = fixture(days, {"A": [100, 300, 300, 300]})
        c = self.gain_config(days, gain_review_dates=("2020-01-29", "2020-01-31"), liquidate_at_end=False)
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), c)
        self.assertEqual(r.transactions.query("event=='gain_harvest'").date.tolist(), [pd.Timestamp(days[2])])
        self.assertEqual(r.summary["gain_harvest_skips"]["recent_class_purchase"], 1)

    def test_fixed_loss_dates_override_daily_frequency_and_cost_hurdle(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-03", "2020-04-03"]
        p = fixture(days, {"A": [100, 99, 99, 99]})
        c = config(end=days[-1], liquidate_at_end=False, harvest=True, harvest_frequency="daily",
                   harvest_review_dates=("2020-03-01",), harvest_min_loss_eur=0,
                   harvest_loss_fraction=0, fx_fee=.01)
        w = weights("2020-01-01", "2020-01-01", A=1)
        r = run_backtest(p, w, c)
        filtered = run_backtest(p, w, replace(c, harvest_cost_multiple=1))
        self.assertEqual(r.transactions.query("event=='sell'").date.tolist(), [pd.Timestamp(days[2])])
        self.assertEqual(len(filtered.transactions.query("event=='sell'")), 0)
        self.assertEqual(len(filtered.transactions.query("event=='harvest_skipped'")), 1)

    def test_future_quotes_and_weights_cannot_change_gain_harvest_prefix(self):
        days = ["2020-01-02", "2020-06-01", "2020-08-03", "2020-12-31"]
        p = fixture(days, {"A": [100, 400, 500, 500], "B": [100]*4})
        w = weights("2020-01-01", "2020-01-01", A=1)
        c = self.gain_config(days, gain_review_dates=tuple(days[1:]), liquidate_at_end=False)
        r = run_backtest(p, w, c)
        p.loc[p.date > days[1], "price_eur"] *= 10
        w = pd.concat([w, weights("2020-05-01", "2020-08-01", B=1)])
        other = run_backtest(p, w, c)
        pd.testing.assert_frame_equal(r.transactions[r.transactions.date <= days[1]].dropna(axis=1, how="all"),
                                      other.transactions[other.transactions.date <= days[1]].dropna(axis=1, how="all"), check_dtype=False)

    def test_departed_only_and_immediate_repurchase_cannot_buy_deleted_stock(self):
        days = ["2020-01-02", "2020-06-01", "2020-12-31"]
        p = fixture(days, {"A": [100, 400, 400], "B": [100]*3})
        w = pd.concat([weights("2020-01-01", "2020-01-01", A=.5, B=.5),
                       weights("2020-05-01", "2020-05-01", B=1)])
        m = pd.DataFrame([dict(effective_date="2020-05-01", security_id="A", is_member=False)])
        c = self.gain_config(days, gain_harvest_scope="departed", liquidate_at_end=False)
        blocked = run_backtest(p, w, c, membership=m)
        allowed = run_backtest(p, w, replace(c, gain_harvest_reinvest="underweights"), membership=m)
        self.assertEqual(blocked.summary["gain_harvest_sales"], 0)
        self.assertEqual(allowed.summary["gain_harvest_sales"], 1)
        self.assertEqual(allowed.transactions.query("event=='gain_harvest'").security_id.tolist(), ["A"])


class NextSessionExecutionTests(unittest.TestCase):
    def next_config(self, days, **changes):
        return config(start=days[0], end=days[-1], execution_mode="next_session",
                      liquidate_at_end=False, **changes)

    def test_buy_cash_budgets_precede_price_shock(self):
        days = ["2020-01-02", "2020-01-03"]
        p = fixture(days, {"A": [100, 1000], "B": [100, 10]})
        w = weights("2020-01-01", "2020-01-01", A=.5, B=.5)
        r = run_backtest(p, w, self.next_config(days))
        buys = r.transactions.query("event=='buy'")
        self.assertEqual(buys.cash_outlay_eur.tolist(), [500, 500])
        self.assertEqual(buys.units.tolist(), [.5, 50])
        self.assertTrue((buys.signal_date < buys.fill_date).all())
        self.assertEqual(r.daily.iloc[0].cash_eur, 1000)
        self.assertEqual(r.daily.iloc[0].holdings, {})

    def test_loss_signal_executes_fixed_units_even_when_fill_is_profitable(self):
        days = ["2020-01-02", "2020-01-03", "2020-03-02", "2020-03-03"]
        p = fixture(days, {"A": [100, 100, 80, 120]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        c = self.next_config(days, harvest=True, harvest_review_dates=(days[2],))
        r = run_backtest(p, w, c)
        sale = r.transactions.query("event=='sell' and reason=='harvest'").iloc[0]
        self.assertEqual(sale.units, 10)
        self.assertEqual(sale.realized_gain_eur, 200)
        self.assertEqual(sale.signal_date, pd.Timestamp(days[2]))
        self.assertEqual(sale.date, pd.Timestamp(days[3]))
        self.assertEqual(r.daily.iloc[-1].cgt_reserve_eur, 66)
        other_prices = p.copy()
        other_prices.loc[other_prices.date.eq(days[-1]), "price_eur"] = 40
        other = run_backtest(other_prices, w, c)
        pd.testing.assert_frame_equal(
            r.transactions.loc[r.transactions.date.le(days[2])].dropna(axis=1, how="all"),
            other.transactions.loc[other.transactions.date.le(days[2])].dropna(axis=1, how="all"))
        self.assertEqual(other.transactions.query("event=='sell'").iloc[0].units, 10)

    def test_gain_price_gap_records_tax_and_rebuys_only_on_later_session(self):
        days = ["2020-01-02", "2020-01-03", "2020-03-02", "2020-03-03", "2020-03-04"]
        p = fixture(days, {"A": [100, 100, 200, 300, 150]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        c = self.next_config(days, cgt_exemption=127, gain_harvest=True,
            gain_review_dates=(days[2],), gain_harvest_reinvest="same_security")
        r = run_backtest(p, w, c)
        sale = r.transactions.query("event=='sell'").iloc[0]
        repurchase = r.transactions.query("event=='buy' and reason=='gain_repurchase'").iloc[0]
        self.assertAlmostEqual(sale.units, 1.27)
        self.assertAlmostEqual(sale.realized_gain_eur, 254)
        self.assertAlmostEqual(r.summary["positive_tax_estimate_error_eur"], 41.91)
        self.assertEqual(repurchase.signal_date, sale.date)
        self.assertGreater(repurchase.date, sale.date)
        self.assertAlmostEqual(repurchase.cash_outlay_eur, 381-41.91)
        self.assertAlmostEqual(repurchase.units, (381-41.91)/150)
        self.assertEqual(repurchase.sale_order_id, sale.order_id)
        self.assertAlmostEqual(r.daily.iloc[-1].cash_eur, 41.91)

    def test_gain_sale_that_fills_at_a_loss_suppresses_repurchase(self):
        days = ["2020-01-02", "2020-01-03", "2020-03-02", "2020-03-03", "2020-03-04"]
        p = fixture(days, {"A": [100, 100, 200, 50, 200]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        c = self.next_config(days, cgt_exemption=127, gain_harvest=True,
            gain_review_dates=(days[2],), gain_harvest_reinvest="same_security")
        r = run_backtest(p, w, c)
        sale = r.transactions.query("event=='sell'").iloc[0]
        self.assertAlmostEqual(sale.realized_gain_eur, -63.5)
        self.assertEqual(len(r.transactions.query("event=='buy'")), 1)
        self.assertEqual(r.transactions.query("event=='gain_repurchase_skipped'").iloc[0].skip_reason,
                         "actual_losing_matched_lot")
        self.assertEqual(r.daily.iloc[-1].cash_eur, 63.5)

    def test_positive_gain_fill_with_one_losing_lot_also_blocks_repurchase(self):
        days = ["2020-01-02", "2020-01-03", "2020-02-03", "2020-02-04", "2020-03-10", "2020-03-11", "2020-03-12"]
        p = fixture(days, {"A": [100, 100, 200, 200, 210, 190, 210]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        c = self.next_config(days, contribution_dates=(days[0], days[2]), cgt_exemption=2000,
            gain_harvest=True, gain_review_dates=(days[4],), gain_harvest_reinvest="same_security")
        r = run_backtest(p, w, c)
        sale = r.transactions.query("event=='sell'").iloc[0]
        self.assertEqual(sale.units, 15)
        self.assertEqual(sale.realized_gain_eur, 850)
        self.assertEqual(len(r.transactions.query("event=='buy'")), 2)
        self.assertEqual(len(r.transactions.query("event=='gain_repurchase_skipped'")), 1)

    def test_split_adjusts_fixed_sale_units(self):
        days = ["2020-01-02", "2020-01-03", "2020-03-02", "2020-03-03"]
        p = fixture(days, {"A": [100, 100, 80, 40]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        events = pd.DataFrame([dict(date=days[-1], security_id="A", event_type="split", ratio=2)])
        c = self.next_config(days, harvest=True, harvest_review_dates=(days[2],))
        r = run_backtest(p, w, c, events)
        sale = r.transactions.query("event=='sell'").iloc[0]
        self.assertEqual(sale.units, 20)
        self.assertEqual(sale.basis_eur, 1000)
        self.assertEqual(sale.realized_gain_eur, -200)
        self.assertEqual(len(r.transactions.query("event=='order_split_adjusted'")), 1)

    def test_spinoff_cancels_pending_orders_without_future_receipt_units(self):
        days = ["2020-01-02", "2020-01-03", "2020-03-02", "2020-03-03"]
        p = fixture(days, {"A": [100, 100, 80, 60], "B": [40]*4})
        w = weights("2020-01-01", "2020-01-01", A=1)
        events = pd.DataFrame([dict(date=days[-1], security_id="A", event_type="spinoff",
            successor_id="B", ratio=.5, basis_fraction=.25, tax_treatment="rollover")])
        c = self.next_config(days, harvest=True, harvest_review_dates=(days[2],))
        r = run_backtest(p, w, c, events)
        self.assertEqual(len(r.transactions.query("event=='sell'")), 0)
        self.assertEqual(r.daily.iloc[-1].holdings, {"A": 10, "B": 5})
        self.assertEqual(r.transactions.query("event=='order_cancelled'").iloc[0].reason, "corporate_action")

    def test_missing_quote_delays_order_without_duplicate_purchase(self):
        days = ["2020-01-02", "2020-01-03", "2020-01-06"]
        p = fixture(days, {"A": [100, None, 200]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        r = run_backtest(p, w, self.next_config(days, investment_frequency="daily"))
        self.assertEqual(r.summary["order_signal_count"], 1)
        buy = r.transactions.query("event=='buy'").iloc[0]
        self.assertEqual(buy.date, pd.Timestamp(days[-1]))
        self.assertEqual(buy.units, 5)

    def test_insufficient_budget_for_whole_share_cancels_without_borrowing(self):
        days = ["2020-01-02", "2020-01-03"]
        p = fixture(days, {"A": [100, 2000]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        r = run_backtest(p, w, self.next_config(days, fractional_shares=False))
        self.assertEqual(r.daily.iloc[-1].cash_eur, 1000)
        self.assertEqual(r.daily.iloc[-1].holdings, {})
        self.assertEqual(r.transactions.query("event=='order_cancelled'").iloc[0].reason, "budget_below_one_share")

    def test_terminal_session_cancels_pending_orders_before_final_sale(self):
        days = ["2020-01-02", "2020-01-03", "2020-03-02", "2020-03-03"]
        p = fixture(days, {"A": [100, 100, 80, 120]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        c = replace(self.next_config(days, harvest=True, harvest_review_dates=(days[2],)), liquidate_at_end=True)
        r = run_backtest(p, w, c)
        self.assertEqual(r.summary["pending_order_count"], 0)
        self.assertEqual(r.transactions.query("event=='sell'").reason.tolist(), ["final_liquidation"])
        self.assertEqual(r.transactions.query("event=='order_cancelled'").iloc[0].reason, "terminal_liquidation")
        self.assertEqual(r.summary["final_cash"], 1134)

    def test_year_boundary_taxes_only_actual_fills(self):
        days = ["2019-01-02", "2019-01-03", "2019-12-31", "2020-01-02", "2020-01-03"]
        p = fixture(days, {"A": [100, 100, 200, 300, 300]})
        w = weights("2019-01-01", "2019-01-01", A=1)
        c = self.next_config(days, cgt_exemption=127, gain_harvest=True,
            gain_review_dates=(days[2],), gain_harvest_reinvest="same_security")
        r = run_backtest(p, w, c)
        self.assertEqual(r.yearly_tax.iloc[0].gains_eur, 0)
        self.assertEqual(r.yearly_tax.iloc[0].exemption_used, 0)
        self.assertEqual(r.transactions.query("event=='sell'").iloc[0].date, pd.Timestamp(days[3]))
        self.assertAlmostEqual(r.daily.iloc[-1].cgt_reserve_eur, 41.91)

    def test_unknown_execution_mode_fails(self):
        p = fixture(["2020-01-02", "2020-03-02"], {"A": [100, 100]})
        with self.assertRaisesRegex(ValueError, "execution mode"):
            run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), config(execution_mode="unknown"))

    def test_rebalance_fixes_excess_units_and_reserves_actual_tax(self):
        days = ["2020-01-02", "2020-01-03", "2020-03-02", "2020-03-03", "2020-03-04"]
        p = fixture(days, {"A": [100, 100, 200, 300, 300], "B": [100, 100, 100, 100, 200]})
        w = weights("2020-01-01", "2020-01-01", A=.5, B=.5)
        r = run_backtest(p, w, self.next_config(days, rebalance_review_dates=(days[2],)))
        sale = r.transactions.query("event=='sell' and reason=='rebalance'").iloc[0]
        self.assertEqual(sale.units, 1.25)
        self.assertEqual(sale.date, pd.Timestamp(days[3]))
        self.assertEqual(sale.realized_gain_eur, 250)
        self.assertEqual(r.summary["rebalance_sale_count"], 1)
        self.assertEqual(r.daily.iloc[-1].cgt_reserve_eur, 82.5)
        buy = r.transactions.query("event=='buy'").iloc[-1]
        self.assertEqual(buy.security_id, "B")
        self.assertEqual(buy.date, pd.Timestamp(days[4]))
        self.assertEqual(buy.cash_outlay_eur, 292.5)
        self.assertEqual(buy.units, 292.5/200)

    def test_rebalance_sells_known_departure_but_retains_unknown_receipt(self):
        days = ["2020-01-02", "2020-01-03", "2020-02-03", "2020-03-02", "2020-03-03"]
        p = fixture(days, {"A": [100, 100, 80, 80, 80], "B": [100]*5, "C": [20]*5})
        w = pd.concat([weights("2020-01-01", "2020-01-01", A=.5, B=.5),
                       weights("2020-02-01", "2020-02-01", A=1)])
        events = pd.DataFrame([dict(date=days[2], security_id="A", event_type="spinoff",
            successor_id="C", ratio=1, basis_fraction=.2, tax_treatment="rollover")])
        member = pd.DataFrame([dict(effective_date="2020-02-01", security_id="B", is_member=False)])
        c = self.next_config(days, rebalance_review_dates=(days[3],))
        r = run_backtest(p, w, c, events, membership=member)
        self.assertEqual(r.transactions.query("event=='sell'").security_id.tolist(), ["B"])
        self.assertEqual(r.daily.iloc[-1].holdings["C"], 5)

    def test_rebalance_respects_recent_purchase_restriction(self):
        days = ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]
        p = fixture(days, {"A": [100, 100, 200, 200], "B": [100]*4})
        w = weights("2020-01-01", "2020-01-01", A=.5, B=.5)
        r = run_backtest(p, w, self.next_config(days, rebalance_review_dates=(days[2],)))
        self.assertEqual(r.summary["rebalance_sale_count"], 0)
        self.assertEqual(r.transactions.query("event=='rebalance_skipped'").iloc[0].skip_reason,
                         "recent_class_purchase")


class DividendSettlementAndMandatoryFeesTests(unittest.TestCase):
    def test_same_day_split_entitlement_and_payment_use_post_split_units(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100, 50, 50]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        events = [
            dict(date=days[1], security_id="A", event_type="dividend_entitlement",
                 dividend_id="d1", cash_eur_per_share=1),
            dict(date=days[1], security_id="A", event_type="split", ratio=2),
            dict(date=days[1], security_id="A", event_type="dividend_payment",
                 dividend_id="d1", cash_eur_per_share=1),
        ]
        for order in ((0, 1, 2), (2, 1, 0), (1, 2, 0)):
            with self.subTest(order=order):
                r = run_backtest(p, w, config(), pd.DataFrame([events[i] for i in order]))
                self.assertEqual(r.summary["total_gross_dividends"], 20)
                self.assertEqual(r.transactions.query("event=='dividend_entitlement'").iloc[0].units, 20)
                self.assertAlmostEqual(r.summary["final_cash"], 1000+20*(1-.5235))

    def test_event_deferred_into_another_tax_year_fails(self):
        days = ["2019-01-02", "2019-12-30", "2020-01-02"]
        p = fixture(days, {"A": [100]*3})
        w = weights("2019-01-01", "2019-01-01", A=1)
        for kind in ("cash_merger", "mixed_merger", "capital_distribution", "cash_dividend",
                     "contingent_cash", "dividend_payment", "dividend_entitlement", "split"):
            with self.subTest(event_type=kind):
                events = pd.DataFrame([dict(date="2019-12-31", security_id="A", event_type=kind,
                    cash_eur_per_share=200, ratio=2)])
                with self.assertRaisesRegex(DataIntegrityError, "deferred across tax-year boundary"):
                    run_backtest(p, w, config(days[0], days[-1]), events)

    def test_pre_start_entitlement_has_zero_units_in_fresh_cohort(self):
        days = ["2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100, 100]})
        e = pd.DataFrame([
            dict(date="2020-01-02", security_id="A", event_type="dividend_entitlement", dividend_id="d1", cash_eur_per_share=2),
            dict(date=days[0], security_id="A", event_type="dividend_payment", dividend_id="d1", cash_eur_per_share=2),
        ])
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1),
                         config(start=days[0], end=days[-1]), e)
        self.assertEqual(r.summary["total_gross_dividends"], 0)
        self.assertEqual(r.summary["final_cash"], 1000)
        with self.assertRaisesRegex(DataIntegrityError, "lacks matching entitlement"):
            run_backtest(p, weights("2020-01-01", "2020-01-01", A=1),
                         config(start=days[0], end=days[-1]), e.iloc[1:])

    def test_dividend_identifier_cannot_be_reused_after_payment(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100]*3})
        e = pd.DataFrame([
            dict(date=days[0], security_id="A", event_type="dividend_entitlement", dividend_id="d1", cash_eur_per_share=2),
            dict(date=days[1], security_id="A", event_type="dividend_payment", dividend_id="d1", cash_eur_per_share=2),
            dict(date=days[2], security_id="A", event_type="dividend_entitlement", dividend_id="d1", cash_eur_per_share=2),
        ])
        with self.assertRaisesRegex(DataIntegrityError, "Duplicate dividend entitlement"):
            run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), config(), e)

    def test_dividend_entitlement_survives_sale_and_cash_waits_for_payment(self):
        days = ["2020-01-02", "2020-02-03", "2020-02-04", "2020-03-02"]
        p = fixture(days, {"A": [100, 90, 90, 90]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        e = pd.DataFrame([
            dict(date=days[1], security_id="A", event_type="dividend_entitlement", dividend_id="d1", cash_eur_per_share=2),
            dict(date=days[2], security_id="A", event_type="cash_merger", cash_eur_per_share=90),
            dict(date=days[3], security_id="A", event_type="dividend_payment", dividend_id="d1", cash_eur_per_share=3),
        ])
        r = run_backtest(p, w, config(), e)
        self.assertEqual(r.daily.iloc[1].cash_eur, 0)
        self.assertAlmostEqual(r.daily.iloc[1].dividend_receivable_eur, 20*(1-.5235))
        self.assertEqual(r.daily.iloc[2].holdings, {})
        self.assertAlmostEqual(r.summary["total_gross_dividends"], 30)
        self.assertAlmostEqual(r.summary["final_cash"], 900+30*(1-.5235))
        self.assertEqual(r.transactions.query("event=='dividend'").date.tolist(), [pd.Timestamp(days[-1])])

    def test_ex_date_buyer_does_not_receive_already_detached_dividend(self):
        days = ["2020-01-02", "2020-02-03", "2020-03-02"]
        p = fixture(days, {"A": [100, 100, 100]})
        w = weights("2020-01-01", "2020-01-01", A=1)
        e = pd.DataFrame([
            dict(date=days[0], security_id="A", event_type="dividend_entitlement", dividend_id="d1", cash_eur_per_share=2),
            dict(date=days[1], security_id="A", event_type="dividend_payment", dividend_id="d1", cash_eur_per_share=2),
        ])
        r = run_backtest(p, w, config(), e)
        self.assertEqual(r.summary["total_gross_dividends"], 0)
        self.assertEqual(r.summary["final_cash"], 1000)

    def test_unpaid_terminal_dividend_fails_closed(self):
        days = ["2020-01-02", "2020-03-02"]
        p = fixture(days, {"A": [100, 100]})
        e = pd.DataFrame([dict(date=days[1], security_id="A", event_type="dividend_entitlement",
                              dividend_id="d1", cash_eur_per_share=2)])
        with self.assertRaisesRegex(DataIntegrityError, "Unpaid dividend receivable"):
            run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), config(), e)

    def test_compulsory_cash_merger_has_no_fx_or_spread_fee(self):
        days = ["2020-01-02", "2020-03-02"]
        p = fixture(days, {"A": [100, 100]})
        e = pd.DataFrame([dict(date=days[1], security_id="A", event_type="cash_merger", cash_eur_per_share=120)])
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1),
                         config(fx_fee=.01, half_spread=.01), e)
        merger = r.transactions.query("event=='sell' and reason=='cash_merger'").iloc[0]
        self.assertEqual(merger.fees_eur, 0)
        self.assertAlmostEqual(r.summary["transaction_costs"], 1000*.02/1.02)

    def test_compulsory_mixed_cash_and_contingent_payment_have_no_fee(self):
        days = ["2020-01-02", "2020-02-03", "2020-02-04", "2020-03-02"]
        p = fixture(days, {"A": [100]*4, "B": [100]*4})
        e = pd.DataFrame([
            dict(date=days[1], security_id="A", event_type="contingent_right", successor_id="R", ratio=1),
            dict(date=days[1], security_id="A", event_type="mixed_merger", successor_id="B", ratio=1,
                 cash_eur_per_share=20, stock_value_eur_per_old_share=100, tax_treatment="rollover"),
            dict(date=days[2], security_id="R", event_type="contingent_cash", cash_eur_per_share=5),
        ])
        c = config(fx_fee=.01, half_spread=.01, liquidate_at_end=False, reinvest_after_disposal=False)
        r = run_backtest(p, weights("2020-01-01", "2020-01-01", A=1), c, e)
        parts = r.transactions.query("event=='lot_disposal' and reason=='mixed_merger'")
        self.assertEqual(parts.fees_eur.sum(), 0)
        self.assertEqual(r.transactions.query("event=='contingent_payment'").fees_eur.sum(), 0)
        self.assertAlmostEqual(r.summary["transaction_costs"], 1000*.02/1.02)


if __name__ == "__main__":
    unittest.main(verbosity=2)
