"""Render a two-page summary of the corrected study and its current limits."""
from pathlib import Path
import gzip
import hashlib
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results/latest"
ORDER = ["etf", "baseline", "monthly_tlh", "monthly_hybrid", "weekly_annual"]
LABELS = {
    "etf": "Hold the Nasdaq-100 ETF",
    "baseline": "Buy shares directly and retain departed stocks",
    "monthly_tlh": "Monthly loss reviews",
    "monthly_hybrid": "Monthly losses with December gain reviews",
    "weekly_annual": "Weekly losses with December gain reviews",
}
DESCRIPTIONS = {
    "etf": "38% fund tax with eight-year deemed disposal.",
    "baseline": "No voluntary sales before final liquidation.",
    "monthly_tlh": "Review eligible losses. No December gain sales.",
    "monthly_hybrid": "December reviews prioritize former index stocks.",
    "weekly_annual": "December reviews consider current index stocks.",
}
INK, MUTED, TEAL, LIME, CORAL = "#142F3B", "#596B72", "#087F80", "#C4EF68", "#B34D35"
PAPER, WHITE, LINE, SOFT = "#F5F4EE", "#FFFFFF", "#D9DFD9", "#E8EDE7"
NIGHT, PANEL, AQUA, BLUE, DIM = "#101F2D", "#1B2D3B", "#54DACB", "#83B5F3", "#B2C3CF"
SALMON = "#F29C88"
PAGE_COUNT = 2


def money(value, signed=False):
    amount = float(value)
    sign = ("+" if amount >= 0 else "−") if signed and round(amount) else ""
    return f"{sign}€{abs(amount) if sign else amount:,.0f}"


def text(fig, x, y, value, size=10, color=INK, weight="normal", **kwargs):
    return fig.text(x, y, value, fontsize=size, color=color, weight=weight,
                    va="top", linespacing=1.45, **kwargs)


def box(fig, x, y, width, height, color):
    fig.add_artist(Rectangle((x, y), width, height, transform=fig.transFigure,
                             facecolor=color, edgecolor="none", zorder=0))


def rounded_box(fig, x, y, width, height, color, radius=.014):
    fig.add_artist(FancyBboxPatch((x, y), width, height,
                   boxstyle=f"round,pad=0,rounding_size={radius}",
                   transform=fig.transFigure, facecolor=color, edgecolor="none", zorder=0))


def rule(fig, x, y, width, color=LINE):
    box(fig, x, y, width, .0012, color)


def page(title, subtitle, number):
    fig = plt.figure(figsize=(11.7, 8.3), facecolor=PAPER)
    for i in range(3):
        box(fig, .05 + i * .009, .944, .005, .009 + i * .008, TEAL)
    text(fig, .088, .964, "NASDAQ AFTER TAX", 9, weight="bold")
    text(fig, .95, .964, "RESEARCH BRIEF  /  2010—2026", 8, MUTED, ha="right")
    text(fig, .05, .887, title, 29, weight="bold")
    text(fig, .05, .817, subtitle, 10, MUTED)
    rule(fig, .05, .066, .90)
    text(fig, .05, .046, "HYPOTHETICAL STUDY  ·  30 SEP 2010 — 30 SEP 2026", 7.5, MUTED)
    text(fig, .95, .046, f"{number:02d} / {PAGE_COUNT:02d}", 8, MUTED, ha="right")
    return fig


def read_inputs():
    required = {
        "comparison": ["key", "label", "final_cash", "total_tax", "transaction_costs", "difference_vs_baseline_eur"],
        "marginal_effects": ["feature", "context", "control", "variant", "control_final_cash", "variant_final_cash", "after_tax_gain_eur", "cgt_reduction_eur", "additional_nominal_exemption_shelter_eur", "additional_cost_eur"],
    }
    frames = {}
    for name, fields in required.items():
        frame = pd.read_csv(OUT / f"{name}.csv")
        missing = set(fields) - set(frame.columns)
        if missing:
            raise ValueError(f"{name}.csv is missing columns: {sorted(missing)}")
        frames[name] = frame
    if set(frames["comparison"].key) != set(ORDER) or len(frames["comparison"]) != len(ORDER):
        raise ValueError("Expected exactly the ETF, stock baseline and three selected stock strategies")
    frames["comparison"] = frames["comparison"].set_index("key").loc[ORDER].reset_index()
    frames["manifest"] = json.loads((OUT / "study_manifest.json").read_text())
    manifest = frames["manifest"]
    if manifest["base_configuration"].get("execution_mode") != "next_session":
        raise ValueError("This report requires later-session stock execution")
    if manifest["period"] != ["2010-09-30", "2026-09-30"]:
        raise ValueError("This report requires the full 2010-2026 study period")
    settings = manifest["contribution_schedule"]
    if (settings["type"], settings["review_month"], settings["deflation_policy"]) != ("irish_cpi_annual", 9, "track"):
        raise ValueError("This report expects September Irish CPI reviews that follow both inflation and deflation")
    schedule = pd.read_csv(OUT / settings["schedule_file"], parse_dates=["date"])
    if not {"date", "contribution_eur"}.issubset(schedule.columns) or schedule.empty:
        raise ValueError("A dated contribution schedule is required")
    if not schedule.date.is_monotonic_increasing or schedule.date.duplicated().any():
        raise ValueError("Contribution dates must be unique and in date order")
    if not np.isfinite(schedule.contribution_eur).all() or not schedule.contribution_eur.gt(0).all():
        raise ValueError("Contribution amounts must be finite and positive")
    checks = [(schedule.contribution_eur.sum(), manifest["contributions_eur"]),
              (schedule.contribution_eur.iloc[0], manifest["initial_monthly_contribution_eur"]),
              (schedule.contribution_eur.iloc[0], settings["initial_monthly_eur"]),
              (schedule.contribution_eur.iloc[-1], settings["final_monthly_eur"])]
    if any(not np.isclose(float(actual), float(expected), rtol=0, atol=.011) for actual, expected in checks):
        raise ValueError("Contribution schedule and manifest amounts do not reconcile")
    frames["contribution_schedule"] = schedule
    for name in ("accuracy_audit", "accuracy_data_audit", "accuracy_replay", "accuracy_etf_funding"):
        frames[name] = json.loads((OUT / f"{name}.json").read_text())
    frames["accuracy_sensitivities"] = pd.read_csv(OUT / "accuracy_sensitivities.csv")
    sensitivity = json.loads((OUT / "accuracy_sensitivities.json").read_text())
    frames["robustness"] = pd.read_csv(OUT / "robustness.csv")
    robustness = json.loads((OUT / "robustness.json").read_text())
    manifest_hash = hashlib.sha256((OUT / "study_manifest.json").read_bytes()).hexdigest()
    for evidence in (sensitivity, robustness, frames["accuracy_audit"], frames["accuracy_replay"]):
        if manifest_hash != evidence["study_manifest_sha256"]:
            raise ValueError("Repeat the accuracy assessment for the current study manifest")
    if hashlib.sha256((OUT / "accuracy_sensitivities.csv").read_bytes()).hexdigest() != sensitivity["results_sha256"]:
        raise ValueError("Sensitivity results do not match their audit record")
    if hashlib.sha256((OUT / "robustness.csv").read_bytes()).hexdigest() != robustness["results_sha256"]:
        raise ValueError("Robustness results do not match their audit record")
    audit, replay, fund = (frames[name] for name in ("accuracy_audit", "accuracy_replay", "accuracy_etf_funding"))
    if (audit["arithmetic_checks"]["all_passed"] is not True or audit["manifest_hashes"]["all_match"] is not True
            or replay["all_match"] is not True or fund["published_summary_reproduced"] is not True
            or any(row["status"] != "PASS" for row in audit["ledger_checks"] + replay["files"])):
        raise ValueError("The report requires successful accuracy checks")
    for hashes in (manifest["input_sha256"], manifest["code_sha256"], sensitivity["code_sha256"],
                   robustness["input_sha256"], robustness["code_sha256"],
                   frames["accuracy_data_audit"]["input_sha256"], fund["source_sha256"]):
        for name, expected in hashes.items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Accuracy evidence is stale: {name}")
    for name, expected in replay["output_sha256"].items():
        content = (ROOT / name).read_bytes()
        if name.endswith(".gz"):
            content = gzip.decompress(content)
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"Replay evidence is stale: {name}")
    if hashlib.sha256((ROOT / "checks/verify_replay.py").read_bytes()).hexdigest() != replay["verification_code_sha256"]:
        raise ValueError("Replay verification code changed; repeat the replay check")
    comparison = frames["comparison"].set_index("key")
    expected_gap = comparison.loc["weekly_annual", "final_cash"]-comparison.loc["etf", "final_cash"]
    if not np.isclose(expected_gap, audit["headline_decomposition"]["total_gap_eur"], rtol=0, atol=1e-6):
        raise ValueError("Accuracy assessment and headline balances disagree")
    if not np.isclose(comparison.loc["etf", "final_cash"],
                      fund["corrected_independent_reproduction"]["final_cash"], rtol=0, atol=1e-6):
        raise ValueError("The ETF balance does not match the corrected independent reproduction")
    dividend_path = ROOT / "inputs/verified_dividends.csv"
    dividend_key = str(dividend_path.relative_to(ROOT))
    if manifest["input_sha256"].get(dividend_key) != hashlib.sha256(dividend_path.read_bytes()).hexdigest():
        raise ValueError("The study manifest does not bind the verified dividend schedule")
    frames["verified_dividends"] = pd.read_csv(dividend_path)
    if not frames["verified_dividends"].payment_evidence.isin(
            ["issuer_report_confirms_payment", "issuer_declared_schedule_only"]).all():
        raise ValueError("The dividend schedule contains an unknown evidence category")
    return frames


def overview(data):
    comparison = data["comparison"].set_index("key")
    best = comparison.loc[comparison.final_cash.idxmax()]
    total = data["manifest"]["contributions_eur"]
    fig = page("The corrected comparison.",
               "Nasdaq-100 share portfolios and an ETF under the same Irish tax scenario. All values are nominal euros.", 1)
    text(fig, .05, .790, "Provisional backtest. The stock portfolios differ from ETF exposure. The next page states the fixes and remaining limits.", 9, CORAL)
    rounded_box(fig, .05, .177, .345, .585, NIGHT)
    rounded_box(fig, .075, .711, .223, .035, PANEL, .008)
    text(fig, .075, .730, "HIGHEST OF THESE FIVE", 9, LIME, "bold")
    text(fig, .072, .675, money(best.final_cash), 42, WHITE, "bold")
    text(fig, .075, .577, LABELS[best.name].replace(" with ", "\nwith ").replace(" and ", "\nand "), 12, WHITE, "bold")
    rule(fig, .075, .474, .292, "#46606A")
    for y, key, label in [(.443, "etf", "versus the ETF"), (.330, "baseline", "versus the stock baseline")]:
        text(fig, .075, y, money(best.final_cash - comparison.loc[key, "final_cash"], True), 25, LIME, "bold")
        text(fig, .075, y - .054, label, 10, "#CFDAD9")
    text(fig, .075, .218, "After liquidation, taxes and costs.", 9, "#CFDAD9")
    maximum = np.ceil(comparison.final_cash.max() / 250000) * 250000
    rounded_box(fig, .418, .177, .545, .585, NIGHT)
    colors = ["#728A9C", "#A1B6C5", BLUE, AQUA, LIME]
    for i, key in enumerate(ORDER):
        y = .736 - i * .100
        row = comparison.loc[key]
        if key == best.name:
            rounded_box(fig, .426, y - .096, .529, .109, "#243D3E", .009)
        text(fig, .435, y, LABELS[key], 9.5, LIME if key == best.name else WHITE, weight="bold")
        text(fig, .435, y - .025, DESCRIPTIONS[key], 8.5, DIM)
        text(fig, .95, y - .046, money(row.final_cash), 16,
             LIME if key == best.name else WHITE, weight="bold", ha="right")
        rounded_box(fig, .435, y - .087, .515, .012, "#354754", .006)
        rounded_box(fig, .435, y - .087, .515 * row.final_cash / maximum, .012, colors[i], .006)
    text(fig, .435, .207, "€0", 8, DIM)
    text(fig, .695, .207, "FINAL WEALTH · LINEAR SCALE", 7, DIM, ha="center")
    text(fig, .95, .207, f"€{maximum / 1000000:g}m", 8, DIM, ha="right")
    text(fig, .05, .158, "Active strategies also review departed stocks quarterly. Signal-date tests seek sales with no extra CGT.", 10, weight="bold")
    text(fig, .05, .127, "Orders execute at later-session prices. Actual gains and taxes can differ from signal-date estimates.", 9.5, MUTED)
    text(fig, .05, .098, f"€{total:,.2f} contributed / {len(data['contribution_schedule'])} payments / 16 years. Differences include exposure, costs and tax.", 9, MUTED)
    return fig


def corrections_and_limits(data):
    audit = data["accuracy_audit"]
    replay = data["accuracy_replay"]
    fund = data["accuracy_etf_funding"]
    coverage = data["accuracy_data_audit"]["source_coverage"]
    dividends = data["verified_dividends"]
    confirmed = dividends.payment_evidence.eq("issuer_report_confirms_payment").sum()
    unconfirmed = len(dividends) - confirmed
    diagnostic = next(row for row in audit["portfolio_diagnostics"] if row["key"] == "weekly_annual")
    exposure_date = pd.Timestamp(diagnostic["as_of"]).strftime("%d %b %Y")
    target_date = pd.Timestamp(diagnostic["target_effective_date"]).strftime("%d %b %Y")
    robustness = data["robustness"]
    delayed = robustness.loc[robustness.key.eq("weekly_annual")
                             & robustness.weight_availability_lag_business_days.eq(5)]
    if len(delayed) != 1 or delayed.status.iloc[0] != "COMPLETE":
        raise ValueError("The summary requires one completed weekly weight-delay control")
    delay_effect = delayed.difference_vs_original_availability_eur.iloc[0]
    config = data["manifest"]["base_configuration"]
    dividend_rate = sum(config[key] for key in ("dividend_income_tax", "dividend_usc", "dividend_prsi"))
    fig = page("Fixes applied. Limits retained.",
               "The model now separates decisions from execution and corrects specific cash-flow errors.", 2)
    text(fig, .05, .751, "WHAT CHANGED", 9, TEAL, "bold")
    text(fig, .53, .751, "WHAT THE RESULTS STILL ASSUME", 9, TEAL, "bold")
    cards = [
        (.05, .535, "01 / LATER EXECUTION",
         "Signal dates fix sale units and purchase cash budgets.\n"
         "Orders fill at a later eligible session's close.\n"
         "Actual prices set realized gains, losses, and tax.\n"
         "Annual gain reviews: 15 December or prior weekday.\n"
         "Final liquidation follows the fixed end date."),
        (.05, .322, "02 / CASH AND COSTS",
         "ETF tax uses the same-day contribution first.\n"
         "Only the shortfall requires a sale of ETF units.\n"
         f"Effect versus the old rule: {money(fund['final_wealth_difference_eur'], True)}.\n"
         "Compulsory corporate cash receipts have no trade fee.\n"
         "The Expedia spin-off no longer adds false cash."),
        (.05, .109, "03 / CDK AND LOGMEIN DIVIDENDS",
         f"The correction adds {len(dividends)} ordinary dividend schedules.\n"
         f"Issuers confirm {confirmed} payments. {unconfirmed} remains declaration-only.\n"
         "Derived ex-dates fix entitlement before payment.\n"
         "Sales after entitlement preserve the right to payment."),
        (.53, .535, "WEEKLY EXPOSURE / SHARED SOURCES",
         f"Top ten share classes / stock value: {diagnostic['top10_share_of_stock_value']:.1%} ({exposure_date}).\n"
         f"Last known targets: {diagnostic['target_top10_weight']:.1%} ({target_date}).\n"
         f"Mean weight-source age: {coverage['mean_snapshot_age_days']:.1f} days.\n"
         f"Weekly wealth change with +5 business days of weight lag: {money(delay_effect, True)}.\n"
         "Release dates and some corporate actions stay provisional."),
        (.53, .322, "TAX AND EXECUTION ASSUMPTIONS",
         f"Frozen rates: {config['cgt_rate']:.0%} CGT, 38% fund tax, {dividend_rate:.2%} dividends.\n"
         f"Annual CGT exemption: {money(config['cgt_exemption'])}. No other gains.\n"
         f"Trade FX: {config['fx_fee']:.2%}. Extra spread per side: {config['half_spread']:.2%}.\n"
         "Fractional access and actual broker fills remain unverified."),
        (.53, .109, "CHECKS AND THEIR LIMITS",
         f"{replay['stock_replays']} stock replays and the ETF reproduce saved results.\n"
         "Independent ledgers and ETF arithmetic pass.\n"
         "Shared data, proxy prices, and tax classifications can err.\n"
         "These selected historical paths do not prove future returns."),
    ]
    for x, y, title, body in cards:
        rounded_box(fig, x, y, .42, .187, WHITE, .008)
        text(fig, x + .015, y + .171, title, 8.5, TEAL, "bold")
        text(fig, x + .015, y + .131, body, 9.2, MUTED)
    text(fig, .05, .085,
         "Other dividend payment dates and personal tax details remain approximate. Research only. No forecast or accuracy percentage.", 8, MUTED)
    return fig


def marginal_chart(data):
    labels = {
        ("baseline", "exits"): "Review former index stocks quarterly\nSignal-date tests seek no extra CGT",
        ("exits", "monthly_tlh"): "Add monthly loss reviews\nLater-session prices determine realized gains or losses",
        ("monthly_tlh", "monthly_hybrid"): "Add December gain reviews: former stocks first\nThen current stocks, with monthly loss reviews",
        ("exits", "weekly_tlh"): "Add weekly loss reviews\nLater-session prices determine realized gains or losses",
        ("weekly_tlh", "weekly_annual"): "Add December gain reviews and later rebuys\nCurrent index stocks only, with weekly loss reviews",
        ("weekly_no_exemption", "weekly_annual"): "Make the €1,270 exemption available\nWeekly loss reviews, with December gain reviews",
        ("hybrid_no_exemption", "monthly_hybrid"): "Make the €1,270 exemption available\nMonthly loss reviews, with former stocks first in December",
    }
    shown = data["marginal_effects"].set_index(["control", "variant"]).loc[list(labels)]
    fig = plt.figure(figsize=(12.6, 8), facecolor=NIGHT)
    ax = fig.add_axes([.50, .090, .345, .695], facecolor="none")
    values = shown.after_tax_gain_eur.to_numpy()
    positions = [.735, .644, .553, .462, .371, .220, .129]
    colors = [BLUE, AQUA, AQUA, AQUA, LIME, LIME, SALMON]
    ax.set_ylim(.090, .785)
    limit = np.ceil(np.abs(values).max() / 10000) * 10000
    ax.set_xlim(min(values.min(), 0) - limit * .07, limit)
    for y, value, label, color in zip(positions, values, labels.values(), colors):
        rounded_box(fig, .04, y - .036, .92, .074, PANEL, .012)
        title, detail = label.split("\n")
        text(fig, .055, y + .021, title, 10, WHITE, "bold")
        text(fig, .055, y - .005, detail, 8.5, DIM)
        ax.barh(y, value, height=.012, color=color, zorder=3)
        ax.scatter(value, y, s=30, color=color, edgecolors=PANEL, linewidths=.8, zorder=4)
        text(fig, .945, y + .017, money(value, True), 15, color, "bold", ha="right")
    ax.set_yticks([])
    ax.axvline(0, color=DIM, lw=1, alpha=.7)
    first_tick = np.ceil(ax.get_xlim()[0] / 10000) * 10000
    ax.set_xticks(np.arange(first_tick, limit + 1, 10000))
    ax.xaxis.set_major_formatter(FuncFormatter(
        lambda value, _: "€0" if value == 0 else f"{'−' if value < 0 else ''}€{abs(value)/1000:,.0f}k"))
    ax.tick_params(length=0, colors=DIM, labelsize=8, pad=7)
    ax.grid(axis="x", color=WHITE, alpha=.10, lw=.6)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)
    text(fig, .04, .971, "NASDAQ AFTER TAX   /   MATCHED COMPARISONS", 8, LIME, "bold")
    text(fig, .04, .920, "What each rule changed.", 28, WHITE, "bold")
    text(fig, .04, .852, "Final wealth after tax and costs. Each row compares portfolios that differ in one rule.", 11, DIM)
    text(fig, .055, .793, "01 / CHANGE A TRADING RULE", 8, AQUA, "bold")
    text(fig, .945, .793, "WEALTH CHANGE", 8, DIM, "bold", ha="right")
    text(fig, .055, .282, "02 / MAKE THE ANNUAL EXEMPTION AVAILABLE", 8, LIME, "bold")
    text(fig, .04, .045, "Different controls: do not add these bars. Wealth changes include exposure, reinvestment, tax, and costs.", 9, DIM)
    text(fig, .04, .021, "Hypothetical 2010–2026 study · CPI-indexed contributions · Full liquidation", 8, DIM)
    fig.savefig(OUT / "marginal_effects.png", dpi=180, facecolor=NIGHT)
    plt.close(fig)


def main():
    data = read_inputs()
    plt.rcParams.update({"font.family": "DejaVu Sans", "pdf.fonttype": 42,
                         "text.color": INK, "axes.labelcolor": MUTED})
    destination = OUT / "report.pdf"
    with PdfPages(destination, metadata={"Title": "Nasdaq After Tax — Research Brief",
            "Author": "Nasdaq After Tax", "Subject": "Corrected Nasdaq-100 share portfolios and ETF: hypothetical Irish tax comparison"}) as pdf:
        for build in (overview, corrections_and_limits):
            fig = build(data)
            pdf.savefig(fig, facecolor=PAPER)
            if build is overview:
                fig.savefig(OUT / "strategy_comparison.png", dpi=170, facecolor=PAPER)
            plt.close(fig)
    marginal_chart(data)
    print(json.dumps({"report": str(destination.relative_to(ROOT.parent)), "pages": PAGE_COUNT,
                      "contributions_eur": data["manifest"]["contributions_eur"],
                      "best_final_cash": float(data["comparison"].final_cash.max())}, indent=2))


if __name__ == "__main__":
    main()
