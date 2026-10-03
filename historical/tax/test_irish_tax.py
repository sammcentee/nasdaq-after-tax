"""Financial edge cases that materially change the comparison."""

import unittest
from datetime import date

from irish_tax import (fund_tax_delta, settle_cgt_year, settle_us_dividend,
                       stock_matching_order,
                       unrestricted_loss_after_repurchase)


class IrishTaxEdgeCases(unittest.TestCase):
    def test_carried_losses_are_used_before_allowance(self):
        result = settle_cgt_year(gains=1270, current_losses=0,
                                 carried_losses=2000)
        self.assertEqual(result.tax_due, 0)
        self.assertEqual(result.loss_carry_forward, 730)
        self.assertEqual(result.exemption_used, 0)

    def test_revenue_cgt_example(self):
        result = settle_cgt_year(gains=96270, current_losses=50000,
                                 carried_losses=10000)
        self.assertEqual(result.taxable_gain, 35000)
        self.assertEqual(result.tax_due, 11550)

    def test_loss_no_immediate_cash_rebate(self):
        result = settle_cgt_year(gains=0, current_losses=10000)
        self.assertEqual(result.tax_due, 0)
        self.assertEqual(result.loss_carry_forward, 10000)

    def test_fund_drop_after_deemed_disposal_refunds_excess(self):
        # Buy at100; year8 value200 gives38 DD tax; sell at150 gives19 refund.
        self.assertEqual(fund_tax_delta(150, 100, 38), -19)
        self.assertEqual(fund_tax_delta(90, 100, 38), -38)

    def test_fund_dd_at_final_exit_cannot_double_tax(self):
        # Prior DD tax38; gain200 now means total76, hence only38 more.
        delta = fund_tax_delta(300, 100, 38)
        self.assertEqual(delta, 38)
        self.assertEqual(fund_tax_delta(300, 100, 38 + delta), 0)

    def test_sale_credit_prorates(self):
        # Half the position: basis50, value150, credit19 -> tax19.
        self.assertEqual(fund_tax_delta(150, 50, 19), 19)

    def test_no_fund_loss_credit_without_prior_tax(self):
        self.assertEqual(fund_tax_delta(80, 100, 0), 0)

    def test_us_withholding_not_added_twice(self):
        result = settle_us_dividend(100)
        self.assertAlmostEqual(result.foreign_withholding, 15)
        self.assertAlmostEqual(result.irish_tax_top_up, 37.35)
        self.assertAlmostEqual(result.total_tax, 52.35)
        self.assertAlmostEqual(result.net_to_reinvest, 47.65)

    def test_recent_buys_override_fifo(self):
        dates = [date(2020, 1, 1), date(2026, 5, 1), date(2026, 5, 10)]
        self.assertEqual(stock_matching_order(dates, date(2026, 5, 20)),
                         [2, 1, 0])

    def test_fifo_after_four_weeks(self):
        dates = [date(2026, 1, 1), date(2026, 2, 1)]
        self.assertEqual(stock_matching_order(dates, date(2026, 5, 20)),
                         [0, 1])

    def test_fractional_repurchase_ring_fences_fractional_loss(self):
        self.assertAlmostEqual(unrestricted_loss_after_repurchase(1000, 100, 40),
                               600)


if __name__ == "__main__":
    unittest.main()
