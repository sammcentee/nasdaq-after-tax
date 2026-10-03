"""Render the current study as a four-page brief and two matching charts."""
from pathlib import Path
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.dates import DateFormatter, YearLocator
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results/latest"
ORDER = ["etf", "baseline", "monthly_tlh", "monthly_hybrid", "weekly_annual"]
LABELS = {
    "etf": "ETF / eight-year deemed disposal",
    "baseline": "Stock baseline / retain departures",
    "monthly_tlh": "Monthly loss harvesting",
    "monthly_hybrid": "Monthly losses + annual hybrid gains",
    "weekly_annual": "Weekly losses + annual same-share gains",
}
UNDERPERFORMER_LABELS = {
    "any_loss": "Harvest losses from €1",
    "retain_gains": "Keep departures; annual gains",
    "monthly_gains": "Review gains every month",
}
UNDERPERFORMER_CONTROLS = {"annual_monthly_control": "A", "annual_only": "B"}
INK, MUTED, TEAL, LIME, CORAL = "#142F3B", "#596B72", "#087F80", "#C4EF68", "#B34D35"
PAPER, WHITE, LINE, SOFT = "#F5F4EE", "#FFFFFF", "#D9DFD9", "#E8EDE7"
PAGE_COUNT = 4


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
    return frames


def overview(data):
    comparison = data["comparison"].set_index("key")
    best = comparison.loc[comparison.final_cash.idxmax()]
    total = data["manifest"]["contributions_eur"]
    fig = page("Nasdaq-100, after Irish tax.",
               "Individual shares versus an accumulating ETF under the modelled Irish tax rules.", 1)
    box(fig, .05, .177, .345, .585, INK)
    text(fig, .075, .730, "HIGHEST SELECTED RESULT", 9, LIME, "bold")
    text(fig, .072, .675, money(best.final_cash), 42, WHITE, "bold")
    text(fig, .075, .570, LABELS[best.name].replace(" + ", " +\n"), 13, WHITE, "bold")
    rule(fig, .075, .474, .292, "#46606A")
    for y, key, label in [(.443, "etf", "versus the ETF"), (.330, "baseline", "versus the stock baseline")]:
        text(fig, .075, y, money(best.final_cash - comparison.loc[key, "final_cash"], True), 25, LIME, "bold")
        text(fig, .075, y - .054, label, 10, "#CFDAD9")
    text(fig, .075, .218, "After liquidation, taxes and costs.", 9, "#CFDAD9")
    maximum = comparison.final_cash.max()
    colors = ["#A7B5BA", "#778F99", "#76B6AE", "#368E8B", TEAL]
    for i, key in enumerate(ORDER):
        y = .736 - i * .100
        row = comparison.loc[key]
        text(fig, .435, y, LABELS[key], 10, weight="bold" if key == best.name else "normal")
        text(fig, .95, y - .030, money(row.final_cash), 17, weight="bold", ha="right")
        box(fig, .435, y - .082, .515, .010, LINE)
        box(fig, .435, y - .082, .515 * row.final_cash / maximum, .010, colors[i])
    text(fig, .435, .215, "Baseline: retain departures; no discretionary harvesting.", 8.5, MUTED)
    text(fig, .05, .138, f"€{total:,.2f} invested  /  192 monthly payments  /  16 years", 11, weight="bold")
    text(fig, .05, .104, "Nominal euros. Selected historical cases; differences include changed holdings and reinvestment as well as tax.", 9, MUTED)
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
    ax = fig.add_axes([.087, .414, .488, .231], facecolor=PAPER)
    cumulative = np.cumsum(steps)
    for i, (gain, top, color) in enumerate(zip(steps, cumulative, ["#9ABFB7", "#4FA39E", TEAL])):
        ax.bar(i, gain, bottom=top-gain, width=.58, color=color, zorder=3)
        ax.text(i, top + 1800, money(gain, True), ha="center", fontsize=10, color=INK, weight="bold")
        ax.plot([i + .29, i + .71], [top, top], color=MUTED, lw=.8, ls=":")
    ax.bar(3, sum(steps), width=.58, color=INK, zorder=3)
    ax.text(3, sum(steps) + 1800, money(sum(steps), True), ha="center", fontsize=10, color=INK, weight="bold")
    ax.set_xticks(range(4), ["Quarterly\nexits", "Weekly\nlosses", "Annual\ngains", "Total"], fontsize=9)
    ax.set_yticks([0, 20000, 40000], ["€0", "+€20k", "+€40k"], fontsize=8, color=MUTED)
    ax.set_ylim(0, max(cumulative.max(), sum(steps)) * 1.20)
    ax.grid(axis="y", color=LINE, lw=.7, zorder=0)
    ax.tick_params(axis="both", length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    text(fig, .05, .322, "MONTHLY ALTERNATIVE  /  AFTER QUARTERLY EXITS", 8, TEAL, "bold")
    a = effect(data, "exits", "monthly_tlh").after_tax_gain_eur
    b = effect(data, "monthly_tlh", "monthly_hybrid").after_tax_gain_eur
    text(fig, .05, .281, f"{money(a, True)} losses  →  {money(b, True)} hybrid gains", 13, weight="bold")
    text(fig, .638, .748, "THE ANNUAL EXEMPTION: OFF → ON", 9, TEAL, "bold")
    for y, key, label in [(.505, "weekly_annual", "WEEKLY + ANNUAL GAINS"),
                           (.270, "monthly_hybrid", "MONTHLY + HYBRID GAINS")]:
        row = effect(data, "weekly_no_exemption" if key == "weekly_annual" else "hybrid_no_exemption", key)
        box(fig, .630, y, .320, .211, WHITE)
        text(fig, .651, y + .187, label, 8.5, MUTED, "bold")
        text(fig, .651, y + .144, money(row.after_tax_gain_eur, True), 26,
             TEAL if row.after_tax_gain_eur >= 0 else CORAL, "bold")
        text(fig, .651, y + .084, "change in final wealth", 9, MUTED)
        text(fig, .651, y + .043, f"Nominal exemption relief: {money(row.additional_nominal_exemption_shelter_eur)}", 10)
    rule(fig, .05, .232, .90)
    text(fig, .05, .205,
         "The three steps add because each builds on the previous rule. The exemption cards are separate experiments.\n"
         "Wealth effects include holdings, costs and reinvestment. Nominal relief is exempt gains × 33%.\n"
         "Loss and gain harvesting interact: effects measured against different controls cannot simply be added.", 10, MUTED)
    return fig


def rules_and_misses(data):
    fig = page("How the strategies traded.",
               "The leading strategy uses three scheduled reviews, with no foresight of later prices or losses.", 3)
    cards = [
        ("01 / EVERY FRIDAY", "Harvest meaningful losses",
         "Sell a whole holding at ≥5% and ≥€25 loss.\nNo same-class buy in the prior 29 days;\nblock repurchase for 29 days afterwards."),
        ("02 / EACH QUARTER", "Review departed stocks",
         "Sell when existing losses and remaining\nexemption cover the gain without extra\nCGT. Keep other departed holdings."),
        ("03 / EACH DECEMBER", "Use remaining tax capacity",
         "Sell eligible FIFO lots: losses first,\nthen the €1,270 exemption. Repurchase\ncurrent shares with non-losing lots;\npurchase restrictions and fees apply."),
    ]
    for x, (cadence, title, body) in zip([.05, .36, .67], cards):
        box(fig, x, .505, .28, .25, WHITE)
        box(fig, x, .746, .28, .009, TEAL)
        text(fig, x + .016, .727, cadence, 8, TEAL, "bold")
        text(fig, x + .016, .684, title, 12, weight="bold")
        text(fig, x + .016, .635, body, 9.5)
    text(fig, .05, .476, "Monthly hybrid: monthly loss reviews; annual gains sell departed holdings first, then restore eligible current shares.", 9, MUTED)
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
         "Controls: quarterly exits + annual same-share gains; monthly 5%/€25 loss reviews for rows 1 and 3, no voluntary losses for row 2.", 8, MUTED)
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
    ax = fig.add_axes([.093, .462, .469, .142], facecolor=PAPER)
    ax.fill_between(schedule.date, initial, schedule.contribution_eur, step="post", color=LIME, alpha=.65)
    ax.step(schedule.date, schedule.contribution_eur, where="post", color=TEAL, lw=2)
    ax.xaxis.set_major_locator(YearLocator(5))
    ax.xaxis.set_major_formatter(DateFormatter("%Y"))
    ax.set_yticks([1000, 1150, 1300], ["€1,000", "€1,150", "€1,300"])
    ax.set_xlim(schedule.date.iloc[0], schedule.date.iloc[-1])
    ax.tick_params(labelsize=8, length=0, colors=MUTED)
    ax.grid(axis="y", color=LINE, lw=.6)
    for spine in ax.spines.values():
        spine.set_visible(False)
    text(fig, .05, .409, "Each September: €1,000 × August CPI ÷ August 2010 CPI.", 10, weight="bold")
    text(fig, .05, .373,
         "Published data only; increases and decreases apply.\n"
         "Same scheduled flows; three stock deposits post next session.\n"
         "CSO CPI: December 2006=100; current, non-revised series.", 9, MUTED)
    box(fig, .630, .339, .320, .420, INK)
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
         "not each year's legislation. See the full modelling limitations.", 9.5, MUTED)
    text(fig, .05, .125, "Research only. Not tax, legal or investment advice.", 10, weight="bold")
    text(fig, .05, .090, "Methodology, ledgers, source links and legal notice: README + study_manifest.json", 8, MUTED,
         url="../../../README.md")
    return fig


def marginal_chart(data):
    labels = {
        ("baseline", "exits"): "Quarterly exits / harvesting off",
        ("exits", "monthly_tlh"): "Monthly losses / annual gains off",
        ("monthly_tlh", "monthly_hybrid"): "Annual hybrid gains / monthly losses",
        ("exits", "weekly_tlh"): "Weekly losses / annual gains off",
        ("weekly_tlh", "weekly_annual"): "Annual gains / weekly losses",
        ("weekly_no_exemption", "weekly_annual"): "Exemption on / weekly combined",
        ("hybrid_no_exemption", "monthly_hybrid"): "Exemption on / monthly hybrid",
    }
    shown = data["marginal_effects"].set_index(["control", "variant"]).loc[list(labels)]
    fig, ax = plt.subplots(figsize=(12, 5.7), facecolor=PAPER)
    fig.subplots_adjust(left=.365, right=.87, top=.79, bottom=.18)
    ax.set_facecolor(PAPER)
    values = shown.after_tax_gain_eur.to_numpy()
    positions = np.arange(len(values))
    ax.barh(positions, values, height=.58, color=[TEAL if v >= 0 else CORAL for v in values])
    ax.set_yticks(positions, list(labels.values()), fontsize=10)
    ax.invert_yaxis()
    limit = np.abs(values).max()
    ax.set_xlim(min(values.min(), 0)-limit*.12, max(values.max(), 0)+limit*.21)
    for y, value in zip(positions, values):
        ax.text(max(value, 0) + limit * .02, y, money(value, True),
                ha="left", va="center", fontsize=10, weight="bold", color=INK if value >= 0 else CORAL)
    ax.axvline(0, color=MUTED, lw=.8)
    ax.axhline(4.5, color=LINE, lw=1, ls=":")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"€{value/1000:,.0f}k"))
    ax.tick_params(length=0, colors=MUTED)
    ax.grid(axis="x", color=LINE, lw=.6)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)
    text(fig, .04, .94, "One rule. One matched comparison.", 24, weight="bold")
    text(fig, .04, .853, "Change in final after-tax wealth; each row has its own control.", 11, MUTED)
    text(fig, .04, .082, "Effects include changed holdings and costs. Exemption availability is a separate experiment from gain harvesting.", 9, MUTED)
    text(fig, .04, .045, "Selected historical cases · CPI-indexed contributions · Full liquidation", 8, MUTED)
    fig.savefig(OUT / "marginal_effects.png", dpi=170, facecolor=PAPER)
    plt.close(fig)


def main():
    data = read_inputs()
    plt.rcParams.update({"font.family": "DejaVu Sans", "pdf.fonttype": 42,
                         "text.color": INK, "axes.labelcolor": MUTED})
    destination = OUT / "report.pdf"
    with PdfPages(destination, metadata={"Title": "Nasdaq After Tax — Research Brief",
            "Author": "Nasdaq After Tax", "Subject": "Hypothetical Irish ETF and direct-share tax comparison"}) as pdf:
        for build in (overview, attribution, rules_and_misses, assumptions):
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
