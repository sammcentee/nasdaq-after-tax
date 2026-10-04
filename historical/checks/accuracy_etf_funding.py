"""Independently check corrected ETF funding and the legacy policy control.

Run: .venv/bin/python historical/checks/accuracy_etf_funding.py
This script does not import the study engine or its tax functions.
"""
from pathlib import Path
import hashlib
import json
import math

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/latest"


def near(actual, expected, label):
    assert math.isfinite(actual) and math.isfinite(expected), label
    assert abs(actual-expected) < 1e-6, (label, actual, expected)


def replay(prices, deposits, contribution_first):
    lots, anniversaries = [], {}
    dd_tax = funding_tax = funding_proceeds = purchase_cash = 0.
    purchased_units = sold_units = disposed_credit = positive_gain_tax = diverted = 0.

    def buy(day, amount, price):
        nonlocal purchase_cash, purchased_units
        if amount <= 0:
            return
        lot = dict(units=amount/price, basis=price, credit=0.)
        lots.append(lot)
        purchase_cash += amount
        purchased_units += lot["units"]
        for years in (8, 16):
            index = prices.index.searchsorted(day+pd.DateOffset(years=years))
            if index < len(prices):
                anniversaries.setdefault(prices.index[index], []).append(lot)

    for day, price in prices.items():
        cash = deposits.get(day, 0.)
        if not contribution_first:
            buy(day, cash, price)
            cash = 0.
        due = 0.
        if day != prices.index[-1]:
            for lot in anniversaries.get(day, []):
                tax = max(0., max(0., price-lot["basis"])*.38-lot["credit"])*lot["units"]
                if lot["units"] > 0:
                    lot["credit"] += tax/lot["units"]
                due += tax
            dd_tax += due
            payment = min(cash, due)
            cash -= payment
            due -= payment
            diverted += payment
            for lot in lots:
                if due <= 1e-8:
                    break
                gross_tax_per_unit = max(0., price-lot["basis"])*.38
                tax_per_unit = gross_tax_per_unit-lot["credit"]
                units = min(lot["units"], due/(price-tax_per_unit))
                due -= units*(price-tax_per_unit)
                funding_proceeds += units*price
                funding_tax += units*tax_per_unit
                positive_gain_tax += units*gross_tax_per_unit
                disposed_credit += units*lot["credit"]
                sold_units += units
                lot["units"] -= units
            assert due < 1e-6, (day, due)
        if contribution_first:
            buy(day, cash, price)
    value = sum(lot["units"]*price for lot in lots)
    remaining_credit = sum(lot["units"]*lot["credit"] for lot in lots)
    final_gross_tax = sum(lot["units"]*max(0., price-lot["basis"])*.38 for lot in lots)
    final_tax = final_gross_tax-remaining_credit
    total_tax = dd_tax+funding_tax+final_tax
    final_cash = value-final_tax
    contributions = sum(deposits.values())
    errors = dict(
        cash_eur=contributions+funding_proceeds+value-purchase_cash-total_tax-final_cash,
        units=purchased_units-sold_units-sum(lot["units"] for lot in lots),
        dd_credit_eur=dd_tax-disposed_credit-remaining_credit,
        lifetime_tax_eur=total_tax-positive_gain_tax-final_gross_tax,
        contribution_allocation_eur=contributions-purchase_cash-diverted)
    for name, error in errors.items():
        near(error, 0., name)
    return dict(contributions=contributions, contribution_count=len(deposits),
                final_value_before_final_tax=value, final_cash=final_cash,
                deemed_disposal_tax=dd_tax, funding_sales_tax=funding_tax,
                final_tax=final_tax, total_tax=total_tax,
                same_day_contributions_used_for_tax_eur=diverted,
                gross_funding_sales_eur=funding_proceeds, purchase_outlay_eur=purchase_cash,
                accounting_errors=errors)


def main():
    nav_path = ROOT / "benchmark/issuer/cndx_nav_eur_2010-09-30_to_2026-09-30.csv"
    schedule_path = OUT / "contribution_schedule.csv"
    published_path = OUT / "etf/summary.json"
    nav = pd.read_csv(nav_path, parse_dates=["date"]).set_index("date")
    prices = nav.loc[nav.index.weekday < 5, "nav_eur"]
    assert prices.index.is_unique and prices.index.is_monotonic_increasing
    assert prices.notna().all() and (prices > 0).all()
    assert prices.index[[0, -1]].strftime("%Y-%m-%d").tolist() == ["2010-09-30", "2026-09-30"]
    schedule = pd.read_csv(schedule_path, parse_dates=["date"])
    assert len(schedule) == 192 and schedule.date.is_unique
    assert schedule.date.isin(prices.index).all() and (schedule.contribution_eur >= 0).all()
    assert schedule.date.max() < prices.index[-1]
    deposits = dict(zip(schedule.date, schedule.contribution_eur))
    corrected = replay(prices, deposits, contribution_first=True)
    legacy = replay(prices, deposits, contribution_first=False)
    published = json.loads(published_path.read_text())
    for name, expected in published.items():
        near(corrected[name], expected, "published corrected "+name)
    source_files = [nav_path, schedule_path, published_path, Path(__file__).resolve()]
    output = dict(
        scope="Independent reproduction of the corrected default and a legacy policy control",
        command=".venv/bin/python historical/checks/accuracy_etf_funding.py",
        source_sha256={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in source_files},
        assumptions=[
            "Both cases use the saved issuer EUR NAV and all 192 saved contributions.",
            "The tax rate stays at 38%; this is not a historical-law reconstruction.",
            "Units are fractional. No ETF execution costs or extra external cash enter either case.",
            "NAV already includes fund expenses and fund-level taxes.",
            "Each purchase has original cost and proportional prior deemed-disposal tax credit.",
            "Eight-year anniversaries use the first available weekday NAV on or after the anniversary.",
            "Tax and refunds settle immediately. Final liquidation replaces same-day deemed disposal.",
            "Corrected default: use only that day's contribution for tax first; invest its remainder after tax.",
            "Legacy control: invest each contribution, then sell FIFO units to pay tax.",
            "Both policies sell FIFO units for residual tax, with tax on those sales included.",
            "The corrected default uses no later contribution and does not optimize annual payment dates."],
        accounting_checks={
            "cash_eur": "Contributions + gross sales - purchases - all taxes = final cash.",
            "units": "Purchased units - funding-sale units = units before final liquidation.",
            "dd_credit_eur": "Prior DD tax = credits on sold units + credits on remaining units.",
            "lifetime_tax_eur": "Total tax = 38% of positive gains on actual disposals, including final sale.",
            "contribution_allocation_eur": "Contributions = purchases + contributions used directly for tax."},
        corrected_independent_reproduction=corrected,
        legacy_buy_before_tax_control=legacy,
        final_wealth_difference_eur=corrected["final_cash"]-legacy["final_cash"],
        published_summary_reproduced=True,
        limitation="Arithmetic agreement does not verify market data, tax classification or executable prices.")
    destination = OUT / "accuracy_etf_funding.json"
    destination.write_text(json.dumps(output, indent=2, allow_nan=False)+"\n")
    print(f"ETF corrected default reproduced: EUR{corrected['final_cash']:,.2f}")
    print(f"Legacy buy-before-tax control: EUR{legacy['final_cash']:,.2f}")
    print(f"Difference: EUR{output['final_wealth_difference_eur']:,.2f}; accounting checks passed")
    print(destination)


if __name__ == "__main__":
    main()
