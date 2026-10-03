"""Replay selected strategies, underperformers and matched tax controls.

Run: .venv/bin/python historical/run_tax_optimization_study.py --workers 3
Uses the latest corrected cached corpus. No account access or broker orders.
"""
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
from pathlib import Path
import argparse
import hashlib
import json
import multiprocessing
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results/latest"
LEDGERS = OUT / "ledgers"
sys.path.insert(0, str(ROOT / "model"))
from direct_stock_backtest import BacktestConfig, run_backtest
from etf_backtest import replay
from study_inputs import prepare

INPUTS = BASE_CONFIG = None
LEADERS = ("monthly_tlh", "monthly_hybrid", "weekly_annual")
UNDERPERFORMERS = ("any_loss", "retain_gains", "monthly_gains")


def scheduled_reviews(frequency):
    if frequency == "weekly":
        return tuple(d.strftime("%Y-%m-%d") for d in pd.date_range("2010-09-30", "2026-09-30", freq="W-FRI"))
    months = {"monthly": range(1, 13), "quarterly": (3, 6, 9, 12), "annual": (12,)}[frequency]
    dates = []
    for period in pd.period_range("2010-09", "2026-09", freq="M"):
        if period.month in months:
            day = period.end_time.normalize()
            while day.weekday() >= 5:
                day -= pd.Timedelta(days=1)
            dates.append(str(day.date()))
    return tuple(dates)


def policies():
    exits = dict(exit_policy="tax_budget", exit_review_dates=scheduled_reviews("quarterly"),
                 exit_annual_tax_budget_eur=0., harvest=False)
    annual = dict(gain_harvest=True, gain_review_dates=scheduled_reviews("annual"),
                  gain_harvest_scope="all", gain_harvest_reinvest="same_security",
                  gain_harvest_ranking="efficient")
    hybrid = dict(annual, gain_harvest_reinvest="hybrid", gain_harvest_ranking="overweight")
    monthly = dict(exits, harvest=True)
    weekly = dict(monthly, harvest_review_dates=scheduled_reviews("weekly"))
    cases = [
        ("baseline", "Retain departures; no voluntary harvesting", dict(harvest=False, exit_policy="retain")),
        ("exits", "Quarterly tax-budget exits; no voluntary harvesting", exits),
        ("monthly_tlh", "Monthly loss harvesting", monthly),
        ("monthly_hybrid", "Monthly losses + annual gains, departed first", dict(monthly, **hybrid)),
        ("weekly_tlh", "Weekly losses; no annual gain harvesting", weekly),
        ("weekly_annual", "Weekly losses + annual gain harvesting", dict(weekly, **annual)),
        ("annual_only", "Annual gains; no voluntary loss harvesting", dict(exits, **annual)),
        ("hybrid_only", "Annual gains, departed first; no voluntary loss harvesting", dict(exits, **hybrid)),
        ("weekly_no_exemption", "Weekly combined strategy; exemption unavailable", dict(weekly, **annual, cgt_exemption=0.)),
        ("hybrid_no_exemption", "Monthly combined strategy; exemption unavailable", dict(monthly, **hybrid, cgt_exemption=0.)),
        ("annual_monthly_control", "Monthly losses + annual same-share gains", dict(monthly, **annual)),
        ("any_loss", "Harvest any monthly loss of at least EUR1", dict(monthly, **annual, harvest_loss_fraction=0., harvest_min_loss_eur=1.)),
        ("retain_gains", "Retain departures; annual gains, no loss harvesting", dict(harvest=False, exit_policy="retain", **annual)),
        ("monthly_gains", "Monthly gain reviews instead of annual", dict(monthly, **dict(annual, gain_review_dates=scheduled_reviews("monthly")))),
    ]
    return [dict(key=key, label=label, frequency="fixed calendar", config=config,
                 role="headline" if key in LEADERS else "underperformer" if key in UNDERPERFORMERS else "baseline" if key == "baseline" else "diagnostic control")
            for key, label, config in cases]


def simulate(spec):
    p, w, events, metadata, membership = INPUTS
    c = replace(BASE_CONFIG, **spec["config"])
    result = run_backtest(p, w, c, events, metadata, membership)
    t, d = result.transactions, result.daily
    def total(event, column, reason=None):
        mask = t.event.eq(event)
        if reason is not None:
            mask &= t.reason.eq(reason)
        return float(t.loc[mask, column].sum()) if column in t else 0.
    cash_check = (total("contribution", "cash_eur") + total("dividend", "net_cash_eur")
                  + total("sell", "net_proceeds_eur")
                  + total("lot_disposal", "net_proceeds_eur", "mixed_merger")
                  + total("lot_disposal", "net_proceeds_eur", "capital_distribution")
                  + total("contingent_payment", "gross_proceeds_eur")
                  - total("contingent_payment", "fees_eur")
                  - total("buy", "cash_outlay_eur") - total("cgt_settlement", "tax_eur"))
    error = cash_check-result.summary["final_cash"]
    assert abs(error) < 1e-5, (spec["key"], error)
    assert result.summary["contributions"] == 192000 and result.summary["contribution_count"] == 192
    assert d.iloc[-1].holdings == {}
    assert (result.lots.units.abs() < 1e-8).all()
    buys = t[t.event.eq("buy")]
    assert (pd.to_datetime(buys.weight_available_date) < pd.to_datetime(buys.date)).all()
    harvests = t[t.event.eq("sell") & t.reason.eq("harvest")]
    assert (harvests.realized_gain_eur < 0).all()
    exits = t[t.event.eq("sell") & t.reason.eq("policy_exit")]
    if c.exit_policy == "loss_only":
        assert (exits.realized_gain_eur < 0).all()
    # Returns adjusted for the only external inflow, scheduled contributions.
    # The curve uses hypothetical after-tax marks; it is not a traded NAV index.
    flow = d.contributions_eur.diff().fillna(d.contributions_eur.iloc[0])
    ratio = (d.after_tax_liquidation_value_eur-flow)/d.after_tax_liquidation_value_eur.shift()
    ratio.iloc[0] = d.after_tax_liquidation_value_eur.iloc[0]/flow.iloc[0]
    twr = ratio.cumprod()
    d["after_tax_unit_growth"] = twr
    penultimate = d.iloc[-2]
    summary = dict(result.summary)
    summary.update(key=spec["key"], label=spec["label"], frequency=spec["frequency"],
        configuration=asdict(c), cash_reconciliation_error_eur=error,
        interim_cgt_paid_eur=result.summary["total_cgt"]-result.summary["final_tax"],
        policy_exit_count=len(exits), policy_sale_proceeds_eur=float(exits.gross_proceeds_eur.sum()),
        policy_realized_net_gain_eur=float(exits.realized_gain_eur.sum()),
        harvest_sale_count=len(harvests), purchase_count=len(buys),
        final_position_count=len(penultimate.holdings),
        mean_outside_weight=float(d.out_of_index_weight.iloc[:-1].mean()),
        peak_outside_weight=float(d.out_of_index_weight.iloc[:-1].max()),
        ending_outside_weight=float(penultimate.out_of_index_weight),
        mean_unknown_weight=float(d.unknown_membership_weight.iloc[:-1].mean()),
        ending_unknown_weight=float(penultimate.unknown_membership_weight),
        ending_combined_outside_unknown_weight=float(penultimate.out_of_index_weight+penultimate.unknown_membership_weight),
        after_tax_unit_max_drawdown=float((twr/twr.cummax()-1).min()),
        after_tax_unit_annualized_return=float(twr.iloc[-1]**(1/16)-1))
    name = spec["key"]
    t.to_csv(LEDGERS / f"{name}_transactions.csv.gz", index=False)
    result.lots.to_csv(LEDGERS / f"{name}_lots.csv.gz", index=False)
    result.yearly_tax.to_csv(LEDGERS / f"{name}_yearly_tax.csv", index=False)
    d["holdings"] = d.holdings.map(json.dumps)
    d.to_csv(LEDGERS / f"{name}_daily.csv.gz", index=False)
    gain_sales = t[t.event.eq("sell") & t.reason.eq("gain_harvest")]
    before_final = result.yearly_tax[~result.yearly_tax.final_settlement]
    summary.update(
        gain_harvest_sale_count=len(gain_sales),
        tlh_realised_net_loss_eur=-float(harvests.realized_gain_eur.sum()),
        exemption_used_before_final_eur=float(before_final.exemption_used.sum()),
        exemption_used_total_eur=float(result.yearly_tax.exemption_used.sum()),
        exemption_fully_used_before_final_years=int(before_final.exemption_used.ge(c.cgt_exemption-1e-5).sum()) if c.cgt_exemption else 0,
        nominal_cgt_sheltered_by_exemption_eur=float(result.yearly_tax.exemption_used.sum())*c.cgt_rate,
        terminal_loss_carry_eur=float(result.yearly_tax.iloc[-1].loss_carry_forward),
    )
    assert result.yearly_tax.exemption_used.between(-1e-8, c.cgt_exemption+1e-6).all()
    assert gain_sales.realized_gain_eur.gt(0).all()
    (LEDGERS / f"{name}_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


# Each pair changes one active decision rule, or the availability of the exemption.
PAIRS = [
    ("Departure management", "No voluntary harvesting", "baseline", "exits", "main"),
    ("Loss harvesting", "Monthly; annual gains off", "exits", "monthly_tlh", "main"),
    ("Annual gain harvesting", "Monthly losses; departed first", "monthly_tlh", "monthly_hybrid", "main"),
    ("Loss harvesting", "Weekly; annual gains off", "exits", "weekly_tlh", "main"),
    ("Annual gain harvesting", "Weekly losses; restore shares", "weekly_tlh", "weekly_annual", "main"),
    ("Annual gain harvesting", "No loss harvesting; restore shares", "exits", "annual_only", "interaction control"),
    ("Annual gain harvesting", "No loss harvesting; departed first", "exits", "hybrid_only", "interaction control"),
    ("Loss harvesting", "Weekly; annual gains on", "annual_only", "weekly_annual", "interaction control"),
    ("Loss harvesting", "Monthly; annual hybrid gains on", "hybrid_only", "monthly_hybrid", "interaction control"),
    ("Annual exemption", "Weekly combined strategy", "weekly_no_exemption", "weekly_annual", "sensitivity"),
    ("Annual exemption", "Monthly hybrid strategy", "hybrid_no_exemption", "monthly_hybrid", "sensitivity"),
]


POOR_COMPARISONS = [
    ("any_loss", "annual_monthly_control",
     "Relaxing the loss threshold triggered many more sales and changed replacement holdings and purchase restrictions. Recorded fees rose, but explain only part of the wealth shortfall; harvesting more losses did not improve the eventual after-tax outcome."),
    ("retain_gains", "annual_only",
     "Retaining departed stocks prevented tax-budget exits and reinvestment into current constituents. This portfolio paid less tax and fewer fees but produced less final wealth. Annual gain harvesting still improved the plain retained-stock baseline; retention underperformed the matched exit policy."),
    ("monthly_gains", "annual_monthly_control",
     "More frequent gain reviews triggered more winning disposals without materially increasing annual exemption use. Earlier basis resets also changed later loss eligibility and holdings. Lower taxes did not offset the weaker investment outcome; an annual allowance is not multiplied by monthly reviews."),
]


def assemble(specs):
    records = [json.loads((LEDGERS / f"{s['key']}_summary.json").read_text()) for s in specs]
    data = {r["key"]: r for r in records}
    (LEDGERS / "all_summaries.json").write_text(json.dumps(records, indent=2))
    etf = json.loads((OUT / "etf/summary.json").read_text())
    headline = [dict(etf, key="etf", label="Accumulating ETF; eight-year deemed disposal",
                     transaction_costs=0.), data["baseline"], *(data[k] for k in LEADERS)]
    columns = ["key", "label", "final_cash", "total_tax", "transaction_costs", "difference_vs_baseline_eur"]
    for row in headline:
        row["difference_vs_baseline_eur"] = row["final_cash"]-data["baseline"]["final_cash"]
    pd.DataFrame(headline)[columns].to_csv(OUT / "comparison.csv", index=False)
    pairs = []
    for feature, context, control, variant, presentation in PAIRS:
        a, b = data[control], data[variant]
        pairs.append(dict(feature=feature, context=context, control=control, variant=variant,
                          presentation=presentation, control_final_cash=a["final_cash"],
                          variant_final_cash=b["final_cash"], after_tax_gain_eur=b["final_cash"]-a["final_cash"],
                          cgt_reduction_eur=a["total_cgt"]-b["total_cgt"],
                          additional_nominal_exemption_shelter_eur=b["nominal_cgt_sheltered_by_exemption_eur"]-a["nominal_cgt_sheltered_by_exemption_eur"],
                          additional_cost_eur=b["transaction_costs"]-a["transaction_costs"]))
    pd.DataFrame(pairs).to_csv(OUT / "marginal_effects.csv", index=False)
    relief = ["key", "label", "exemption_used_before_final_eur", "exemption_used_total_eur",
              "exemption_fully_used_before_final_years", "nominal_cgt_sheltered_by_exemption_eur",
              "tlh_realised_net_loss_eur", "terminal_loss_carry_eur"]
    pd.DataFrame([data[k] for k in LEADERS])[relief].to_csv(OUT / "tax_relief.csv", index=False)
    interactions = []
    for context, loss, gain, both in [("Weekly losses / annual gains", "weekly_tlh", "annual_only", "weekly_annual"),
                                     ("Monthly losses / annual hybrid gains", "monthly_tlh", "hybrid_only", "monthly_hybrid")]:
        a, b, c, d = (data[k]["final_cash"] for k in ("exits", loss, gain, both))
        interactions.append(dict(context=context, loss_effect_without_gains_eur=b-a,
                                 loss_effect_with_gains_eur=d-c, gain_effect_without_losses_eur=c-a,
                                 gain_effect_with_losses_eur=d-b, interaction_eur=d-b-c+a))
    pd.DataFrame(interactions).to_csv(OUT / "interactions.csv", index=False)
    poor = []
    for key, comparator, explanation in POOR_COMPARISONS:
        a, b = data[comparator], data[key]
        poor.append(dict(key=key, label=b["label"], comparator=comparator,
                         final_cash=b["final_cash"], comparator_final_cash=a["final_cash"],
                         difference_vs_comparator_eur=b["final_cash"]-a["final_cash"],
                         additional_transaction_cost_eur=b["transaction_costs"]-a["transaction_costs"],
                         cgt_reduction_eur=a["total_cgt"]-b["total_cgt"],
                         total_tax_reduction_eur=a["total_tax"]-b["total_tax"],
                         additional_nominal_exemption_shelter_eur=b["nominal_cgt_sheltered_by_exemption_eur"]-a["nominal_cgt_sheltered_by_exemption_eur"],
                         harvest_sale_count=b["harvest_sale_count"], comparator_harvest_sale_count=a["harvest_sale_count"],
                         gain_harvest_sale_count=b["gain_harvest_sale_count"], comparator_gain_harvest_sale_count=a["gain_harvest_sale_count"],
                         tlh_realised_net_loss_eur=b["tlh_realised_net_loss_eur"], explanation=explanation))
    pd.DataFrame(poor).to_csv(OUT / "underperformers.csv", index=False)
    yearly = []
    for spec in specs:
        y = pd.read_csv(LEDGERS / f"{spec['key']}_yearly_tax.csv")
        y.insert(0, "strategy", spec["key"])
        yearly.append(y)
    pd.concat(yearly, ignore_index=True).to_csv(OUT / "annual_tax_and_exemptions.csv", index=False)


def main():
    global INPUTS, BASE_CONFIG
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--assemble-only", action="store_true")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    specs = policies()
    if args.assemble_only:
        assemble(specs)
        return
    LEDGERS.mkdir(parents=True, exist_ok=True)
    (OUT / "etf").mkdir(exist_ok=True)
    (OUT / "policy_definitions.json").write_text(json.dumps(specs, indent=2))
    nav_path = ROOT / "benchmark/issuer/cndx_nav_eur_2010-09-30_to_2026-09-30.csv"
    nav = pd.read_csv(nav_path, parse_dates=["date"]).set_index("date")
    etf, ledger, daily = replay(nav.loc[nav.index.weekday < 5, "nav_eur"], tax_rate=.38, deemed_disposal=True)
    assert etf["contribution_count"] == 192 and etf["contributions"] == 192000
    (OUT / "etf/summary.json").write_text(json.dumps(etf, indent=2))
    ledger.to_csv(OUT / "etf/events.csv.gz", index=False)
    daily.to_csv(OUT / "etf/daily.csv.gz", index=False)
    dates = tuple(ledger.loc[ledger.event.eq("contribution"), "date"].dt.strftime("%Y-%m-%d"))
    BASE_CONFIG = BacktestConfig(contribution_dates=dates, missing_target_policy="reserve_cash", max_stale_sessions=10)
    p, w, events, metadata, membership, audit_dir = prepare()
    overlay_path = ROOT / "inputs/corrected_membership/membership_alias_overlay.csv"
    overlay = pd.read_csv(overlay_path, parse_dates=["effective_date", "available_date"])
    membership = pd.concat([membership, overlay], ignore_index=True).drop_duplicates(
        ["security_id", "effective_date"], keep="last")
    membership.to_csv(LEDGERS / "membership_used.csv", index=False)
    metadata.to_csv(LEDGERS / "metadata_used.csv", index=False)
    INPUTS = (p[["date", "security_id", "price_eur", "dividend_eur", "tradable"]], w, events, metadata, membership)
    input_audit = json.loads((audit_dir / "input_audit.json").read_text())
    benchmark_audit = json.loads((ROOT / "benchmark/issuer/benchmark_audit.json").read_text())
    extra_inputs = [nav_path, overlay_path, ROOT / "benchmark/issuer/cndx_nav_eur.csv",
                    ROOT / "benchmark/indexes/NASDAQ100.csv", ROOT / "prices/best_effort/yf_GBPUSD=X.csv"]
    input_hashes = dict(input_audit["input_sha256"])
    input_hashes.update({str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in extra_inputs})
    code = [Path(__file__), ROOT / "study_inputs.py", ROOT / "model/direct_stock_backtest.py",
            ROOT / "model/etf_backtest.py", ROOT / "tax/irish_tax.py"]
    eligible_weights = w[pd.to_datetime(w.available_date) < pd.Timestamp(BASE_CONFIG.end)]
    freshness = dict(stock_price_cutoff=str(p.date.max().date()),
                     benchmark_cache_cutoff=benchmark_audit["end"],
                     source_audit_date=benchmark_audit["as_of"],
                     latest_eligible_weight_effective_date=str(pd.to_datetime(eligible_weights.effective_date).max().date()),
                     latest_eligible_weight_available_date=str(pd.to_datetime(eligible_weights.available_date).max().date()),
                     weights_publication_lag="September2026 holdings assumed available7October; excluded from earlier decisions")
    manifest = dict(project="Nasdaq After Tax", classification="PROVISIONAL_MATCHED_STRATEGY_STUDY",
                    period=[BASE_CONFIG.start, BASE_CONFIG.end], monthly_contribution_eur=1000,
                    contributions_eur=192000, final_liquidation=True, data_freshness=freshness,
                    headline_strategies=list(LEADERS), underperforming_strategies=list(UNDERPERFORMERS), stock_replays=len(specs),
                    selection="Three effective strategies retained after the earlier25-case exploration; retrospective selection, not an out-of-sample test or proof of optimality",
                    underperformer_selection="Three lowest final-wealth gain-harvesting variants in the earlier25-case study, excluding control cases and extra-spread sensitivities; different departure policies remain eligible. Each is compared with a matched rule variant, not labelled universally ineffective",
                    base_configuration=asdict(BASE_CONFIG), input_sha256=input_hashes,
                    code_sha256={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in code},
                    prepared_membership_sha256=hashlib.sha256((LEDGERS / "membership_used.csv").read_bytes()).hexdigest(),
                    assumptions=input_audit["assumptions"]+[
                        "Fixed complete16-year horizon; newest corrected cached corpus, no live account access",
                        "33% CGT,38% fund tax and52.35% dividend tax are frozen comparison scenarios, not historical tax legislation",
                        "All regular cases receive the EUR1270 annual CGT exemption; annual gain harvesting actively uses remaining headroom",
                        "Current and carried losses must be used before the exemption; unused exemption expires;17 calendar tax years",
                        "Exemption-unavailable sensitivities set only cgt_exemption=0; no other personal gains are modelled",
                        "Quarterly departure sales may realise losses even when discretionary TLH is off",
                        "Same-share gain repurchase requires all selected FIFO lots nonnegative and no same-class buy in preceding29days",
                        "Loss sales impose a29-day voluntary repurchase block; compulsory receipts remain separately audited",
                        "Tax-funded cash reserves and January settlements approximate payment timing; no interest on reserves",
                        "0.15% FX per non-euro buy/sale; no additional exchange spread/slippage; ETF NAV includes fund costs",
                        "Marginal wealth effects include holdings, reinvestment, tax and costs; do not add conditional effects or call all of them pure tax savings",
                        "Nominal exemption shelter equals exemption_used times CGT rate on that ledger; it is not incremental terminal wealth",
                    ],
                    tax_sources=[
                        "https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/how-to-calculate-cgt.aspx",
                        "https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/selling-or-disposing-of-shares.aspx",
                        "https://www.revenue.ie/en/tax-professionals/documents/notes-for-guidance/tca/part19.pdf",
                        "https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/when-and-how-do-you-pay-and-file-cgt.aspx",
                    ])
    (OUT / "study_manifest.json").write_text(json.dumps(manifest, indent=2))
    if args.workers == 1:
        for spec in specs:
            result = simulate(spec)
            print(f"{result['key']}: EUR{result['final_cash']:,.2f}", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context("fork")) as pool:
            futures = [pool.submit(simulate, spec) for spec in specs]
            for future in as_completed(futures):
                result = future.result()
                print(f"{result['key']}: EUR{result['final_cash']:,.2f}", flush=True)
    assemble(specs)
    print(f"Saved current study to {OUT}", flush=True)


if __name__ == "__main__":
    main()
