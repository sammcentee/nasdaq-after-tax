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
# The issuer reports confirm these five payments. Other corrections are separate.
DIVIDENDS = [
    ("yahoo:CDK", "2020-09-01", "2020-09-30", .15, CDK_SOURCE),
    ("yahoo:CDK", "2020-12-01", "2020-12-30", .15, CDK_SOURCE),
    ("yahoo:CDK", "2021-03-08", "2021-03-30", .15, CDK_SOURCE),
    ("yahoo:CDK", "2021-06-21", "2021-06-30", .15, CDK_SOURCE),
    ("yahoo:LOGM", "2018-08-08", "2018-08-24", .30, LOGM_SOURCE),
]


def audit_verified_dividends(daily, transactions, dividends, fx):
    """Check every sourced entitlement against prior-session holdings and cash."""
    entries = transactions.loc[transactions.event.eq("dividend_entitlement")]
    payments = transactions.loc[transactions.event.eq("dividend")
                                & transactions.security_id.isin(dividends.security_id)]
    assert payments.dividend_id.notna().all(), "Unkeyed dividend may duplicate a sourced payment"
    expected_ids = set(dividends.dividend_id)
    assert set(entries.dividend_id) == expected_ids
    assert set(payments.dividend_id) == expected_ids
    assert not entries.dividend_id.duplicated().any()
    assert not payments.dividend_id.duplicated().any()
    entries = entries.set_index("dividend_id")
    payments = payments.set_index("dividend_id")
    rows = []
    residuals = []
    for source in dividends.itertuples():
        entry, payment = entries.loc[source.dividend_id], payments.loc[source.dividend_id]
        assert entry.security_id == payment.security_id == source.security_id
        assert pd.Timestamp(entry.date) == source.entitlement_date
        assert pd.Timestamp(payment.date) == source.payment_session
        assert pd.Timestamp(payment.entitlement_date) == source.entitlement_date
        earlier = daily.loc[daily.date.lt(source.entitlement_date)]
        prior_units = earlier.iloc[-1].holdings.get(source.security_id, 0.) if len(earlier) else 0.
        assert prior_units >= 0
        expected_entitlement = prior_units*source.cash_usd_per_share/fx.loc[source.entitlement_date]
        expected_cash = prior_units*source.cash_usd_per_share/fx.loc[source.payment_session]
        differences = [entry.units-prior_units, payment.units-prior_units,
            entry.gross_entitlement_eur-expected_entitlement, payment.gross_eur-expected_cash,
            payment.net_cash_eur+payment.tax_eur-payment.gross_eur,
            payment.withholding_eur+payment.irish_top_up_eur-payment.tax_eur]
        assert all(abs(value) < 1e-8 for value in differences), (source.dividend_id, differences)
        residuals.extend(abs(value) for value in differences)
        rows.append(dict(dividend_id=source.dividend_id, security_id=source.security_id,
            entitlement_date=str(source.entitlement_date.date()),
            payment_date=str(source.payment_date.date()), payment_session=str(source.payment_session.date()),
            payment_evidence=source.payment_evidence, ex_date_quality=source.ex_date_quality,
            prior_session_units=float(prior_units), recorded_gross_eur=float(payment.gross_eur),
            recorded_net_cash_eur=float(payment.net_cash_eur), recorded_tax_eur=float(payment.tax_eur)))
    return dict(source_schedules=len(dividends), entitlement_rows=len(entries), payment_rows=len(payments),
        positive_entitlements=sum(row["prior_session_units"] > 0 for row in rows),
        zero_entitlements=sum(row["prior_session_units"] == 0 for row in rows),
        recorded_gross_eur=sum(row["recorded_gross_eur"] for row in rows),
        recorded_net_cash_eur=sum(row["recorded_net_cash_eur"] for row in rows),
        recorded_tax_eur=sum(row["recorded_tax_eur"] for row in rows),
        maximum_arithmetic_residual=max(residuals, default=0.), all_schedules_checked_exactly_once=True,
        payments=rows)


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
        p, w, events, _, _, _ = prepare(audit_dir)
        dividends = pd.read_csv(Path(audit_dir) / "verified_dividends_prepared.csv",
            parse_dates=["entitlement_date", "payment_date", "payment_session"])
    share_changes = events.loc[events.event_type.isin(
        ["split", "stock_exchange", "spinoff", "mixed_merger", "cash_merger"])]
    for source in dividends.itertuples():
        assert not (share_changes.date.eq(source.entitlement_date)
                    & (share_changes.security_id.eq(source.security_id)
                       | share_changes.successor_id.eq(source.security_id))).any()
    snapshots = sorted(set(zip(pd.to_datetime(w.effective_date), pd.to_datetime(w.available_date))))
    for row in coverage.itertuples():
        day = pd.Timestamp(row.purchase_date)
        latest = max(pair for pair in snapshots if pair[0] <= day and pair[1] < day)
        assert latest == (pd.Timestamp(row.source_effective_date), pd.Timestamp(row.source_available_date))
    provisional = p.loc[~p.tradable]
    marks = {day: dict(zip(group.security_id, group.price_eur))
             for day, group in provisional.groupby("date")}
    fx = pd.read_csv(ROOT / "benchmark/issuer/cndx_nav_eur.csv", parse_dates=["date"])
    fx = fx.drop_duplicates("date").set_index("date").usd_per_eur
    calendar = pd.DatetimeIndex(sorted(p.date.unique()))
    fx = fx.reindex(fx.index.union(calendar)).sort_index().ffill().reindex(calendar)
    result = {
        "classification": "DESCRIPTIVE_DATA_LIMITS_NOT_AN_ERROR_BOUND",
        "broker_cash_payment_fee_source": "https://helpcentre.trading212.com/hc/en-us/articles/11669719976093-What-is-a-multi-currency-account",
        "metric_definitions": {
            "coverage": "Cached source-coverage audit on the 192 scheduled contribution dates; equal weight per date, not invested capital. Dates and latest eligible snapshots are checked against current prepared inputs.",
            "provisional_weight": "Value of held securities with an explicit nontradable prepared mark divided by same-day value_eur, which includes cash before CGT reserve deduction. Mean includes every saved daily row, including final liquidation. Other stale quotes and contingent rights are excluded.",
            "dividend_examples": "Five issuer payments must appear exactly once in the corrected ledgers. Units remain positive and constant from seven calendar days before record date through payment. Gross EUR uses payment-date ECB FX. The check does not establish complete dividends for other securities.",
            "verified_dividend_corpus": "All 42 sourced CDK and LOGM schedules, including zero holdings, must have one entitlement and one payment. Entitlement units are checked against previous-session holdings. These securities have no same-day share-changing action on the derived ex-dates. Gross EUR uses each event's contemporary ECB FX, forward-filled as in preparation. This verifies ledger use of the corpus, not issuer dates or completeness of dividends for other securities.",
            "mandatory_cash_fx_fees": "Recorded cash-merger, contingent-payment, mixed-merger and capital-distribution fees. Corrected lot rows must contain explicit fee amounts. This amount excludes later tax and reinvestment effects.",
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
        "verified_dividend_sources": {
            "schedules": len(dividends),
            "issuer_report_confirmed_payments": int(dividends.payment_evidence.eq("issuer_report_confirms_payment").sum()),
            "issuer_declared_schedules_only": int(dividends.payment_evidence.eq("issuer_declared_schedule_only").sum()),
            "derived_ex_dates": int(dividends.ex_date_quality.eq("derived_Nasdaq_11140_regular_distribution").sum()),
            "securities": dividends.groupby("security_id").size().to_dict(),
        },
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
        cash_actions = transactions.event.eq("sell") & transactions.reason.eq("cash_merger")
        cash_actions |= transactions.event.eq("contingent_payment")
        mixed = transactions.event.eq("lot_disposal") & transactions.reason.isin(["mixed_merger", "capital_distribution"])
        assert transactions.loc[mixed, "fees_eur"].notna().all(), "Rerun corrected ledgers with explicit corporate cash fees"
        mandatory_fees = float(transactions.loc[cash_actions | mixed, "fees_eur"].sum())
        assert abs(mandatory_fees) < 1e-9, "Corporate cash receipts must not incur trade FX fees"
        examples = []
        for security, record, payment, amount, source in DIVIDENDS:
            window = daily.loc[daily.date.between(pd.Timestamp(record)-pd.Timedelta(days=7), pd.Timestamp(payment))]
            units = window.holdings.map(lambda held: held.get(security, 0.))
            assert len(units) and units.min() > 0 and units.nunique() == 1
            recorded = transactions.loc[transactions.event.eq("dividend") & transactions.security_id.eq(security)
                                        & transactions.date.eq(payment)]
            expected = float(units.iloc[0]*amount/fx.loc[pd.Timestamp(payment)])
            assert len(recorded) == 1, (key, security, payment, "Missing or duplicate verified dividend")
            assert abs(float(recorded.gross_eur.sum())-expected) < 1e-8
            examples.append(dict(security_id=security, record_date=record, payment_date=payment,
                dividend_usd_per_share=amount, units=float(units.iloc[0]),
                units_constant_in_entitlement_window=True,
                expected_gross_eur_at_payment_fx=expected,
                recorded_gross_eur=float(recorded.gross_eur.sum()), source=source))
        buys = transactions.loc[transactions.event.eq("buy")]
        result["strategies"][key] = {
            "daily_rows": len(daily),
            "days_with_explicit_provisional_value": int(daily.provisional_value_eur.gt(0).sum()),
            "peak_provisional_weight": float(peak.provisional_weight),
            "peak_weight_date": str(peak.date.date()),
            "provisional_value_eur_at_peak_weight": float(peak.provisional_value_eur),
            "maximum_provisional_value_eur": float(daily.provisional_value_eur.max()),
            "mean_provisional_weight": float(daily.provisional_weight.mean()),
            "known_dividend_examples": examples,
            "five_examples_recorded_gross_eur": sum(row["recorded_gross_eur"] for row in examples),
            "five_examples_verified_exactly_once": True,
            "verified_dividend_corpus": audit_verified_dividends(daily, transactions, dividends, fx),
            "mandatory_cash_fx_fees_eur": mandatory_fees,
            "buy_count": len(buys),
            "buy_count_below_one_share": int(buys.units.lt(1).sum()),
        }
    paths = [Path(__file__), ROOT / "study_inputs.py", coverage_path, OUT / "contribution_schedule.csv",
             ROOT / "benchmark/issuer/cndx_nav_eur.csv", ROOT / "benchmark/indexes/NASDAQ100.csv"]
    paths += [ROOT / f"inputs/best_effort/{name}.csv" for name in ("best_effort_weights", "membership", "metadata")]
    paths += [ROOT / f"prices/best_effort/{name}" for name in ("prices_usd.csv.gz", "actions.csv", "split_events.csv")]
    paths += [ROOT / f"inputs/{name}" for name in ("verified_dividends.csv", "verified_dividends_provenance.json")]
    paths += [OUT / "ledgers" / f"{key}_{name}.csv.gz" for key in CASES for name in ("daily", "transactions")]
    paths += [OUT / "ledgers" / f"{key}_summary.json" for key in CASES]
    result["input_sha256"] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    output = OUT / "accuracy_data_audit.json"
    output.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({"output": str(output), "source_coverage": result["source_coverage"],
                      "peak_provisional_weights": {key: row["peak_provisional_weight"] for key, row in result["strategies"].items()}}, indent=2))


if __name__ == "__main__":
    main()
