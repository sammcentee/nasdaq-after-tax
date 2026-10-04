"""Separate execution-mode and December-calendar effects in the weekly case.

Run: .venv/bin/python historical/checks/execution_timing_checks.py
The two new replays share corrected inputs. The current main case is the third
control. Calendar dates are fixed for operational reasons, not selected by return.
"""
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path
import hashlib
import json
import multiprocessing
import sys
import tempfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/latest"
sys.path[:0] = [str(ROOT), str(ROOT / "model")]
from direct_stock_backtest import BacktestConfig, run_backtest
from run_tax_optimization_study import policies, scheduled_reviews
from study_inputs import prepare

INPUTS = None
ORIGINAL_CASH = 998424.9672303945
ORIGINAL_COMMIT = "86fa591672e27ace812bec7d2922751e53a32714"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def simulate(case):
    name, config = case
    prices, weights, events, metadata, membership = INPUTS
    result = run_backtest(prices, weights, config, events, metadata, membership)
    transactions = result.transactions

    def total(event, column, reason=None):
        mask = transactions.event.eq(event)
        if reason is not None:
            mask &= transactions.reason.eq(reason)
        return float(transactions.loc[mask, column].sum()) if column in transactions else 0.

    cash = (total("contribution", "cash_eur") + total("dividend", "net_cash_eur")
            + total("sell", "net_proceeds_eur")
            + total("lot_disposal", "net_proceeds_eur", "mixed_merger")
            + total("lot_disposal", "net_proceeds_eur", "capital_distribution")
            + total("contingent_payment", "gross_proceeds_eur") - total("contingent_payment", "fees_eur")
            - total("buy", "cash_outlay_eur") - total("cgt_settlement", "tax_eur"))
    assert abs(cash-result.summary["final_cash"]) < 1e-5
    assert result.daily.iloc[-1].holdings == {} and (result.lots.units.abs() < 1e-8).all()
    assert result.summary["pending_order_count"] == result.summary["unpaid_dividend_receivable_eur"] == 0
    if config.execution_mode == "next_session":
        fills = transactions.loc[transactions.event.isin(["buy", "sell"]) & transactions.order_id.notna()]
        assert (fills.signal_date < fills.fill_date).all()
    return dict(name=name, configuration=asdict(config), summary=result.summary,
                cash_reconciliation_error_eur=cash-result.summary["final_cash"])


def main():
    global INPUTS
    manifest_path = OUT / "study_manifest.json"
    reference_path = OUT / "ledgers/weekly_annual_summary.json"
    manifest, reference = (json.loads(path.read_text()) for path in (manifest_path, reference_path))
    weekly = next(policy for policy in policies() if policy["key"] == "weekly_annual")
    base = BacktestConfig(**dict(manifest["base_configuration"], **weekly["config"]))
    assert json.loads(json.dumps(asdict(base))) == reference["configuration"]
    assert base.execution_mode == "next_session"
    december_month_end = tuple(day for day in scheduled_reviews("monthly") if day[5:7] == "12")
    assert len(december_month_end) == 16
    next_month_end = replace(base, gain_review_dates=december_month_end)
    same_month_end = replace(next_month_end, execution_mode="same_close")
    assert {key for key in asdict(base) if asdict(base)[key] != asdict(next_month_end)[key]} == {"gain_review_dates"}
    assert {key for key in asdict(next_month_end) if asdict(next_month_end)[key] != asdict(same_month_end)[key]} == {"execution_mode"}
    hashes = {**manifest["input_sha256"], **manifest["code_sha256"]}
    for name, expected in hashes.items():
        assert digest(ROOT / name) == expected, f"Stale study source: {name}"
    for path in (manifest_path, reference_path, Path(__file__)):
        hashes[str(path.relative_to(ROOT))] = digest(path)
    with tempfile.TemporaryDirectory(prefix="nasdaq-timing-inputs-") as temporary:
        prices, weights, events, metadata, membership, _ = prepare(temporary)
    overlay = pd.read_csv(ROOT / "inputs/corrected_membership/membership_alias_overlay.csv",
                          parse_dates=["effective_date", "available_date"])
    membership = pd.concat([membership, overlay], ignore_index=True).drop_duplicates(
        ["security_id", "effective_date"], keep="last")
    prepared_membership_hash = hashlib.sha256(membership.to_csv(index=False).encode()).hexdigest()
    assert prepared_membership_hash == manifest["prepared_membership_sha256"]
    INPUTS = prices[["date", "security_id", "price_eur", "dividend_eur", "tradable"]], weights, events, metadata, membership
    cases = [("same_close_december_month_end", same_month_end),
             ("next_session_december_month_end", next_month_end)]
    with ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context("fork")) as pool:
        records = list(pool.map(simulate, cases))
    records.append(dict(name="next_session_december_15", configuration=asdict(base), summary=reference,
                        cash_reconciliation_error_eur=reference["cash_reconciliation_error_eur"], reused_main_result=True))
    values = [row["summary"]["final_cash"] for row in records]
    differences = dict(corrected_inputs_and_fees_vs_original_eur=values[0]-ORIGINAL_CASH,
                       execution_mode_at_month_end_eur=values[1]-values[0],
                       december_15_vs_month_end_next_session_eur=values[2]-values[1],
                       combined_main_vs_original_eur=values[2]-ORIGINAL_CASH)
    assert abs(sum(list(differences.values())[:3])-differences["combined_main_vs_original_eur"]) < 1e-7
    rows = [dict(scenario=row["name"], execution_mode=row["configuration"]["execution_mode"],
                 final_cash=row["summary"]["final_cash"], total_tax=row["summary"]["total_tax"],
                 transaction_costs=row["summary"]["transaction_costs"],
                 gain_harvest_sales=row["summary"]["gain_harvest_sales"],
                 exemption_used_total_eur=row["summary"]["cgt_exemption_used_total_eur"],
                 cash_reconciliation_error_eur=row["cash_reconciliation_error_eur"]) for row in records]
    destination = OUT / "execution_timing.csv"
    pd.DataFrame(rows).to_csv(destination, index=False)
    result = dict(scope="Matched execution-mode and annual-review-calendar controls on corrected inputs",
        source_sha256=hashes, prepared_membership_sha256=prepared_membership_hash,
        results_sha256=digest(destination), all_checks_passed=True, cases=records,
        previous_published_result=dict(commit=ORIGINAL_COMMIT, final_cash=ORIGINAL_CASH,
                                      path="historical/results/latest/ledgers/weekly_annual_summary.json"),
        differences_eur=differences,
        limitations=[
            "Execution mode changes fill dates, later use of proceeds, actual-price tax deviations, and order cancellations. It is not only a price substitution.",
            "The first difference combines corrected dividends and compulsory fees. It does not separate those corrections.",
            "December 15 leaves time for execution within the tax year. Its selection did not use these control returns and does not establish an optimal date.",
            "All controls share provisional market and tax inputs. The current main result is reused rather than replayed here.",
        ])
    (OUT / "execution_timing.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps(dict(final_cash=values, differences_eur=differences, output=str(destination)), indent=2))


if __name__ == "__main__":
    main()
