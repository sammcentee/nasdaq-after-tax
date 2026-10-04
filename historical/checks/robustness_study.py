"""Replay fixed rules across cohorts and a delayed-weight diagnostic.

Run after the main study: .venv/bin/python historical/checks/robustness_study.py --workers 3
All cohorts reuse retrospectively selected rules. None is an out-of-sample test.
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
from assess_accuracy import money_weighted_return
from direct_stock_backtest import DataIntegrityError

INPUTS = BASE_CONFIG = SCHEDULE = None
KEYS = ("baseline", *study.LEADERS)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cohorts(prices, stock_dates):
    dates = prices.index.intersection(pd.DatetimeIndex(stock_dates)).sort_values()
    boundaries = {year: dates[dates <= pd.Timestamp(f"{year}-09-30")][-1]
                  for year in (2010, 2015, 2018, 2020, 2021, 2025, 2026)}
    return [dict(cohort=f"{years}y_{first}_{last}", nominal_years=years,
                 start=str(boundaries[first].date()), end=str(boundaries[last].date()))
            for first, last, years in ((2010, 2026, 16), (2010, 2018, 8), (2018, 2026, 8),
                                       (2010, 2015, 5), (2015, 2020, 5), (2020, 2025, 5),
                                       (2015, 2026, 11), (2021, 2026, 5))]


def contributions(cohort):
    return SCHEDULE.loc[(SCHEDULE.date >= cohort["start"]) & (SCHEDULE.date < cohort["end"])].copy()


def row_summary(cohort, key, lag, summary, deposits, scenario="fixed_rule"):
    scheduled = contributions(cohort)
    assert len(deposits) == len(scheduled) == cohort["nominal_years"]*12
    assert tuple(deposits.cash_eur) == tuple(scheduled.contribution_eur)
    assert math.isclose(summary["contributions"], scheduled.contribution_eur.sum(), abs_tol=1e-7, rel_tol=0)
    actual_dates = pd.to_datetime(deposits.date).reset_index(drop=True)
    mismatch = actual_dates.ne(pd.to_datetime(scheduled.date).reset_index(drop=True))
    return dict(**cohort, key=key, scenario=scenario, status="COMPLETE", weight_availability_lag_business_days=lag,
                contribution_count=len(deposits), contributions_eur=summary["contributions"],
                initial_contribution_eur=float(scheduled.contribution_eur.iloc[0]),
                final_contribution_eur=float(scheduled.contribution_eur.iloc[-1]),
                contribution_date_mismatch_count=int(mismatch.sum()),
                final_cash_eur=summary["final_cash"], total_tax_eur=summary["total_tax"],
                transaction_costs_eur=summary.get("transaction_costs", 0.),
                money_weighted_annual_return=money_weighted_return(deposits, cohort["end"], summary["final_cash"]))


def stock_replay(task):
    cohort, spec, lag, scenario = task
    schedule = contributions(cohort)
    policy = dict(spec["config"])
    if scenario == "quarterly_target_rebalance":
        policy["rebalance_review_dates"] = study.scheduled_reviews("quarterly")
    config = replace(BASE_CONFIG, **policy, start=cohort["start"], end=cohort["end"],
                     contribution_dates=tuple(schedule.date), contribution_amounts=tuple(schedule.contribution_eur),
                     execution_mode="next_session")
    reviews = {}
    for field in ("exit_review_dates", "harvest_review_dates", "gain_review_dates", "rebalance_review_dates"):
        values = getattr(config, field)
        if values is not None:
            reviews[field] = tuple(day for day in values if config.start <= day <= config.end)
    config = replace(config, **reviews)
    p, w, events, metadata, membership = INPUTS
    weights = w.copy()
    weights["effective_date"] = pd.to_datetime(weights.effective_date)
    weights["available_date"] = pd.to_datetime(weights.available_date)
    if lag:
        weights["available_date"] += pd.offsets.BusinessDay(lag)
    try:
        result = study.run_backtest(p, weights, config, events, metadata, membership)
    except DataIntegrityError as error:
        if not str(error).startswith(("Fresh final liquidation price required:", "Unpaid dividend receivable at final liquidation")):
            raise
        print(f"{cohort['cohort']} {spec['key']} {scenario} lag={lag}: DATA_UNAVAILABLE: {error}", flush=True)
        return dict(**cohort, key=spec["key"], scenario=scenario, weight_availability_lag_business_days=lag,
                    status="DATA_UNAVAILABLE", unavailable_reason=str(error))
    t = result.transactions
    assert result.daily.iloc[-1].holdings == {}
    assert result.lots.units.abs().lt(1e-8).all()
    def total(event, column, reason=None):
        if column not in t:
            return 0.
        mask = t.event.eq(event)
        if reason is not None:
            mask &= t.reason.eq(reason)
        return float(t.loc[mask, column].sum())
    cash = (total("contribution", "cash_eur") + total("dividend", "net_cash_eur")
            + total("sell", "net_proceeds_eur")
            + total("lot_disposal", "net_proceeds_eur", "mixed_merger")
            + total("lot_disposal", "net_proceeds_eur", "capital_distribution")
            + total("contingent_payment", "gross_proceeds_eur")-total("contingent_payment", "fees_eur")
            - total("buy", "cash_outlay_eur")-total("cgt_settlement", "tax_eur"))
    error = cash-result.summary["final_cash"]
    assert abs(error) < 1e-5, (cohort["cohort"], spec["key"], lag, error)
    row = row_summary(cohort, spec["key"], lag, result.summary,
                      t.loc[t.event.eq("contribution"), ["date", "cash_eur"]], scenario)
    row["cash_reconciliation_error_eur"] = error
    before = result.daily.iloc[-2]
    holdings = pd.Series(before.holdings, dtype=float)
    marks = p.loc[p.date.le(before.date) & p.security_id.isin(holdings.index)].dropna(subset=["price_eur"])
    marks = marks.sort_values("date").groupby("security_id").tail(1).set_index("security_id").price_eur
    assert holdings.index.isin(marks.index).all()
    values = holdings*marks.reindex(holdings.index)
    assert abs(values.sum()+before.cash_eur+before.dividend_receivable_eur-before.value_eur) < 1e-5
    known = weights.loc[weights.effective_date.le(before.date) & weights.available_date.lt(before.date)]
    latest = known.sort_values(["effective_date", "available_date"]).iloc[-1]
    targets = known.loc[known.effective_date.eq(latest.effective_date) & known.available_date.eq(latest.available_date)]
    targets = targets.loc[targets.security_id.ne(config.cash_target_security_id)]
    row.update(exposure_date=str(before.date.date()),
               prefinal_top10_share_of_stock_value=float(values.nlargest(10).sum()/values.sum()),
               last_known_target_top10_weight=float(targets.weight.nlargest(10).sum()),
               target_effective_date=str(latest.effective_date.date()), target_available_date=str(latest.available_date.date()),
               mean_outside_weight=float(result.daily.out_of_index_weight.iloc[:-1].mean()),
               mean_unknown_weight=float(result.daily.unknown_membership_weight.iloc[:-1].mean()),
               rebalance_sale_count=result.summary["rebalance_sale_count"])
    print(f"{cohort['cohort']} {spec['key']} {scenario} lag={lag}: EUR{row['final_cash_eur']:,.2f}", flush=True)
    return row


def main():
    global INPUTS, BASE_CONFIG, SCHEDULE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    manifest_path = OUT / "study_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest_hash = digest(manifest_path)
    for relative, expected in {**manifest["input_sha256"], **manifest["code_sha256"]}.items():
        assert digest(ROOT / relative) == expected, f"Regenerate the main study for changed input or code: {relative}"
    assert manifest["base_configuration"].get("execution_mode") == "next_session", "Regenerate the main study with delayed execution"
    BASE_CONFIG = study.BacktestConfig(**manifest["base_configuration"])
    assert BASE_CONFIG.half_spread == 0 and BASE_CONFIG.rebalance_review_dates is None
    code_paths = [Path(__file__), ROOT / "checks/assess_accuracy.py", ROOT / "checks/audit_ledgers.py",
                  *(ROOT / name for name in manifest["code_sha256"])]
    code_hashes = {str(path.relative_to(ROOT)): digest(path) for path in code_paths}
    nav = pd.read_csv(ROOT / "benchmark/issuer/cndx_nav_eur_2010-09-30_to_2026-09-30.csv",
                      parse_dates=["date"]).set_index("date")
    prices = nav.loc[nav.index.weekday < 5, "nav_eur"]
    dates = tuple(day.strftime("%Y-%m-%d") for day in sorted(study.monthly_dates(prices)))
    SCHEDULE = study.build_cpi_schedule(dates, initial_amount=1000.)
    assert tuple(SCHEDULE.contribution_eur) == tuple(BASE_CONFIG.contribution_amounts)
    SCHEDULE["date"] = pd.to_datetime(SCHEDULE.date).dt.strftime("%Y-%m-%d")
    with TemporaryDirectory(prefix="nasdaq-robustness-inputs-") as temporary:
        p, w, events, metadata, membership, _ = study.prepare(audit_dir=temporary)
    overlay = pd.read_csv(ROOT / "inputs/corrected_membership/membership_alias_overlay.csv",
                          parse_dates=["effective_date", "available_date"])
    membership = pd.concat([membership, overlay], ignore_index=True).drop_duplicates(
        ["security_id", "effective_date"], keep="last")
    prepared_hash = hashlib.sha256(membership.to_csv(index=False).encode()).hexdigest()
    assert prepared_hash == manifest["prepared_membership_sha256"]
    INPUTS = (p[["date", "security_id", "price_eur", "dividend_eur", "tradable"]], w, events, metadata, membership)
    periods = cohorts(prices, p.date.unique())
    specs = [spec for spec in study.policies() if spec["key"] in KEYS]
    tasks = [(cohort, spec, 0, "fixed_rule") for cohort in periods for spec in specs]
    tasks.extend((periods[0], spec, 5, "fixed_rule") for spec in specs)
    tasks.extend((periods[0], spec, 0, "quarterly_target_rebalance") for spec in specs
                 if spec["key"] in ("baseline", "weekly_annual"))
    if args.workers == 1:
        rows = [stock_replay(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context("fork")) as pool:
            rows = list(pool.map(stock_replay, tasks))
    for cohort in periods:
        schedule = contributions(cohort)
        actual = tuple(day.strftime("%Y-%m-%d") for day in sorted(study.monthly_dates(prices, cohort["start"], cohort["end"])))
        assert actual == tuple(schedule.date)
        summary, ledger, _ = study.replay(prices, tax_rate=.38, deemed_disposal=True,
                                         start=cohort["start"], end=cohort["end"], contribution_first=True,
                                         contribution_amounts=tuple(schedule.contribution_eur))
        deposits = ledger.loc[ledger.event.eq("contribution"), ["date", "cash"]].rename(columns={"cash": "cash_eur"})
        rows.append(row_summary(cohort, "etf", 0, summary, deposits))
    frame = pd.DataFrame(rows)
    etfs = frame.loc[frame.key.eq("etf")].set_index("cohort").final_cash_eur
    frame["difference_vs_cohort_etf_eur"] = frame.final_cash_eur-frame.cohort.map(etfs)
    for _, group in frame.groupby(["cohort", "weight_availability_lag_business_days", "scenario"]):
        baseline = group.loc[group.key.eq("baseline"), "final_cash_eur"].iloc[0]
        frame.loc[group.index, "difference_vs_matched_stock_baseline_eur"] = group.final_cash_eur-baseline
        stocks = group.loc[group.key.ne("etf") & group.status.eq("COMPLETE")]
        if len(stocks) == 4:
            frame.loc[stocks.index, "rank_among_four_stock_cases"] = stocks.final_cash_eur.rank(ascending=False, method="min")
    full = frame.loc[frame.cohort.eq(periods[0]["cohort"]) & frame.weight_availability_lag_business_days.eq(0)
                     & frame.scenario.eq("fixed_rule")]
    assert full.status.eq("COMPLETE").all(), "The full reference must reproduce the main study"
    for row in full.itertuples():
        path = OUT / ("etf/summary.json" if row.key == "etf" else f"ledgers/{row.key}_summary.json")
        published = json.loads(path.read_text())
        assert math.isclose(row.final_cash_eur, published["final_cash"], abs_tol=1e-6, rel_tol=0), row.key
    lagged = frame.weight_availability_lag_business_days.eq(5)
    frame.loc[lagged, "difference_vs_original_availability_eur"] = (
        frame.loc[lagged, "final_cash_eur"]-frame.loc[lagged, "key"].map(full.set_index("key").final_cash_eur))
    rebalanced = frame.scenario.eq("quarterly_target_rebalance")
    frame.loc[rebalanced, "difference_vs_unrebalanced_same_strategy_eur"] = (
        frame.loc[rebalanced, "final_cash_eur"]-frame.loc[rebalanced, "key"].map(full.set_index("key").final_cash_eur))
    for relative, expected in {**manifest["input_sha256"], **code_hashes}.items():
        assert digest(ROOT / relative) == expected, f"Input or code changed during replay: {relative}"
    assert digest(manifest_path) == manifest_hash, "Study manifest changed during replay"
    csv_path = OUT / "robustness.csv"
    frame.to_csv(csv_path, index=False)
    metadata = dict(generated_at_utc=datetime.now(timezone.utc).isoformat(),
                    classification="RETROSPECTIVE_FIXED_RULE_ROBUSTNESS_NOT_OUT_OF_SAMPLE",
                    stock_execution_mode="next_session", etf_contribution_first=True,
                    cohorts=periods, stock_replays=len(tasks), etf_replays=len(periods),
                    unavailable_stock_cases=int(frame.status.eq("DATA_UNAVAILABLE").sum()),
                    study_manifest_sha256=manifest_hash, input_sha256=manifest["input_sha256"],
                    prepared_membership_sha256=prepared_hash, code_sha256=code_hashes,
                    results_sha256=digest(csv_path), assumptions=[
        "All rules were selected with knowledge of the full historical period. These cohorts are retrospective diagnostics, not holdouts.",
        "The two eight-year cohorts and three five-year cohorts have separate contribution intervals within each set. The sets overlap each other.",
        "The five-year set ends in September 2025. It excludes the last year of the full reference.",
        "Each boundary is the last common stock and weekday NAV date on or before September 30. Year labels are nominal horizons.",
        "Two extra cohorts start in 2015 and 2021 and end in 2026, when the main study has supported final quotes. This choice reflects data availability, not performance.",
        "Common-end cohorts overlap and share the same final market date. They are not independent samples.",
        "DATA_UNAVAILABLE records retain failed attempts with missing executable final prices or unsettled dividends. They contain no proxy terminal wealth.",
        "Each cohort starts with an empty portfolio and ends with complete stock liquidation and final fund tax.",
        "Contributions retain the original CPI schedule. Later cohorts start above EUR1000. Amounts match across strategies within each cohort.",
        "XIRR uses actual contribution receipt dates, final cash and 365.25 days per year. Date mismatch counts compare receipt dates with the intended schedule.",
        "The lag control adds five Monday-to-Friday business days to weight availability dates. It excludes holiday calendars and leaves membership notices unchanged.",
        "The lag control does not establish the true publication dates of source weights.",
        "Two full-period controls add quarterly target rebalancing to the baseline and weekly combined rules. They use actual disposal tax and existing quote and repurchase restrictions.",
        "Rebalancing follows the same stale source weights and leaves unresolved exposures. These controls are not strict Nasdaq-100 replicas.",
        "Prefinal top-ten shares use stock value alone. Target top-ten shares retain the target portfolio denominator, including target cash. They count share classes, not companies.",
        "Stock tax rates and fees and the 38% ETF rate remain fixed comparison assumptions for every cohort.",
        "All values are nominal euros. Rankings and rates are historical results, not probabilities or forecasts.",
    ])
    (OUT / "robustness.json").write_text(json.dumps(metadata, indent=2)+"\n")


if __name__ == "__main__":
    main()
