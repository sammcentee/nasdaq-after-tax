"""Render the current study, accuracy assessment, and two matching charts."""
from pathlib import Path
import gzip
import hashlib
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.dates import DateFormatter, YearLocator
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results/latest"
ORDER = ["etf", "baseline", "monthly_tlh", "monthly_hybrid", "weekly_annual"]
LABELS = {
    "etf": "Hold the ETF",
    "baseline": "Buy underlying company shares directly; keep stocks that leave",
    "monthly_tlh": "Sell losing shares each month",
    "monthly_hybrid": "Sell losses monthly; sell former index stocks first in December",
    "weekly_annual": "Sell losses weekly; sell and rebuy current stocks in December",
}
DESCRIPTIONS = {
    "etf": "Fund tax on gains, including eight-year deemed disposal.",
    "baseline": "No voluntary sales before the final sale of everything.",
    "monthly_tlh": "Sell eligible losses; no December sales to use the exemption.",
    "monthly_hybrid": "Then sell and rebuy eligible current stocks to use remaining exemption.",
    "weekly_annual": "Sell at a covered profit; rebuy to reset the purchase cost for future CGT.",
}
UNDERPERFORMER_LABELS = {
    "any_loss": "Sell even tiny losses (from €1)",
    "retain_gains": "Keep stocks that leave the index",
    "monthly_gains": "Sell and rebuy profitable shares monthly",
}
UNDERPERFORMER_CONTROLS = {"annual_monthly_control": "A", "annual_only": "B"}
INK, MUTED, TEAL, LIME, CORAL = "#142F3B", "#596B72", "#087F80", "#C4EF68", "#B34D35"
PAPER, WHITE, LINE, SOFT = "#F5F4EE", "#FFFFFF", "#D9DFD9", "#E8EDE7"
NIGHT, PANEL, AQUA, BLUE, DIM = "#101F2D", "#1B2D3B", "#54DACB", "#83B5F3", "#B2C3CF"
SALMON = "#F29C88"
PAGE_COUNT = 8
ASSESSMENT_URL = "https://github.com/sammcentee/nasdaq-after-tax/blob/main/docs/ACCURACY_ASSESSMENT.md"


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
        "tax_relief": ["key", "label", "exemption_used_before_final_eur", "exemption_used_total_eur", "exemption_fully_used_before_final_years", "nominal_cgt_sheltered_by_exemption_eur", "tlh_realised_net_loss_eur", "terminal_loss_carry_eur"],
        "interactions": ["context", "loss_effect_without_gains_eur", "loss_effect_with_gains_eur", "gain_effect_without_losses_eur", "gain_effect_with_losses_eur", "interaction_eur"],
        "underperformers": ["key", "label", "comparator", "final_cash", "comparator_final_cash", "difference_vs_comparator_eur", "additional_transaction_cost_eur", "cgt_reduction_eur", "total_tax_reduction_eur", "additional_nominal_exemption_shelter_eur", "harvest_sale_count", "comparator_harvest_sale_count", "gain_harvest_sale_count", "comparator_gain_harvest_sale_count", "tlh_realised_net_loss_eur", "explanation"],
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
    weak = frames["underperformers"]
    if set(weak.key) != set(UNDERPERFORMER_LABELS) or len(weak) != 3:
        raise ValueError("Expected the three selected underperforming tax-management variants")
    if set(weak.comparator) != set(UNDERPERFORMER_CONTROLS):
        raise ValueError("Underperformer rows must identify the monthly-loss and no-loss matched controls")
    for _, group in weak.groupby("comparator"):
        if not np.allclose(group.comparator_final_cash, group.comparator_final_cash.iloc[0]):
            raise ValueError("Inconsistent final cash for the same underperformer comparator")
    frames["manifest"] = json.loads((OUT / "study_manifest.json").read_text())
    manifest = frames["manifest"]
    settings = manifest["contribution_schedule"]
    if (settings["type"], settings["review_month"], settings["deflation_policy"]) != ("irish_cpi_annual", 9, "track"):
        raise ValueError("This report expects September Irish CPI reviews that follow both inflation and deflation")
    schedule = pd.read_csv(OUT / settings["schedule_file"], parse_dates=["date"])
    if not {"date", "contribution_eur"}.issubset(schedule.columns) or schedule.empty:
        raise ValueError("A dated contribution schedule is required")
    if not schedule.date.is_monotonic_increasing or schedule.date.duplicated().any():
        raise ValueError("Contribution dates must be unique and increasing")
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
    manifest_hash = hashlib.sha256((OUT / "study_manifest.json").read_bytes()).hexdigest()
    for evidence in (sensitivity, frames["accuracy_audit"], frames["accuracy_replay"]):
        if manifest_hash != evidence["study_manifest_sha256"]:
            raise ValueError("Repeat the accuracy assessment for the current study manifest")
    if hashlib.sha256((OUT / "accuracy_sensitivities.csv").read_bytes()).hexdigest() != sensitivity["results_sha256"]:
        raise ValueError("Sensitivity results do not match their audit record")
    audit, replay, fund = (frames[name] for name in ("accuracy_audit", "accuracy_replay", "accuracy_etf_funding"))
    if (audit["arithmetic_checks"]["all_passed"] is not True or audit["manifest_hashes"]["all_match"] is not True
            or replay["all_match"] is not True or fund["published_summary_reproduced"] is not True
            or any(row["status"] != "PASS" for row in audit["ledger_checks"] + replay["files"])):
        raise ValueError("The report requires successful accuracy checks")
    for hashes in (manifest["input_sha256"], manifest["code_sha256"], sensitivity["code_sha256"],
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
    comparison = frames["comparison"].set_index("key")
    expected_gap = comparison.loc["weekly_annual", "final_cash"]-comparison.loc["etf", "final_cash"]
    if not np.isclose(expected_gap, audit["headline_decomposition"]["total_gap_eur"], rtol=0, atol=1e-6):
        raise ValueError("Accuracy assessment and headline balances disagree")
    return frames


def overview(data):
    comparison = data["comparison"].set_index("key")
    best = comparison.loc[comparison.final_cash.idxmax()]
    total = data["manifest"]["contributions_eur"]
    fig = page("Recreating an ETF, share by share.",
               "We buy and manage the Nasdaq-100's individual shares ourselves, then compare Irish taxes with owning an ETF.", 1)
    text(fig, .05, .790, "Provisional estimates. Substantial weight drift and execution limits affect interpretation. See the assessment on pages 5–8.", 9, CORAL)
    rounded_box(fig, .05, .177, .345, .585, NIGHT)
    rounded_box(fig, .075, .711, .223, .035, PANEL, .008)
    text(fig, .075, .730, "HIGHEST SELECTED RESULT", 9, LIME, "bold")
    text(fig, .072, .675, money(best.final_cash), 42, WHITE, "bold")
    text(fig, .075, .577, LABELS[best.name].replace("; ", ";\n").replace("current stocks", "current stocks\n"), 12, WHITE, "bold")
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
    text(fig, .05, .158, "All three active stock strategies: review former index stocks quarterly; sell only when the sale adds no CGT.", 10, weight="bold")
    text(fig, .05, .127, "December profit sales use existing losses first, then the remaining €1,270 exemption. Eligibility limits apply.", 9.5, MUTED)
    text(fig, .05, .098, f"€{total:,.2f} invested / 192 payments / 16 years. Nominal wealth; differences include holdings, costs and tax.", 9, MUTED)
    return fig


def effect(data, control, variant):
    rows = data["marginal_effects"]
    return rows.loc[rows.control.eq(control) & rows.variant.eq(variant)].iloc[0]


def attribution(data):
    fig = page("Where the gains came from.",
               "Change one rule at a time; compare complete portfolios after all taxes and costs.", 2)
    baseline = data["comparison"].set_index("key").loc["baseline", "final_cash"]
    steps = [effect(data, a, b).after_tax_gain_eur for a, b in
             [("baseline", "exits"), ("exits", "weekly_tlh"), ("weekly_tlh", "weekly_annual")]]
    text(fig, .05, .748, "THE WEEKLY STRATEGY, BUILT IN THREE STEPS", 9, TEAL, "bold")
    text(fig, .05, .701, f"{money(baseline)} → {money(baseline + sum(steps))}", 25, weight="bold")
    rounded_box(fig, .05, .350, .545, .300, NIGHT)
    ax = fig.add_axes([.096, .422, .475, .210], facecolor=NIGHT)
    cumulative = np.cumsum(steps)
    for i, (gain, top, color) in enumerate(zip(steps, cumulative, [BLUE, AQUA, AQUA])):
        ax.bar(i, gain, bottom=top-gain, width=.58, color=color, zorder=3)
        ax.text(i, top + 2300, money(gain, True), ha="center", fontsize=10, color=WHITE, weight="bold")
        ax.plot([i + .29, i + .71], [top, top], color=DIM, lw=.9, ls=(0, (2, 3)))
    ax.bar(3, sum(steps), width=.58, color=LIME, zorder=3)
    ax.text(3, sum(steps) + 2300, money(sum(steps), True), ha="center", fontsize=10, color=LIME, weight="bold")
    ax.set_xticks(range(4), ["01 / Sell former\nindex stocks\nquarterly", "02 / Sell losing\nshares\nweekly", "03 / Sell & rebuy\ncurrent stocks\nin December", "Combined\nchange"], fontsize=8, color=WHITE)
    ax.set_yticks([0, 20000, 40000], ["€0", "+€20k", "+€40k"], fontsize=8, color=DIM)
    ax.set_ylim(0, max(cumulative.max(), sum(steps)) * 1.20)
    ax.grid(axis="y", color=WHITE, alpha=.12, lw=.7, zorder=0)
    ax.tick_params(axis="both", length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    text(fig, .05, .322, "ALTERNATIVE: CHECK LOSSES MONTHLY", 8, TEAL, "bold")
    a = effect(data, "exits", "monthly_tlh").after_tax_gain_eur
    b = effect(data, "monthly_tlh", "monthly_hybrid").after_tax_gain_eur
    text(fig, .05, .286, f"{money(a, True)}: sell losses monthly. Then {money(b, True)}:", 11, weight="bold")
    text(fig, .05, .256, "sell former index stocks first in December; then sell & rebuy current stocks.", 8.5, MUTED)
    text(fig, .638, .748, "THE ANNUAL EXEMPTION: OFF → ON", 9, TEAL, "bold")
    for y, key, label in [(.505, "weekly_annual", "Weekly loss sales; December sell & rebuy"),
                           (.270, "monthly_hybrid", "Monthly loss sales; former stocks first")]:
        row = effect(data, "weekly_no_exemption" if key == "weekly_annual" else "hybrid_no_exemption", key)
        rounded_box(fig, .630, y, .320, .211, NIGHT)
        text(fig, .651, y + .187, label, 8, DIM, "bold")
        text(fig, .651, y + .144, money(row.after_tax_gain_eur, True), 26,
             LIME if row.after_tax_gain_eur >= 0 else SALMON, "bold")
        text(fig, .651, y + .084, "change in final wealth", 9, DIM)
        text(fig, .651, y + .043, f"Nominal exemption relief: {money(row.additional_nominal_exemption_shelter_eur)}", 10, WHITE)
    rule(fig, .05, .232, .90)
    text(fig, .05, .205,
         "The three steps add because each builds on the previous rule. The exemption cards are separate experiments.\n"
         "Wealth effects include holdings, costs and reinvestment. Nominal relief is exempt gains × 33%.\n"
         "Loss and gain harvesting interact: effects measured against different controls cannot simply be added.", 10, MUTED)
    return fig


def rules_and_misses(data):
    fig = page("How we manage our own index portfolio.",
               "Leading strategy: contributions, net dividends and sale proceeds top up eligible index stocks below their target weights.", 3)
    cards = [
        ("01 / EVERY FRIDAY", "Sell losing shares",
         "Sell a whole holding at ≥5% and ≥€25 loss.\nNo buy of that share class in prior 29 days;\nblock repurchase for 29 days afterwards.\nReinvest in other current index stocks."),
        ("02 / EACH QUARTER", "Sell former index stocks",
         "Sell when existing losses and remaining\nexemption cover the gain without extra\nCGT. Keep other departed holdings."),
        ("03 / EACH DECEMBER", "Sell and rebuy at a profit",
         "Sell eligible current stocks; buy them back.\nUse existing losses, then the remaining\n€1,270 exemption, to cover gains. Oldest\nshares sell first; no losing lots; fees apply."),
    ]
    for x, (cadence, title, body) in zip([.05, .36, .67], cards):
        box(fig, x, .505, .28, .25, WHITE)
        box(fig, x, .746, .28, .009, TEAL)
        text(fig, x + .016, .727, cadence, 8, TEAL, "bold")
        text(fig, x + .016, .684, title, 12, weight="bold")
        text(fig, x + .016, .635, body, 9.5)
    text(fig, .05, .476, "Monthly alternative: sell losses monthly. In December, sell former index stocks first; then sell and rebuy current stocks.", 9, MUTED)
    text(fig, .05, .416, "Three rules that fell behind.", 20, weight="bold")
    text(fig, .05, .361, "PREVIOUSLY WEAK RULES, REPLAYED", 8, MUTED, "bold")
    text(fig, .605, .361, "SHORTFALL VS CONTROL", 8, MUTED, "bold", ha="right")
    text(fig, .655, .361, "WHAT CHANGED", 8, MUTED, "bold")
    notes = {
        "any_loss": lambda r: f"{r.harvest_sale_count:,} loss sales vs {r.comparator_harvest_sale_count:,};\nfees and holdings changed.",
        "retain_gains": lambda r: "Kept former constituents;\nlower tax, lower final wealth.",
        "monthly_gains": lambda r: f"{r.gain_harvest_sale_count:,} gain sales vs {r.comparator_gain_harvest_sale_count:,};\nthe annual allowance stayed fixed.",
    }
    for y, r in zip([.317, .247, .177], data["underperformers"].itertuples()):
        rule(fig, .05, y + .015, .90)
        text(fig, .05, y, UNDERPERFORMER_LABELS[r.key], 11)
        text(fig, .605, y, money(r.difference_vs_comparator_eur, True), 17, CORAL, "bold", ha="right")
        text(fig, .655, y, notes[r.key](r), 9.5)
    text(fig, .05, .102,
         "Controls: sell former stocks quarterly; sell/rebuy current stocks each December. Monthly loss sales for rows 1/3; none for row 2.", 8, MUTED)
    return fig


def assumptions(data):
    schedule = data["contribution_schedule"]
    initial, final = schedule.contribution_eur.iloc[[0, -1]]
    total = data["manifest"]["contributions_eur"]
    fig = page("What the comparison assumes.",
               "Same scheduled funding. Frozen tax scenarios. A provisional historical reconstruction.", 4)
    text(fig, .05, .748, "CONTRIBUTIONS FOLLOW IRISH CPI", 9, TEAL, "bold")
    text(fig, .05, .703, f"€{initial:,.2f} → €{final:,.2f}", 29, weight="bold")
    text(fig, .05, .641, f"Per month  /  €{total:,.2f} contributed over 16 years", 10, MUTED)
    rounded_box(fig, .05, .432, .545, .181, NIGHT)
    ax = fig.add_axes([.095, .467, .405, .121], facecolor=NIGHT)
    ax.fill_between(schedule.date, initial, schedule.contribution_eur, step="post", color=AQUA, alpha=.16)
    ax.step(schedule.date, schedule.contribution_eur, where="post", color=AQUA, lw=2.2)
    reviews = schedule.loc[schedule.contribution_eur.ne(schedule.contribution_eur.shift())]
    ax.scatter(reviews.date, reviews.contribution_eur, s=9, color=AQUA, zorder=3, clip_on=False)
    ax.scatter(schedule.date.iloc[-1], final, s=38, color=LIME, edgecolors=NIGHT,
               linewidths=1, zorder=4, clip_on=False)
    ax.annotate(f"€{final:,.0f}", (schedule.date.iloc[-1], final), xytext=(9, 0),
                textcoords="offset points", fontsize=9, color=LIME, weight="bold", va="center")
    ax.xaxis.set_major_locator(YearLocator(5))
    ax.xaxis.set_major_formatter(DateFormatter("%Y"))
    ax.set_yticks([1000, 1150, 1300], ["€1,000", "€1,150", "€1,300"])
    ax.set_xlim(schedule.date.iloc[0], schedule.date.iloc[-1])
    padding = (schedule.contribution_eur.max() - schedule.contribution_eur.min()) * .2
    ax.set_ylim(schedule.contribution_eur.min() - padding * .5, schedule.contribution_eur.max() + padding)
    ax.tick_params(labelsize=8, length=0, colors=DIM, pad=5)
    ax.grid(axis="y", color=WHITE, alpha=.12, lw=.6)
    for spine in ax.spines.values():
        spine.set_visible(False)
    text(fig, .05, .409, "Each September: €1,000 × August CPI ÷ August 2010 CPI.", 10, weight="bold")
    text(fig, .05, .373,
         "Published data only; increases and decreases apply.\n"
         "Same scheduled flows; three stock deposits post next session.\n"
         "CSO CPI: December 2006=100; current, non-revised series.", 9, MUTED)
    rounded_box(fig, .630, .339, .320, .420, NIGHT)
    text(fig, .653, .730, "THE TAX SCENARIO", 9, LIME, "bold")
    taxes = [("33%", "STOCK CAPITAL GAINS"), ("€1,270", "ANNUAL CGT EXEMPTION"),
             ("52.35%", "DIVIDEND TAX"), ("38% / 8y", "FUND TAX / DEEMED DISPOSAL")]
    for y, (value, label) in zip([.680, .606, .532, .458], taxes):
        text(fig, .653, y, value, 20, WHITE, "bold")
        text(fig, .653, y - .045, label, 7.7, "#CFDAD9")
    text(fig, .653, .366, "No unrelated gains consume the allowance.", 8, "#CFDAD9")
    rule(fig, .05, .300, .90)
    text(fig, .05, .270, "READ THE RESULTS AS A BACKTEST", 8.5, TEAL, "bold")
    text(fig, .05, .233,
         "Strategies were selected retrospectively, not out of sample.\n"
         "Weights, membership and corporate actions remain provisional;\n"
         "some holdings use nontradable marks. Wealth is nominal.", 9.5, MUTED)
    text(fig, .550, .270, "COSTS & INTERPRETATION", 8.5, TEAL, "bold")
    text(fig, .550, .233,
         "0.15% FX each non-euro trade; no extra spread or slippage.\n"
         "ETF NAV includes fund costs. Tax rates are frozen scenarios,\n"
         "not each year's legislation. See the assessment on pages 5–8.", 9.5, MUTED)
    text(fig, .05, .125, "Research only. Not tax, legal or investment advice.", 10, weight="bold")
    text(fig, .05, .090, "Methodology, ledgers, source links and legal notice: README + study_manifest.json", 8, MUTED,
         url="../../../README.md")
    return fig


def accuracy_verdict(data):
    audit = data["accuracy_audit"]
    diagnostic = next(r for r in audit["portfolio_diagnostics"] if r["key"] == "weekly_annual")
    comparison = data["comparison"].set_index("key")
    fig = page("What the results can support.",
               "Accuracy assessment / 4 October 2026 / Numerical consistency does not establish real-world accuracy.", 5)
    rounded_box(fig, .05, .613, .90, .154, NIGHT)
    text(fig, .075, .740, "REPRODUCIBLE SCENARIO  /  LIMITED EVIDENCE OF REAL-WORLD PERFORMANCE", 10, LIME, "bold")
    text(fig, .075, .695,
         "The balances follow the checked model and cached inputs. The stock portfolio differs substantially from its targets.\n"
         "The study does not establish an executable, tax-compliant replica or a reliable forecast.\n"
         "There is no defensible overall accuracy percentage or measured error interval for final wealth.", 10, WHITE)
    text(fig, .05, .580, "THE ETF GAP IS NOT A PURE TAX BENEFIT", 9, TEAL, "bold")
    labels = ["ETF → direct-share baseline", "Then: quarterly departure sales",
              "Then: weekly loss sales", "Then: December gain sales"]
    for y, label, row in zip([.532, .485, .438, .391], labels, audit["headline_decomposition"]["steps"]):
        text(fig, .05, y, label, 10)
        text(fig, .525, y, money(row["change_eur"], True), 12, weight="bold", ha="right")
    rule(fig, .05, .352, .475)
    text(fig, .05, .329, "Total difference from the ETF", 10, weight="bold")
    text(fig, .525, .329, money(audit["headline_decomposition"]["total_gap_eur"], True), 18, TEAL, "bold", ha="right")
    text(fig, .05, .271,
         "These sequential policy effects include different securities,\n"
         "taxes, fees, and reinvestment. They depend on this path.\n"
         "Most of the gap exists before the extra sale rules.", 9.5, MUTED)
    text(fig, .590, .580, "TOP TEN SHARE CLASSES", 9, TEAL, "bold")
    for y, value, label, color in [(.521, diagnostic["top10_share_of_stock_value"], "Held stock value / 29 Sep 2026", TEAL),
                                   (.421, diagnostic["target_top10_weight"], "Last known targets / 31 Aug 2026", MUTED)]:
        text(fig, .590, y, f"{value:.2%}", 23, color, "bold")
        text(fig, .590, y-.053, label, 9, MUTED)
    text(fig, .590, .329,
         "Targets assumed available on 7 September.\n"
         "Different dates: this is target-weight drift,\n"
         "not contemporaneous ETF tracking error.\n"
         "Large weights in winners change risk and return.", 9.5, MUTED)
    gap = comparison.loc["weekly_annual", "final_cash"]-comparison.loc["monthly_hybrid", "final_cash"]
    rule(fig, .05, .183, .90)
    text(fig, .05, .161, f"The weekly strategy leads the monthly hybrid by only {money(gap)} ({gap/comparison.loc['monthly_hybrid', 'final_cash']:.2%}).", 11, weight="bold")
    text(fig, .05, .120, "One retrospectively selected market path does not prove an optimal strategy, equal risk, or future superiority.", 10, MUTED)
    return fig


def accuracy_limits(data):
    coverage = data["accuracy_data_audit"]["source_coverage"]
    marks = data["accuracy_data_audit"]["strategies"]["weekly_annual"]
    fig = page("Where realism is limited.",
               "Some limits have a measured scale. The combined effect on final wealth and strategy rank remains unknown.", 6)
    cards = [
        (.05, .559, "01 / HISTORICAL WEIGHTS", "Stale inputs; assumed release dates",
         f"Mean source age: {coverage['mean_snapshot_age_days']:.1f} days. Maximum: {coverage['maximum_snapshot_age_days']} days.\n"
         f"{coverage['dates_age_over_90_days']}/192 deposit dates use weights over 90 days old.\n"
         "Fund snapshots stay fixed between updates.\n"
         "Prior-date checks do not prove assumed release dates."),
        (.52, .559, "02 / PORTFOLIO EXECUTION", "Decisions and trades use the same close",
         "The model observes closing prices, then trades at them.\n"
         "It has no next-session execution validation.\n"
         "Ordinary dividends use ex-date cash accrual.\n"
         "ETF NAV and ECB FX are valuation references."),
        (.05, .328, "03 / INCOMPLETE CASH FLOWS", "Known omissions have a small direct scale",
         f"Weekly peak proxy marks / total portfolio: {marks['peak_provisional_weight']:.4%}.\n"
         "Five verified missing dividends total under €2 gross\n"
         "per stock case, at payment-date FX. The full total is unknown.\n"
         "Neither measure bounds valuation or portfolio errors."),
        (.52, .328, "04 / TAX CLASSIFICATION", "Core formulas have conditional support",
         "Loss ordering, exemption and fund credits agree with\n"
         "Revenue guidance under the stated assumptions.\n"
         "84 corporate-action classifications remain provisional.\n"
         "The weekly case encounters 33 of those actions."),
        (.05, .097, "05 / PERSONAL TAX AND DATES", "Frozen tax rates; approximate payment dates",
         "Rates do not reconstruct each year's legislation.\n"
         "Dividend tax and treaty credits depend on the investor.\n"
         "The €1,270 exemption is shared with other eligible gains.\n"
         "Tax reserves and settlement dates affect investable cash."),
        (.52, .097, "06 / BROKER FEASIBILITY", "Thousands of small fractional purchases",
         "Weekly case: 16,739 buys, median outlay €10.55.\n"
         "15,119 purchases buy less than one share.\n"
         "Historical instrument access is not reconstructed.\n"
         "Spreads, some charges and investor time are absent."),
    ]
    for x, y, tag, title, body in cards:
        box(fig, x, y, .43, .204, WHITE)
        text(fig, x+.014, y+.188, tag, 8, TEAL, "bold")
        text(fig, x+.014, y+.153, title, 11, weight="bold")
        text(fig, x+.014, y+.113, body, 9, MUTED)
    return fig


def accuracy_stresses(data):
    frame = data["accuracy_sensitivities"]
    fig = page("How assumptions change the result.",
               "Complete cost replays and ETF controls. Diagnostic scenarios, not calibrated costs or confidence intervals.", 7)
    text(fig, .05, .755, "STOCK CASES / FINAL AFTER-TAX WEALTH", 9, TEAL, "bold")
    for x, label in [(.05, "Strategy"), (.59, "Published costs"), (.77, "+5 bp per side"), (.95, "+25 bp per side")]:
        text(fig, x, .708, label, 9, MUTED, "bold", ha="left" if x == .05 else "right")
    for y, key, label in zip([.660, .612, .564, .516], ORDER[1:],
                            ["Retained-share baseline", "Monthly loss sales", "Monthly hybrid", "Weekly loss + annual gain sales"]):
        text(fig, .05, y, label, 11, weight="bold" if key == "weekly_annual" else "normal")
        for x, spread in zip([.59, .77, .95], [0, .0005, .0025]):
            row = frame.loc[frame.key.eq(key) & frame.extra_cost_per_side.eq(spread)].iloc[0]
            text(fig, x, y, money(row.final_cash), 12, TEAL if key == "weekly_annual" else INK, ha="right")
    text(fig, .05, .464,
         "The two monthly strategies reverse order at 25 bp. Weekly remains highest among these four cases.\n"
         "1 bp = 0.01%. FX stays at 0.15%. The extra cost also affects certain corporate cash receipts.", 9.5, MUTED)
    rule(fig, .05, .398, .90)
    text(fig, .05, .376, "ETF CONTROLS / SAME NAV AND CONTRIBUTIONS", 9, TEAL, "bold")
    etf = frame.loc[frame.asset.eq("etf")].set_index("scenario")
    labels = [("fund_tax_41_before_2026_38_from_2026", "41% before 2026, then 38% / rate-only change"),
              ("fund_tax_38_dd_0", "38% with no interim deemed disposal / hypothetical")]
    for y, (key, label) in zip([.331, .286], labels):
        text(fig, .05, y, label, 10)
        text(fig, .73, y, money(etf.loc[key, "final_cash"]), 12, weight="bold", ha="right")
        text(fig, .95, y, money(etf.loc[key, "difference_vs_published_same_strategy_eur"], True), 12, ha="right")
    text(fig, .05, .241, "No deemed disposal still includes final fund tax. It is not an available tax election.", 9, MUTED)
    text(fig, .05, .201, "ETF cash management: pay a same-day tax bill from the contribution before any unit sale.", 10, weight="bold")
    fund = data["accuracy_etf_funding"]
    text(fig, .05, .165,
         f"Independent control: {money(fund['same_date_contribution_first_sensitivity']['final_cash'])} final wealth, or "
         f"{money(fund['final_wealth_difference_eur'], True)}. Contribution dates and totals stay the same.", 10, MUTED)
    text(fig, .05, .119, "All controls retain other model limits. They do not establish an error range or resolve exposure and execution differences.", 9.5, CORAL)
    return fig


def accuracy_evidence(data):
    audit = data["accuracy_audit"]
    replay = data["accuracy_replay"]
    fig = page("What we checked. What remains open.",
               "Evidence supports arithmetic and specific model comparisons. It does not certify every input or legal interpretation.", 8)
    text(fig, .05, .752, "VERIFICATION COMPLETED", 9, TEAL, "bold")
    text(fig, .05, .709,
         f"Full replay: {replay['stock_replays']} stock cases and the ETF.\n"
         f"{replay['files_compared']} CSV/JSON outputs match exactly after parsing.\n"
         "122 existing unit and synthetic checks passed.\n"
         f"{audit['manifest_hashes']['count']} recorded input/code hashes match.\n"
         "Independent ledger checks: all 14 stock cases pass.\n"
         "Maximum cash residual is below €0.000001.\n"
         "Independent ETF lot arithmetic reproduces the baseline.", 11)
    text(fig, .05, .465, "LIMITS OF THAT VERIFICATION", 9, TEAL, "bold")
    text(fig, .05, .424,
         "A replay uses the same engine and cached inputs.\n"
         "Ledger checks detect arithmetic and consistency errors.\n"
         "They do not prove price accuracy or source completeness.\n"
         "Cost stresses keep same-close execution and selected history.\n"
         "Shared sources can contain shared errors.\n"
         "No independent holdout or probability of future success exists.", 10, MUTED)
    text(fig, .56, .752, "NEXT EVIDENCE NEEDED", 9, TEAL, "bold")
    text(fig, .56, .709,
         "Executable decisions with a later trade price.\n"
         "A comparison with matched investment exposures.\n"
         "Complete dividends and event-specific Irish tax treatment.\n"
         "A joint historical-rate and payment-date replay.\n"
         "Independent periods with rules fixed before evaluation.", 10.5)
    text(fig, .56, .509, "PRIMARY SOURCES / CLICK TO OPEN", 9, TEAL, "bold")
    sources = [
        ("Revenue / CGT and annual exemption", "https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/how-to-calculate-cgt.aspx"),
        ("Revenue / share identification and four-week rules", "https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/selling-or-disposing-of-shares.aspx"),
        ("Revenue / 2026 fund-tax rate", "https://www.revenue.ie/en/tax-professionals/ebrief/2026/no-0162026.aspx"),
        ("Revenue / fund tax and deemed-disposal credits", "https://www.revenue.ie/en/tax-professionals/tdm/income-tax-capital-gains-tax-corporation-tax/part-27/27-01a-02.pdf"),
        ("iShares / fund NAV and expenses", "https://www.ishares.com/uk/individual/en/products/253741/ishares-nasdaq-100-ucits-etf"),
        ("ECB / reference FX rates", "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html"),
    ]
    for y, (label, url) in zip([.468, .433, .398, .363, .328, .293], sources):
        text(fig, .56, y, label, 9, TEAL, url=url)
    rule(fig, .05, .218, .90)
    text(fig, .05, .193, "Full assessment, reproducible evidence, broker and issuer sources", 12, TEAL, "bold", url=ASSESSMENT_URL)
    text(fig, .05, .148,
         "docs/ACCURACY_ASSESSMENT.md · historical/checks/accuracy* · results/latest/accuracy*\n"
         "This is a documented software and research assessment. It is not an external financial audit or a Revenue ruling.", 9.5, MUTED)
    return fig


def marginal_chart(data):
    labels = {
        ("baseline", "exits"): "Sell former index stocks quarterly\nOnly when the sale adds no CGT",
        ("exits", "monthly_tlh"): "Add monthly sales of losing shares\nNo December profit sales",
        ("monthly_tlh", "monthly_hybrid"): "Add December profit sales: former stocks first\nThen sell and rebuy current stocks; losses monthly",
        ("exits", "weekly_tlh"): "Add weekly sales of losing shares\nNo December profit sales",
        ("weekly_tlh", "weekly_annual"): "Add December sales and rebuys at a profit\nCurrent index stocks only; losses weekly",
        ("weekly_no_exemption", "weekly_annual"): "Make the €1,270 exemption available\nWeekly loss sales; December sales and rebuys",
        ("hybrid_no_exemption", "monthly_hybrid"): "Make the €1,270 exemption available\nMonthly loss sales; former stocks first in December",
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
    ax.set_xticks(np.arange(0, limit + 1, 10000))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: "€0" if value == 0 else f"€{value/1000:,.0f}k"))
    ax.tick_params(length=0, colors=DIM, labelsize=8, pad=7)
    ax.grid(axis="x", color=WHITE, alpha=.10, lw=.6)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)
    text(fig, .04, .971, "NASDAQ AFTER TAX   /   MATCHED COMPARISONS", 8, LIME, "bold")
    text(fig, .04, .920, "What each change added.", 28, WHITE, "bold")
    text(fig, .04, .852, "Final wealth after tax and costs. Each row compares portfolios differing in one rule.", 11, DIM)
    text(fig, .055, .793, "01 / CHANGE A TRADING RULE", 8, AQUA, "bold")
    text(fig, .945, .793, "WEALTH CHANGE", 8, DIM, "bold", ha="right")
    text(fig, .055, .282, "02 / MAKE THE ANNUAL EXEMPTION AVAILABLE", 8, LIME, "bold")
    text(fig, .04, .045, "Different controls: do not add these bars. Wealth changes include holdings and reinvestment, not just tax savings.", 9, DIM)
    text(fig, .04, .021, "Hypothetical 2010–2026 study · CPI-indexed contributions · Full liquidation", 8, DIM)
    fig.savefig(OUT / "marginal_effects.png", dpi=180, facecolor=NIGHT)
    plt.close(fig)


def main():
    data = read_inputs()
    plt.rcParams.update({"font.family": "DejaVu Sans", "pdf.fonttype": 42,
                         "text.color": INK, "axes.labelcolor": MUTED})
    destination = OUT / "report.pdf"
    with PdfPages(destination, metadata={"Title": "Nasdaq After Tax — Research Brief",
            "Author": "Nasdaq After Tax", "Subject": "Recreating a Nasdaq-100 ETF with a self-managed share portfolio: hypothetical Irish tax comparison"}) as pdf:
        for build in (overview, attribution, rules_and_misses, assumptions,
                      accuracy_verdict, accuracy_limits, accuracy_stresses, accuracy_evidence):
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
