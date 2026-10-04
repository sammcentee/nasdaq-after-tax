"""Measure source gaps and provisional values in the saved headline ledgers.

Run from the repository root with .venv/bin/python. These checks measure the
saved reconstruction. They do not certify market data or bound return errors.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/latest"
CASES = ("baseline", "monthly_tlh", "monthly_hybrid", "weekly_annual")
sys.path.insert(0, str(ROOT))
from study_inputs import prepare

CDK_SOURCE = "https://www.sec.gov/Archives/edgar/data/1609702/000160970221000058/cdk-20210630.htm"
LOGM_SOURCE = "https://www.sec.gov/Archives/edgar/data/1420302/000156459018025208/logm-10q_20180930.htm"
# The issuer reports confirm these actual payments. The list is incomplete.
DIVIDENDS = [
    ("yahoo:CDK", "2020-09-01", "2020-09-30", .15, CDK_SOURCE),
    ("yahoo:CDK", "2020-12-01", "2020-12-30", .15, CDK_SOURCE),
    ("yahoo:CDK", "2021-03-08", "2021-03-30", .15, CDK_SOURCE),
    ("yahoo:CDK", "2021-06-21", "2021-06-30", .15, CDK_SOURCE),
    ("yahoo:LOGM", "2018-08-08", "2018-08-24", .30, LOGM_SOURCE),
]


def main():
    coverage_path = ROOT / "inputs/best_effort/purchase_date_coverage.csv"
    coverage = pd.read_csv(coverage_path)
    schedule = pd.read_csv(OUT / "contribution_schedule.csv")
    assert coverage.purchase_date.tolist() == schedule.date.tolist()
    dates = pd.to_datetime(coverage.purchase_date)
    ages = (dates-pd.to_datetime(coverage.source_effective_date)).dt.days
    assert ages.tolist() == coverage.source_age_days.tolist()
    assert (pd.to_datetime(coverage.source_available_date) < dates).all()
    assert (pd.to_datetime(coverage.source_effective_date) <= dates).all()
    with TemporaryDirectory(prefix="nasdaq-accuracy-data-") as audit_dir:
        p, w, _, metadata, _, _ = prepare(audit_dir)
    currencies = metadata.set_index("security_id").currency.to_dict()
    snapshots = sorted(set(zip(pd.to_datetime(w.effective_date), pd.to_datetime(w.available_date))))
    for row in coverage.itertuples():
        day = pd.Timestamp(row.purchase_date)
        latest = max(pair for pair in snapshots if pair[0] <= day and pair[1] < day)
        assert latest == (pd.Timestamp(row.source_effective_date), pd.Timestamp(row.source_available_date))
    provisional = p.loc[~p.tradable]
    marks = {day: dict(zip(group.security_id, group.price_eur))
             for day, group in provisional.groupby("date")}
    fx = pd.read_csv(ROOT / "benchmark/issuer/cndx_nav_eur.csv").set_index("date").usd_per_eur
    result = {
        "classification": "DESCRIPTIVE_DATA_LIMITS_NOT_AN_ERROR_BOUND",
        "broker_cash_payment_fee_source": "https://helpcentre.trading212.com/hc/en-us/articles/11669719976093-What-is-a-multi-currency-account",
        "metric_definitions": {
            "coverage": "Cached source-coverage audit on the 192 scheduled contribution dates; equal weight per date, not invested capital. Dates and latest eligible snapshots are checked against current prepared inputs.",
            "provisional_weight": "Value of held securities with an explicit nontradable prepared mark divided by same-day value_eur, which includes cash before CGT reserve deduction. Mean includes every saved daily row, including final liquidation. Other stale quotes and contingent rights are excluded.",
            "dividend_examples": "Five actual issuer payments absent from the saved ledgers. Units must remain positive and constant from seven calendar days before the record date through payment. The window covers ordinary ex-date entitlement, without an exact ex-date assumption. Gross EUR uses payment-date ECB FX; this is not an exact model correction, since the model uses ex-date cash accrual. Tax, reinvestment and later decisions are excluded. Full missing-dividend total remains unknown.",
            "mandatory_cash_fx_fees": "Cash-merger and contingent-payment fees plus inferred mixed-merger/capital-distribution fees. Mixed-event rows store net cash without a fee field, so fees equal net cash times 0.0015/0.9985. The configuration check requires a 0.15% FX fee and zero half-spread. All affected securities use USD metadata or the USD default. This amount excludes later tax and reinvestment effects.",
        },
        "source_coverage": {
            "scheduled_contribution_dates": len(coverage),
            "mean_snapshot_age_days": float(ages.mean()),
            "median_snapshot_age_days": float(ages.median()),
            "maximum_snapshot_age_days": int(ages.max()),
            "maximum_age_purchase_date": coverage.loc[ages.idxmax(), "purchase_date"],
            "dates_age_over_60_days": int(ages.gt(60).sum()),
            "dates_age_over_90_days": int(ages.gt(90).sum()),
            "dates_with_new_members_without_source_weight": int(coverage.new_members_without_source_weight.gt(0).sum()),
            "maximum_new_members_without_source_weight": int(coverage.new_members_without_source_weight.max()),
            "dates_with_unresolved_target_weight": int(coverage.unresolved_weight_reserved_as_cash.gt(0).sum()),
            "mean_unresolved_target_weight": float(coverage.unresolved_weight_reserved_as_cash.mean()),
            "maximum_unresolved_target_weight": float(coverage.unresolved_weight_reserved_as_cash.max()),
            "minimum_mapped_current_member_target_weight": float(coverage.mapped_current_member_target_weight.min()),
            "recorded_prior_availability_passes": True,
            "availability_limitation": "The CNDX five-business-day publication lag and community membership availability remain assumptions, not proven historical timestamps.",
        },
        "explicit_provisional_marks": {"prepared_rows": len(provisional), "securities": provisional.security_id.nunique()},
        "strategies": {},
    }
    for key in CASES:
        daily = pd.read_csv(OUT / "ledgers" / f"{key}_daily.csv.gz", parse_dates=["date"])
        daily["holdings"] = daily.holdings.map(json.loads)
        daily["provisional_value_eur"] = [sum(units*marks.get(row.date, {}).get(security, 0.)
            for security, units in row.holdings.items()) for row in daily.itertuples()]
        daily["provisional_weight"] = daily.provisional_value_eur/daily.value_eur
        peak = daily.loc[daily.provisional_weight.idxmax()]
        transactions = pd.read_csv(OUT / "ledgers" / f"{key}_transactions.csv.gz", low_memory=False)
        config = json.loads((OUT / "ledgers" / f"{key}_summary.json").read_text())["configuration"]
        assert config["half_spread"] == 0 and config["fx_fee"] == .0015
        cash_actions = transactions.event.eq("sell") & transactions.reason.eq("cash_merger")
        cash_actions |= transactions.event.eq("contingent_payment")
        mixed = transactions.event.eq("lot_disposal") & transactions.reason.isin(["mixed_merger", "capital_distribution"])
        assert all(currencies.get(security, "USD") == "USD"
                   for security in transactions.loc[cash_actions | mixed, "security_id"])
        mandatory_fees = float(transactions.loc[cash_actions, "fees_eur"].sum()
            + transactions.loc[mixed, "net_proceeds_eur"].sum()*.0015/.9985)
        examples = []
        for security, record, payment, amount, source in DIVIDENDS:
            window = daily.loc[daily.date.between(pd.Timestamp(record)-pd.Timedelta(days=7), pd.Timestamp(payment))]
            units = window.holdings.map(lambda held: held.get(security, 0.))
            assert len(units) and units.min() > 0 and units.nunique() == 1
            recorded = transactions.loc[transactions.event.eq("dividend") & transactions.security_id.eq(security)]
            assert recorded.empty, (key, security, "Dividend evidence requires review")
            examples.append(dict(security_id=security, record_date=record, payment_date=payment,
                dividend_usd_per_share=amount, units=float(units.iloc[0]),
                units_constant_in_entitlement_window=True,
                omitted_gross_eur_at_payment_fx=float(units.iloc[0]*amount/fx.loc[payment]), source=source))
        buys = transactions.loc[transactions.event.eq("buy")]
        result["strategies"][key] = {
            "daily_rows": len(daily),
            "days_with_explicit_provisional_value": int(daily.provisional_value_eur.gt(0).sum()),
            "peak_provisional_weight": float(peak.provisional_weight),
            "peak_weight_date": str(peak.date.date()),
            "provisional_value_eur_at_peak_weight": float(peak.provisional_value_eur),
            "maximum_provisional_value_eur": float(daily.provisional_value_eur.max()),
            "mean_provisional_weight": float(daily.provisional_weight.mean()),
            "known_omitted_dividend_examples": examples,
            "five_examples_omitted_gross_eur_at_payment_fx": sum(row["omitted_gross_eur_at_payment_fx"] for row in examples),
            "mandatory_cash_fx_fees_eur": mandatory_fees,
            "buy_count": len(buys),
            "buy_count_below_one_share": int(buys.units.lt(1).sum()),
        }
    paths = [Path(__file__), ROOT / "study_inputs.py", coverage_path, OUT / "contribution_schedule.csv",
             ROOT / "benchmark/issuer/cndx_nav_eur.csv", ROOT / "benchmark/indexes/NASDAQ100.csv"]
    paths += [ROOT / f"inputs/best_effort/{name}.csv" for name in ("best_effort_weights", "membership", "metadata")]
    paths += [ROOT / f"prices/best_effort/{name}" for name in ("prices_usd.csv.gz", "actions.csv", "split_events.csv")]
    paths += [OUT / "ledgers" / f"{key}_{name}.csv.gz" for key in CASES for name in ("daily", "transactions")]
    paths += [OUT / "ledgers" / f"{key}_summary.json" for key in CASES]
    result["input_sha256"] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    output = OUT / "accuracy_data_audit.json"
    output.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({"output": str(output), "source_coverage": result["source_coverage"],
                      "peak_provisional_weights": {key: row["peak_provisional_weight"] for key, row in result["strategies"].items()}}, indent=2))


if __name__ == "__main__":
    main()
