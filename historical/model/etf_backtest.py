"""Tax-lot replay for an accumulating ETF; accepts independently audited EUR prices.

This module does not reconstruct a direct-stock portfolio. Historical NAVs already
include fund expenses and fund-level withholding: never subtract its TER again.
Tax rates/Trading 212 terms are counterfactual current rules, not historical law.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import sys
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tax"))
from irish_tax import fund_tax_delta


@dataclass
class FundLot:
    acquired: pd.Timestamp
    units: float
    unit_basis: float
    unit_credit: float = 0.0


def monthly_dates(prices, start="2010-09-30", end="2026-09-30"):
    """192 month-end deposits, September 2010 through August 2026.

    The final observation is September 2026, exactly 16 calendar years after
    the first deposit. Select the last observed market date in each month.
    """
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    p = prices.loc[start:end]
    dates = p.groupby(p.index.to_period("M")).apply(lambda x: x.index[-1])
    return set(pd.Timestamp(d) for d in dates.iloc[:-1])


def replay(prices: pd.Series, contribution=1000.0, tax_rate=.38,
           deemed_disposal=True, start="2010-09-30", end="2026-09-30",
           contribution_amounts: tuple[float, ...] | None = None):
    """Replay amounts aligned with sorted monthly_dates; None uses contribution."""
    prices = prices.sort_index().dropna()
    prices = prices[~prices.index.duplicated(keep="last")]
    prices = prices.loc[start:end]
    if len(prices) == 0 or (prices <= 0).any():
        raise ValueError("Positive, dated prices are required")
    if prices.index[0] != pd.Timestamp(start) or prices.index[-1] != pd.Timestamp(end):
        raise ValueError("Price series must include exact start and end dates")
    deposit_dates = sorted(monthly_dates(prices, start, end))
    amounts = contribution_amounts
    if amounts is None:
        amounts = (contribution,) * len(deposit_dates)
    if len(amounts) != len(deposit_dates):
        raise ValueError("Contribution amounts must match the scheduled contribution dates")
    amounts = tuple(float(amount) for amount in amounts)
    if any(not isfinite(amount) or amount < 0 for amount in amounts):
        raise ValueError("Contribution amounts must be finite and nonnegative")
    deposits = dict(zip(deposit_dates, amounts))
    lots, ledger, path = [], [], []
    anniversaries = {}
    total_contributions = total_dd = total_funding_sale_tax = 0.0
    final_tax = 0.0

    def rate_on(day):
        return float(tax_rate(day) if callable(tax_rate) else tax_rate)

    def fund_bill(due, day, price):
        """FIFO sales, with proportional original cost and previously paid credit.

        Liability/refund is settled immediately in the model. This is a tax
        reserve convention, not a claim about Revenue's actual payment dates.
        """
        nonlocal total_funding_sale_tax
        for lot in lots:
            if due <= 1e-8:
                break
            if lot.units <= 1e-12:
                continue
            per_unit_tax = fund_tax_delta(price, lot.unit_basis,
                                          lot.unit_credit, rate_on(day))
            net_per_unit = price - per_unit_tax
            if net_per_unit <= 0:
                raise ValueError("Non-positive redemption proceeds")
            sold = min(lot.units, due / net_per_unit)
            due -= sold * net_per_unit
            amount_tax = sold * per_unit_tax
            total_funding_sale_tax += amount_tax
            lot.units -= sold
            ledger.append(dict(date=day, event="fund_tax_with_fifo_sale",
                               gross_proceeds=sold*price, tax=amount_tax,
                               units=sold, acquisition=lot.acquired))
        if due > 1e-6:
            raise RuntimeError("Insufficient assets to pay tax")

    final_day = prices.index[-1]
    for day, price in prices.items():
        if day in deposits:
            amount = deposits[day]
            lot = FundLot(day, amount/price, price)
            lots.append(lot)
            total_contributions += amount
            # Map calendar anniversaries to the first available valuation day.
            for years in (8, 16):
                anniversary = day + pd.DateOffset(years=years)
                k = prices.index.searchsorted(anniversary)
                if k < len(prices):
                    anniversaries.setdefault(prices.index[k], []).append(lot)
            ledger.append(dict(date=day, event="contribution", cash=amount,
                               units=lot.units, price=price))
        if deemed_disposal and day != final_day:
            bill = 0.0
            for lot in anniversaries.get(day, []):
                if lot.units <= 1e-12:
                    continue
                amount = max(0.0, fund_tax_delta(price*lot.units,
                    lot.unit_basis*lot.units, lot.unit_credit*lot.units, rate_on(day)))
                lot.unit_credit += amount / lot.units
                bill += amount
                ledger.append(dict(date=day, event="deemed_disposal", tax=amount,
                                   units=lot.units, acquisition=lot.acquired))
            total_dd += bill
            if bill > 1e-8:
                fund_bill(bill, day, price)
        value = sum(l.units*price for l in lots)
        if day == final_day:
            final_tax = sum(fund_tax_delta(l.units*price, l.units*l.unit_basis,
                l.units*l.unit_credit, rate_on(day)) for l in lots)
            ledger.append(dict(date=day, event="final_sale", gross_proceeds=value,
                               tax=final_tax, net_proceeds=value-final_tax))
        path.append(dict(date=day, value=value, contributed=total_contributions,
                         tax_paid=total_dd+total_funding_sale_tax,
                         hypothetical_liquidation_tax=sum(fund_tax_delta(
                             l.units*price,l.units*l.unit_basis,
                             l.units*l.unit_credit,rate_on(day)) for l in lots)))
    result = dict(contributions=total_contributions,
                  contribution_count=len(deposits),
                  final_value_before_final_tax=value,
                  final_tax=final_tax,
                  final_cash=value-final_tax,
                  deemed_disposal_tax=total_dd,
                  funding_sales_tax=total_funding_sale_tax,
                  total_tax=total_dd+total_funding_sale_tax+final_tax)
    return result, pd.DataFrame(ledger), pd.DataFrame(path)
