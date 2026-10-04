"""Replay diagnostic cost and fund-tax stresses on the published study inputs.

Run: .venv/bin/python historical/checks/accuracy_sensitivities.py --workers 3
These scenarios are not calibrated estimates or confidence intervals.
"""
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import argparse
import hashlib
import json
import math
import multiprocessing
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/latest"
sys.path.insert(0, str(ROOT))
import run_tax_optimization_study as study

INPUTS = BASE_CONFIG = None
KEYS = ("baseline", *study.LEADERS)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stock_replay(task):
    spec, spread = task
    p, w, events, metadata, membership = INPUTS
    config = replace(BASE_CONFIG, **spec["config"], half_spread=spread)
    result = study.run_backtest(p, w, config, events, metadata, membership)
    summary, transactions = result.summary, result.transactions
    assert math.isclose(summary["contributions"], sum(config.contribution_amounts), abs_tol=1e-7, rel_tol=0)
    assert summary["contribution_count"] == len(config.contribution_dates) == 192
    assert result.daily.iloc[-1].holdings == {}
    assert result.lots.units.abs().lt(1e-8).all()
    def total(event, column, reason=None):
        mask = transactions.event.eq(event)
        if reason is not None:
            mask &= transactions.reason.eq(reason)
        return float(transactions.loc[mask, column].sum())
    cash = (total("contribution", "cash_eur") + total("dividend", "net_cash_eur")
            + total("sell", "net_proceeds_eur")
            + total("lot_disposal", "net_proceeds_eur", "mixed_merger")
            + total("lot_disposal", "net_proceeds_eur", "capital_distribution")
            + total("contingent_payment", "gross_proceeds_eur")
            - total("contingent_payment", "fees_eur")
            - total("buy", "cash_outlay_eur") - total("cgt_settlement", "tax_eur"))
    error = cash-summary["final_cash"]
    assert abs(error) < 1e-5, (spec["key"], spread, error)
    published = json.loads((OUT / f"ledgers/{spec['key']}_summary.json").read_text())
    if spread == 0:
        for field in ("final_cash", "total_tax", "transaction_costs"):
            assert math.isclose(summary[field], published[field], abs_tol=1e-6, rel_tol=0), (spec["key"], field)
    row = dict(asset="stock", key=spec["key"], scenario=f"extra_cost_{spread*10000:g}bp",
               extra_cost_per_side=spread, fx_fee=config.fx_fee, fund_tax_rate=None,
               deemed_disposal=None, contributions=summary["contributions"],
               final_cash=summary["final_cash"], total_tax=summary["total_tax"],
               transaction_costs=summary["transaction_costs"],
               difference_vs_published_same_strategy_eur=summary["final_cash"]-published["final_cash"],
               cash_reconciliation_error_eur=error)
    print(f"{row['scenario']} {spec['key']}: EUR{summary['final_cash']:,.2f}", flush=True)
    return row


def main():
    global INPUTS, BASE_CONFIG
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    manifest_path = OUT / "study_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for relative, expected in manifest["input_sha256"].items():
        assert sha256(ROOT / relative) == expected, f"Study input changed: {relative}"
    BASE_CONFIG = study.BacktestConfig(**manifest["base_configuration"])
    assert BASE_CONFIG.half_spread == 0
    nav_path = ROOT / "benchmark/issuer/cndx_nav_eur_2010-09-30_to_2026-09-30.csv"
    nav = pd.read_csv(nav_path, parse_dates=["date"]).set_index("date")
    prices = nav.loc[nav.index.weekday < 5, "nav_eur"]
    dates = tuple(day.strftime("%Y-%m-%d") for day in sorted(study.monthly_dates(prices)))
    contributions = study.build_cpi_schedule(dates, initial_amount=1000.)
    assert dates == tuple(BASE_CONFIG.contribution_dates)
    assert tuple(contributions.contribution_eur) == tuple(BASE_CONFIG.contribution_amounts)
    with TemporaryDirectory(prefix="nasdaq-sensitivity-inputs-") as temporary:
        p, w, events, metadata, membership, _ = study.prepare(audit_dir=temporary)
    overlay = pd.read_csv(ROOT / "inputs/corrected_membership/membership_alias_overlay.csv",
                          parse_dates=["effective_date", "available_date"])
    membership = pd.concat([membership, overlay], ignore_index=True).drop_duplicates(
        ["security_id", "effective_date"], keep="last")
    prepared_hash = hashlib.sha256(membership.to_csv(index=False).encode()).hexdigest()
    assert prepared_hash == manifest["prepared_membership_sha256"]
    INPUTS = (p[["date", "security_id", "price_eur", "dividend_eur", "tradable"]],
              w, events, metadata, membership)
    specs = [spec for spec in study.policies() if spec["key"] in KEYS]
    tasks = [(spec, spread) for spread in (0., .0005, .0025) for spec in specs]
    if args.workers == 1:
        rows = [stock_replay(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context("fork")) as pool:
            rows = list(pool.map(stock_replay, tasks))
    published_etf = json.loads((OUT / "etf/summary.json").read_text())
    etf_cases = [("fund_tax_38_dd_1", .38, True), ("fund_tax_41_dd_1", .41, True),
                 ("fund_tax_38_dd_0", .38, False),
                 ("fund_tax_41_before_2026_38_from_2026", lambda day: .41 if day.year < 2026 else .38, True)]
    for scenario, tax_rate, deemed_disposal in etf_cases:
        summary, _, _ = study.replay(prices, tax_rate=tax_rate, deemed_disposal=deemed_disposal,
                                     contribution_amounts=tuple(contributions.contribution_eur))
        assert math.isclose(summary["contributions"], sum(BASE_CONFIG.contribution_amounts), abs_tol=1e-7, rel_tol=0)
        assert summary["contribution_count"] == 192
        if tax_rate == .38 and deemed_disposal:
            for field in ("final_cash", "total_tax"):
                assert math.isclose(summary[field], published_etf[field], abs_tol=1e-6, rel_tol=0)
        rows.append(dict(asset="etf", key="etf", scenario=scenario,
                         extra_cost_per_side=0., fx_fee=0., fund_tax_rate=None if callable(tax_rate) else tax_rate,
                         deemed_disposal=deemed_disposal, contributions=summary["contributions"],
                         final_cash=summary["final_cash"], total_tax=summary["total_tax"], transaction_costs=0.,
                         difference_vs_published_same_strategy_eur=summary["final_cash"]-published_etf["final_cash"]))
        print(f"{rows[-1]['scenario']}: EUR{summary['final_cash']:,.2f}", flush=True)
    frame = pd.DataFrame(rows)
    for spread in (0., .0005, .0025):
        mask = frame.asset.eq("stock") & frame.extra_cost_per_side.eq(spread)
        baseline = frame.loc[mask & frame.key.eq("baseline"), "final_cash"].iloc[0]
        frame.loc[mask, "difference_vs_same_cost_baseline_eur"] = frame.loc[mask, "final_cash"]-baseline
        frame.loc[mask, "rank_among_four_stock_cases"] = frame.loc[mask, "final_cash"].rank(ascending=False, method="min")
    csv_path = OUT / "accuracy_sensitivities.csv"
    frame.to_csv(csv_path, index=False)
    code_paths = [Path(__file__), *(ROOT / relative for relative in manifest["code_sha256"])]
    metadata = dict(
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        classification="DIAGNOSTIC_STRESS_SCENARIOS_NOT_CALIBRATED_ESTIMATES",
        period=manifest["period"], study_manifest_sha256=sha256(manifest_path),
        input_sha256=manifest["input_sha256"], prepared_membership_sha256=prepared_hash,
        code_sha256={str(path.relative_to(ROOT)): sha256(path) for path in code_paths},
        results_sha256=sha256(csv_path), stock_replays=len(tasks), etf_replays=len(etf_cases),
        stock_identity_cases=list(KEYS), identity_tolerance_eur=1e-6,
        maximum_cash_reconciliation_error_eur=float(frame.cash_reconciliation_error_eur.abs().max()),
        dated_fund_rate_sources=[
            "https://www.revenue.ie/en/tax-professionals/tdm/income-tax-capital-gains-tax-corporation-tax/part-27/27-01a-02.pdf",
            "https://www.revenue.ie/en/tax-professionals/ebrief/2026/no-0162026.aspx",
        ],
        assumptions=[
            "All prepared inputs, contribution dates and policy rules match the published study.",
            "Stock stresses change only half_spread. The 0.15% non-euro FX fee stays unchanged.",
            "The extra cost enters the shared model cost rate, including costed corporate cash receipts and final sales.",
            "The 5 bp and 25 bp costs are diagnostic stresses, not measured spreads, slippage or confidence intervals.",
            "ETF stresses retain the issuer NAV and zero explicit investor transaction costs.",
            "The 38% and 41% fund tax rates remain constant across the full period. They are not historical tax schedules.",
            "The dated ETF rate control uses 41% before 2026 and 38% from 2026. This study has no taxable fund events before 2018.",
            "The dated rate control is a partial historical rate check, not a full reconstruction of historical law or payment dates.",
            "No deemed disposal is a hypothetical timing control. Final fund tax still applies.",
            "These checks do not validate missing source data, historical broker access, tax law or strategy selection.",
        ])
    (OUT / "accuracy_sensitivities.json").write_text(json.dumps(metadata, indent=2)+"\n")


if __name__ == "__main__":
    main()
