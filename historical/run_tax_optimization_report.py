"""Render the current study as a four-page brief and two matching charts."""
from pathlib import Path
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
    "baseline": "Buy index shares; keep stocks that leave",
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
    return frames


def overview(data):
    comparison = data["comparison"].set_index("key")
    best = comparison.loc[comparison.final_cash.idxmax()]
    total = data["manifest"]["contributions_eur"]
    fig = page("Recreating an ETF, share by share.",
               "We buy and manage the Nasdaq-100's individual shares ourselves, then compare Irish taxes with owning an ETF.", 1)
    text(fig, .05, .790, "Target the full index; rebalance with fresh cash using dated weights. Tax rules and data gaps allow drift.", 9.5, MUTED)
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
         "not each year's legislation. See the full modelling limitations.", 9.5, MUTED)
    text(fig, .05, .125, "Research only. Not tax, legal or investment advice.", 10, weight="bold")
    text(fig, .05, .090, "Methodology, ledgers, source links and legal notice: README + study_manifest.json", 8, MUTED,
         url="../../../README.md")
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
