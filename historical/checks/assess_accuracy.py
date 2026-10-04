"""Check saved arithmetic and quantify the limits of the ETF comparison.

Run: .venv/bin/python historical/checks/assess_accuracy.py
This script does not replay either portfolio engine. Concentration uses the
study's prepared price marks, so it does not independently validate those marks.
"""
from pathlib import Path
import hashlib
import json
import sys
import tempfile

import pandas as pd

from audit_ledgers import audit_case, near

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/latest"
LEDGERS = OUT / "ledgers"
sys.path.insert(0, str(ROOT))
from study_inputs import prepare


def read(path):
    return json.loads(path.read_text())


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def money_weighted_return(deposits, terminal_date, terminal_cash):
    """Annual IRR on actual cash-flow dates, using 365.25 days per year."""
    years = (pd.Timestamp(terminal_date)-pd.to_datetime(deposits.date)).dt.days / 365.25
    low, high = -0.999, 10.
    for _ in range(100):
        rate = (low+high)/2
        future_value = (deposits.cash_eur * (1+rate)**years).sum()
        if future_value < terminal_cash:
            low = rate
        else:
            high = rate
    near((deposits.cash_eur * (1+rate)**years).sum(), terminal_cash, "IRR cash flows")
    return rate


def main():
    manifest = read(OUT / "study_manifest.json")
    hashes = {**manifest["input_sha256"], **manifest["code_sha256"]}
    hashes["results/latest/ledgers/membership_used.csv"] = manifest["prepared_membership_sha256"]
    for name, expected in hashes.items():
        assert digest(ROOT / name) == expected, f"Stale recorded input or code: {name}"

    summaries = {s["key"]: s for s in read(LEDGERS / "all_summaries.json")}
    etf = read(OUT / "etf/summary.json")
    schedule = pd.read_csv(OUT / "contribution_schedule.csv")
    near(schedule.contribution_eur.sum(), manifest["contributions_eur"], "Total contributions")
    assert len(schedule) == 192 and schedule.date.nunique() == 192
    near(etf["contributions"], schedule.contribution_eur.sum(), "ETF contributions")
    assert etf["contribution_count"] == len(schedule)
    specs = read(OUT / "policy_definitions.json")
    assert set(summaries) == {s["key"] for s in specs}
    ledger_checks = [audit_case(LEDGERS / f"{key}_summary.json") for key in summaries]
    for key, summary in summaries.items():
        assert summary == read(LEDGERS / f"{key}_summary.json"), f"Stale combined summary: {key}"
        near(summary["contributions"], schedule.contribution_eur.sum(), f"{key} contributions")
        assert summary["contribution_count"] == len(schedule)

    comparison = pd.read_csv(OUT / "comparison.csv")
    for row in comparison.itertuples():
        summary = etf if row.key == "etf" else summaries[row.key]
        for column in ("final_cash", "total_tax"):
            near(getattr(row, column), summary[column], f"{row.key} {column}")
        near(row.difference_vs_baseline_eur, row.final_cash-summaries["baseline"]["final_cash"], "Headline difference")
    marginal = pd.read_csv(OUT / "marginal_effects.csv")
    for row in marginal.itertuples():
        a, b = summaries[row.control], summaries[row.variant]
        for column, expected in {
            "after_tax_gain_eur": b["final_cash"]-a["final_cash"],
            "cgt_reduction_eur": a["total_cgt"]-b["total_cgt"],
            "additional_cost_eur": b["transaction_costs"]-a["transaction_costs"],
            "additional_nominal_exemption_shelter_eur": b["nominal_cgt_sheltered_by_exemption_eur"]-a["nominal_cgt_sheltered_by_exemption_eur"],
        }.items():
            near(getattr(row, column), expected, f"{row.control}/{row.variant} {column}")

    chain = [("ETF to direct baseline", "etf", "baseline"),
             ("Quarterly departure management", "baseline", "exits"),
             ("Weekly loss reviews", "exits", "weekly_tlh"),
             ("Annual gain reviews", "weekly_tlh", "weekly_annual")]
    all_cases = {"etf": etf, **summaries}
    gap = summaries["weekly_annual"]["final_cash"]-etf["final_cash"]
    decomposition = [dict(step=label, control=a, variant=b,
                          change_eur=all_cases[b]["final_cash"]-all_cases[a]["final_cash"],
                          share_of_total_gap=(all_cases[b]["final_cash"]-all_cases[a]["final_cash"])/gap)
                     for label, a, b in chain]
    near(sum(row["change_eur"] for row in decomposition), gap, "Sequential decomposition")
    bridges = []
    for row in marginal.itertuples():
        a, b = summaries[row.control], summaries[row.variant]
        gross_a = a["final_cash"]-a["contributions"]+a["total_tax"]+a["transaction_costs"]
        gross_b = b["final_cash"]-b["contributions"]+b["total_tax"]+b["transaction_costs"]
        tax_change = b["total_tax"]-a["total_tax"]
        cost_change = b["transaction_costs"]-a["transaction_costs"]
        near(gross_b-gross_a-tax_change-cost_change, row.after_tax_gain_eur, "Accounting bridge")
        bridges.append(dict(control=row.control, variant=row.variant,
                            change_in_gross_investment_profit_eur=gross_b-gross_a,
                            additional_total_tax_eur=tax_change, additional_cost_eur=cost_change,
                            change_in_final_cash_eur=row.after_tax_gain_eur))

    with tempfile.TemporaryDirectory(prefix="nasdaq-accuracy-inputs-") as temporary:
        prices, weights, _, metadata, _, _ = prepare(audit_dir=temporary)
    metadata = metadata.drop_duplicates("security_id").set_index("security_id")
    weights["effective_date"] = pd.to_datetime(weights.effective_date)
    weights["available_date"] = pd.to_datetime(weights.available_date)
    diagnostics = []
    for key in ("baseline", "monthly_tlh", "monthly_hybrid", "weekly_annual"):
        summary = summaries[key]
        daily = pd.read_csv(LEDGERS / f"{key}_daily.csv.gz", parse_dates=["date"])
        transactions = pd.read_csv(LEDGERS / f"{key}_transactions.csv.gz", low_memory=False)
        prior = daily.iloc[:-1]
        as_of = prior.iloc[-1]
        holdings = pd.Series(json.loads(as_of.holdings), dtype=float)
        marks = prices.loc[prices.date.le(as_of.date)].dropna(subset=["price_eur"])
        marks = marks.sort_values("date").groupby("security_id").tail(1).set_index("security_id")
        assert holdings.index.isin(marks.index).all()
        values = holdings * marks.price_eur.reindex(holdings.index)
        near(values.sum()+as_of.cash_eur+as_of.get("dividend_receivable_eur", 0.),
             as_of.value_eur, f"{key} pre-liquidation value")
        held_weights = (values/values.sum()).sort_values(ascending=False)
        known = weights.loc[weights.effective_date.le(as_of.date) & weights.available_date.lt(as_of.date)]
        snapshot = known.sort_values(["effective_date", "available_date"]).iloc[-1]
        targets = known.loc[known.effective_date.eq(snapshot.effective_date) & known.available_date.eq(snapshot.available_date)]
        targets = targets.groupby("security_id").weight.sum()
        near(targets.sum(), 1., "Target weights")
        top = [dict(security_id=security, ticker=str(metadata.loc[security, "ticker"]),
                    share_of_stock_value=float(weight), last_known_target_weight=float(targets.get(security, 0.)))
               for security, weight in held_weights.head(10).items()]
        buys = transactions.loc[transactions.event.eq("buy")]
        discretionary = transactions.loc[transactions.event.eq("sell") & transactions.reason.isin(["harvest", "gain_harvest", "policy_exit"])]
        deposits = transactions.loc[transactions.event.eq("contribution")]
        growth = (daily.after_tax_liquidation_value_eur-daily.contributions_eur.diff()) / daily.after_tax_liquidation_value_eur.shift()
        growth.iloc[0] = daily.after_tax_liquidation_value_eur.iloc[0]/daily.contributions_eur.iloc[0]
        unit_growth = growth.cumprod()
        near((unit_growth-daily.after_tax_unit_growth).abs().max(), 0., f"{key} unit growth")
        near(unit_growth.iloc[-1]**(1/16)-1, summary["after_tax_unit_annualized_return"], "Annualized marked return")
        diagnostics.append(dict(
            key=key, as_of=str(as_of.date.date()), stock_position_count=len(holdings),
            total_stock_value_eur=float(values.sum()), top10_share_of_stock_value=float(held_weights.head(10).sum()),
            target_effective_date=str(snapshot.effective_date.date()), target_available_date=str(snapshot.available_date.date()),
            target_top10_weight=float(targets.nlargest(10).sum()), top_holdings=top,
            purchases=len(buys), discretionary_sales=len(discretionary),
            dividend_records=int(transactions.event.eq("dividend").sum()),
            fractional_purchases=int((buys.units-buys.units.round()).abs().gt(1e-8).sum()),
            purchases_below_eur10=int(buys.cash_outlay_eur.lt(10).sum()),
            median_purchase_eur=float(buys.cash_outlay_eur.median()),
            total_purchase_outlay_eur=float(buys.cash_outlay_eur.sum()),
            discretionary_sale_gross_eur=float(discretionary.gross_proceeds_eur.sum()),
            mean_cash_share=float((prior.cash_eur/prior.value_eur).mean()),
            peak_cash_share=float((prior.cash_eur/prior.value_eur).max()),
            money_weighted_annual_return=money_weighted_return(deposits, daily.date.iloc[-1], summary["final_cash"]),
            mean_outside_weight=summary["mean_outside_weight"], mean_unknown_weight=summary["mean_unknown_weight"],
        ))
    result = dict(
        classification="SAVED_OUTPUT_ARITHMETIC_AND_EXPOSURE_AUDIT",
        scope="Arithmetic checks on saved outputs, plus portfolio diagnostics from shared prepared price inputs. This is not an independent market-data audit or a new backtest.",
        study_manifest_sha256=digest(OUT / "study_manifest.json"),
        manifest_hashes=dict(all_match=True, count=len(hashes), files=sorted(hashes),
                             limitation="Matching hashes verify consistency with recorded artifacts, not completeness, source accuracy, or availability at the historical date."),
        ledger_checks=ledger_checks,
        arithmetic_checks=dict(stock_cases=len(summaries), headline_rows=len(comparison), matched_pairs=len(marginal),
                               all_passed=True, contribution_count=len(schedule), contributions_eur=float(schedule.contribution_eur.sum()),
                               max_cash_residual_eur=max(abs(c["cash_error_eur"]) for c in ledger_checks),
                               max_basis_residual_eur=max(abs(c["basis_error_eur"]) for c in ledger_checks)),
        headline_decomposition=dict(total_gap_eur=gap, relative_gap=gap/etf["final_cash"], steps=decomposition),
        accounting_bridges=bridges, portfolio_diagnostics=diagnostics,
        limitations=[
            "Gross investment profit is an accounting reconstruction of each actual modeled path. It is not a counterfactual return with all taxes removed.",
            "Concentration uses September 29 holdings and available marks. Target weights are dated August 31. Their difference is not contemporaneous ETF tracking error.",
            "Top ten counts share classes, not consolidated companies. The stock-value denominator excludes cash. The target denominator includes any target cash weight.",
            "Trade counts exclude corporate-action and final-liquidation sales from discretionary sales. No minimum commission or value for investor time is modeled.",
            "The marked after-tax unit curve is not an investable index. Its annualized return differs from the investor money-weighted return.",
            "One retrospectively selected 16-year market path supplies no confidence interval, out-of-sample validation, or probability of future outperformance.",
        ],
    )
    destination = OUT / "accuracy_audit.json"
    destination.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps(dict(output=str(destination.relative_to(ROOT.parent)), **result["arithmetic_checks"]), indent=2))


if __name__ == "__main__":
    main()
