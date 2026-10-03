"""Audit saved matched comparisons without importing the backtest or tax engine.

Run after the study: .venv/bin/python historical/checks/check_attribution.py
Checks arithmetic and experimental controls, not the quality of market inputs.
"""
from pathlib import Path
import hashlib
import json
import math

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/latest"
LEDGERS = OUT / "ledgers"
CASES = ("baseline", "exits", "monthly_tlh", "monthly_hybrid", "weekly_tlh",
         "weekly_annual", "annual_only", "hybrid_only", "weekly_no_exemption",
         "hybrid_no_exemption", "annual_monthly_control", "any_loss", "retain_gains", "monthly_gains")
LEADERS = ("monthly_tlh", "monthly_hybrid", "weekly_annual")
UNDERPERFORMERS = ("any_loss", "retain_gains", "monthly_gains")
PAIRS = (
    ("Departure management", "baseline", "exits"),
    ("Loss harvesting", "exits", "monthly_tlh"),
    ("Annual gain harvesting", "monthly_tlh", "monthly_hybrid"),
    ("Loss harvesting", "exits", "weekly_tlh"),
    ("Annual gain harvesting", "weekly_tlh", "weekly_annual"),
    ("Annual gain harvesting", "exits", "annual_only"),
    ("Annual gain harvesting", "exits", "hybrid_only"),
    ("Loss harvesting", "annual_only", "weekly_annual"),
    ("Loss harvesting", "hybrid_only", "monthly_hybrid"),
    ("Annual exemption", "weekly_no_exemption", "weekly_annual"),
    ("Annual exemption", "hybrid_no_exemption", "monthly_hybrid"),
)


def read(path):
    return json.loads(path.read_text())


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def near(actual, expected, label):
    assert math.isfinite(float(actual)) and math.isfinite(float(expected)), label
    assert abs(float(actual)-float(expected)) < 2e-5, f"{label}: {actual} != {expected}"


def check_controls(feature, a, b):
    """Allow parameters of the toggled rule, never changes to other rules."""
    assert a.keys() == b.keys(), "Configuration fields differ"
    changed = {key for key in a if a[key] != b[key]}
    if feature == "Annual exemption":
        assert changed == {"cgt_exemption"}, changed
        assert (a["cgt_exemption"], b["cgt_exemption"]) == (0., 1270.)
        return changed
    switches = {"Departure management": "exit_policy", "Loss harvesting": "harvest",
                "Annual gain harvesting": "gain_harvest"}
    allowed = {
        "Departure management": {"exit_policy", "exit_review_dates", "exit_annual_tax_budget_eur"},
        "Loss harvesting": {"harvest", "harvest_review_dates"},
        "Annual gain harvesting": {"gain_harvest", "gain_review_dates", "gain_harvest_scope",
                                  "gain_harvest_reinvest", "gain_harvest_ranking", "gain_harvest_min_eur"},
    }
    switch = switches[feature]
    assert switch in changed and changed <= allowed[feature], (feature, changed)
    expected = ("retain", "tax_budget") if switch == "exit_policy" else (False, True)
    assert (a[switch], b[switch]) == expected, feature
    return changed


def main():
    (OUT / "attribution_audit.json").unlink(missing_ok=True)
    manifest = read(OUT / "study_manifest.json")
    specs = read(OUT / "policy_definitions.json")
    assert [s["key"] for s in specs] == list(CASES), "Unexpected policy set/order"
    assert manifest["stock_replays"] == len(CASES)
    assert manifest["headline_strategies"] == list(LEADERS)
    assert manifest["underperforming_strategies"] == list(UNDERPERFORMERS)
    assert "earlier25-case study" in manifest["underperformer_selection"]
    assert "retrospective" in manifest["selection"]
    assert manifest["period"] == ["2010-09-30", "2026-09-30"]
    assert manifest["final_liquidation"] is True
    assert manifest["monthly_contribution_eur"] == 1000
    assert manifest["contributions_eur"] == 192000
    for group in ("input_sha256", "code_sha256"):
        assert manifest[group], f"No recorded {group}"
        for name, expected in manifest[group].items():
            assert digest(ROOT / name) == expected, f"Stale source/input: {name}"
    input_audit = read(OUT / "input_audit/input_audit.json")
    for name, expected in input_audit["input_sha256"].items():
        assert manifest["input_sha256"][name] == expected, f"Conflicting input hashes: {name}"
    assert set(manifest["input_sha256"]) == set(input_audit["input_sha256"]) | {
        "benchmark/issuer/cndx_nav_eur_2010-09-30_to_2026-09-30.csv",
        "inputs/corrected_membership/membership_alias_overlay.csv", "benchmark/issuer/cndx_nav_eur.csv",
        "benchmark/indexes/NASDAQ100.csv", "prices/best_effort/yf_GBPUSD=X.csv"}
    assert set(manifest["code_sha256"]) == {
        "run_tax_optimization_study.py", "study_inputs.py", "model/direct_stock_backtest.py",
        "model/etf_backtest.py", "tax/irish_tax.py"}
    assert digest(LEDGERS / "membership_used.csv") == manifest["prepared_membership_sha256"], "Stale membership"
    for suffix in ("_summary.json", "_transactions.csv.gz", "_lots.csv.gz", "_yearly_tax.csv", "_daily.csv.gz"):
        actual = {p.name.removesuffix(suffix) for p in LEDGERS.glob(f"*{suffix}")}
        assert actual == set(CASES), (suffix, actual.symmetric_difference(CASES))

    data = {key: read(LEDGERS / f"{key}_summary.json") for key in CASES}
    assert read(LEDGERS / "all_summaries.json") == list(data.values()), "Stale combined summaries"
    annual_frames = []
    gross_profit = {}
    for spec in specs:
        key = spec["key"]
        s = data[key]
        c = s["configuration"]
        assert c == dict(manifest["base_configuration"], **spec["config"]), f"Stale configuration: {key}"
        assert spec["role"] == ("headline" if key in LEADERS else "underperformer" if key in UNDERPERFORMERS else "baseline" if key == "baseline" else "diagnostic control")
        assert s["key"] == key and s["label"] == spec["label"]
        assert s["contributions"] == 192000 and s["contribution_count"] == 192
        assert s["liquidated"] and c["liquidate_at_end"]
        near(s["final_cash"], s["final_value"], f"{key} liquidated value")
        near(s["cash_reconciliation_error_eur"], 0, f"{key} cash reconciliation")
        near(s["total_tax"], s["total_cgt"]+s["total_dividend_tax"], f"{key} total tax")
        near(s["total_cgt"], s["interim_cgt_paid_eur"]+s["final_tax"], f"{key} tax timing")
        assert c["cgt_rate"] == .33 and c["cgt_exemption"] == (0. if key.endswith("no_exemption") else 1270.)
        y = pd.read_csv(LEDGERS / f"{key}_yearly_tax.csv")
        assert y.year.tolist() == list(range(2010, 2027)), f"{key} tax years"
        assert y.final_settlement.tolist() == [False]*16+[True], f"{key} final settlement"
        assert y.exemption_used.between(-1e-8, c["cgt_exemption"]+1e-6).all()
        gross_profit[key] = y.gains_eur.sum()-y.losses_eur.sum()+y.gross_dividends_eur.sum()+s["transaction_costs"]
        near(gross_profit[key], s["final_cash"]-s["contributions"]+s["total_tax"]+s["transaction_costs"],
             f"{key} gross investment profit reconciliation")
        for field, expected in {
            "total_cgt": y.tax_due.sum(), "final_tax": y.tax_due.iloc[-1],
            "total_dividend_tax": y.dividend_tax_eur.sum(),
            "exemption_used_total_eur": y.exemption_used.sum(),
            "exemption_used_before_final_eur": y.exemption_used.iloc[:-1].sum(),
            "exemption_fully_used_before_final_years": int(y.exemption_used.iloc[:-1].ge(c["cgt_exemption"]-1e-5).sum()) if c["cgt_exemption"] else 0,
            "nominal_cgt_sheltered_by_exemption_eur": y.exemption_used.sum()*c["cgt_rate"],
            "terminal_loss_carry_eur": y.loss_carry_forward.iloc[-1],
        }.items():
            near(s[field], expected, f"{key} {field}")
        if not c["harvest"]:
            assert s["harvest_sale_count"] == 0
            near(s["tlh_realised_net_loss_eur"], 0, f"{key} disabled TLH")
        if not c["gain_harvest"]:
            assert s["gain_harvest_sale_count"] == 0
        if c["exit_policy"] == "retain":
            assert s["policy_exit_count"] == 0
        daily = pd.read_csv(LEDGERS / f"{key}_daily.csv.gz",
                           usecols=["date", "holdings", "after_tax_liquidation_value_eur"])
        assert daily.date.iloc[0] == c["start"] and daily.date.iloc[-1] == c["end"]
        assert json.loads(daily.holdings.iloc[-1]) == {}, f"{key} terminal holdings"
        near(daily.after_tax_liquidation_value_eur.iloc[-1], s["final_cash"], f"{key} final daily mark")
        y.insert(0, "strategy", key)
        annual_frames.append(y)
    pd.testing.assert_frame_equal(pd.read_csv(OUT / "annual_tax_and_exemptions.csv"),
                                  pd.concat(annual_frames, ignore_index=True), atol=2e-5, rtol=0)

    pairs = pd.read_csv(OUT / "marginal_effects.csv")
    assert list(pairs[["feature", "control", "variant"]].itertuples(index=False, name=None)) == list(PAIRS)
    changed_fields = {}
    effects = {}
    for row in pairs.itertuples(index=False):
        a, b = data[row.control], data[row.variant]
        changed_fields[f"{row.control} -> {row.variant}"] = sorted(check_controls(row.feature, a["configuration"], b["configuration"]))
        for field, expected in {
            "control_final_cash": a["final_cash"], "variant_final_cash": b["final_cash"],
            "after_tax_gain_eur": b["final_cash"]-a["final_cash"],
            "cgt_reduction_eur": a["total_cgt"]-b["total_cgt"],
            "additional_cost_eur": b["transaction_costs"]-a["transaction_costs"],
            "additional_nominal_exemption_shelter_eur": b["nominal_cgt_sheltered_by_exemption_eur"]-a["nominal_cgt_sheltered_by_exemption_eur"],
        }.items():
            near(getattr(row, field), expected, f"{row.control}/{row.variant} {field}")
        effects[row.control, row.variant] = row.after_tax_gain_eur

    interactions = pd.read_csv(OUT / "interactions.csv")
    assert len(interactions) == 2
    for row, (loss, gain, both) in zip(interactions.itertuples(index=False),
            [("weekly_tlh", "annual_only", "weekly_annual"), ("monthly_tlh", "hybrid_only", "monthly_hybrid")]):
        a, b, c, d = [data[k]["final_cash"] for k in ("exits", loss, gain, both)]
        for field, expected in {"loss_effect_without_gains_eur": b-a, "loss_effect_with_gains_eur": d-c,
                               "gain_effect_without_losses_eur": c-a, "gain_effect_with_losses_eur": d-b,
                               "interaction_eur": (d-c)-(b-a)}.items():
            near(getattr(row, field), expected, f"{both} {field}")
        near(row.interaction_eur, row.gain_effect_with_losses_eur-row.gain_effect_without_losses_eur,
             f"{both} symmetric interaction")
    ladders = {}
    for path in [("baseline", "exits", "monthly_tlh", "monthly_hybrid"),
                 ("baseline", "exits", "weekly_tlh", "weekly_annual")]:
        step_sum = sum(effects[a, b] for a, b in zip(path, path[1:]))
        near(step_sum, data[path[-1]]["final_cash"]-data[path[0]]["final_cash"], f"{path[-1]} ladder")
        ladders[path[-1]] = step_sum

    headline = pd.read_csv(OUT / "comparison.csv")
    assert headline.key.tolist() == ["etf", "baseline", *LEADERS], "Headline selection changed"
    etf = read(OUT / "etf/summary.json")
    assert etf["contributions"] == 192000 and etf["contribution_count"] == 192
    near(etf["final_cash"], etf["final_value_before_final_tax"]-etf["final_tax"], "ETF final tax")
    near(etf["total_tax"], etf["final_tax"]+etf["deemed_disposal_tax"]+etf["funding_sales_tax"], "ETF tax components")
    for row in headline.itertuples(index=False):
        s = etf if row.key == "etf" else data[row.key]
        for field in ("final_cash", "total_tax", "transaction_costs"):
            near(getattr(row, field), s.get(field, 0.), f"Headline {row.key} {field}")
        near(row.difference_vs_baseline_eur, s["final_cash"]-data["baseline"]["final_cash"], f"Headline {row.key} difference")
    relief = pd.read_csv(OUT / "tax_relief.csv")
    assert relief.key.tolist() == list(LEADERS)
    for row in relief.to_dict("records"):
        for field, actual in row.items():
            if field not in ("key", "label"):
                near(actual, data[row["key"]][field], f"Relief {row['key']} {field}")

    poor = pd.read_csv(OUT / "underperformers.csv")
    assert poor.key.tolist() == list(UNDERPERFORMERS)
    assert poor.comparator.tolist() == ["annual_monthly_control", "annual_only", "annual_monthly_control"]
    assert poor.final_cash.is_monotonic_increasing, "Underperformer rows must follow their historical ranking"
    underperformer_checks = {}
    for row in poor.itertuples(index=False):
        a, b = data[row.comparator], data[row.key]
        ac, bc = a["configuration"], b["configuration"]
        assert ac.keys() == bc.keys()
        changed = {key for key in ac if ac[key] != bc[key]}
        if row.key == "any_loss":
            assert changed == {"harvest_loss_fraction", "harvest_min_loss_eur"}, changed
            assert (ac["harvest_loss_fraction"], ac["harvest_min_loss_eur"]) == (.05, 25.)
            assert (bc["harvest_loss_fraction"], bc["harvest_min_loss_eur"]) == (0., 1.)
        elif row.key == "retain_gains":
            check_controls("Departure management", bc, ac)
            assert bc["exit_review_dates"] is None, "Retain review cadence must be inactive"
            assert b["final_cash"] > data["baseline"]["final_cash"], "Retain gain harvesting still improves its baseline"
        else:
            assert changed == {"gain_review_dates"}, changed
            assert len(ac["gain_review_dates"]) == 16 and len(bc["gain_review_dates"]) == 193
            assert all(day[5:7] == "12" for day in ac["gain_review_dates"])
            assert len({day[:7] for day in bc["gain_review_dates"]}) == 193
        changed_fields[f"{row.comparator} -> {row.key}"] = sorted(changed)
        assert row.label == b["label"] and isinstance(row.explanation, str) and row.explanation
        assert row.difference_vs_comparator_eur < 0
        for field, expected in {
            "final_cash": b["final_cash"], "comparator_final_cash": a["final_cash"],
            "difference_vs_comparator_eur": b["final_cash"]-a["final_cash"],
            "additional_transaction_cost_eur": b["transaction_costs"]-a["transaction_costs"],
            "cgt_reduction_eur": a["total_cgt"]-b["total_cgt"],
            "total_tax_reduction_eur": a["total_tax"]-b["total_tax"],
            "additional_nominal_exemption_shelter_eur": b["nominal_cgt_sheltered_by_exemption_eur"]-a["nominal_cgt_sheltered_by_exemption_eur"],
            "harvest_sale_count": b["harvest_sale_count"], "comparator_harvest_sale_count": a["harvest_sale_count"],
            "gain_harvest_sale_count": b["gain_harvest_sale_count"], "comparator_gain_harvest_sale_count": a["gain_harvest_sale_count"],
            "tlh_realised_net_loss_eur": b["tlh_realised_net_loss_eur"],
        }.items():
            near(getattr(row, field), expected, f"Underperformer {row.key} {field}")
        near(row.difference_vs_comparator_eur,
             gross_profit[row.key]-gross_profit[row.comparator]+row.total_tax_reduction_eur-row.additional_transaction_cost_eur,
             f"{row.key} accounting bridge")
        underperformer_checks[row.key] = dict(
            comparator=row.comparator,
            gross_investment_profit_difference_eur=float(gross_profit[row.key]-gross_profit[row.comparator]),
            total_tax_reduction_eur=row.total_tax_reduction_eur,
            additional_transaction_cost_eur=row.additional_transaction_cost_eur,
            after_tax_wealth_difference_eur=row.difference_vs_comparator_eur,
            annual_ledger_profit_reconciled=True)

    audit = dict(status="PASS", stock_cases=len(CASES), headline_rows=len(headline),
                 matched_pairs=len(pairs), interactions=len(interactions),
                 underperformer_comparisons=len(poor),
                 underperformer_checks=underperformer_checks,
                 accounting_bridge_scope="Realised investment profit along each actual portfolio path; not a tax-free counterfactual or a claim about individual missed recoveries",
                 sequential_ladder_gains_eur=ladders,
                 input_hashes_checked=len(manifest["input_sha256"]),
                 code_hashes_checked=len(manifest["code_sha256"]),
                 shared_membership_sha256=manifest["prepared_membership_sha256"],
                 control_configuration_changes=changed_fields,
                 checker_sha256=digest(Path(__file__)),
                 scope="Saved-output arithmetic, matched controls and source freshness; excludes certification of prices, legal classifications and pure-tax causal attribution")
    (OUT / "attribution_audit.json").write_text(json.dumps(audit, indent=2)+"\n")
    print(f"PASS: {len(CASES)} stock cases, {len(pairs)} matched pairs, {len(poor)} underperformer comparisons, two interactions and two wealth ladders")


if __name__ == "__main__":
    main()
