"""Render the current study only: one five-page PDF and two shareable charts."""
from pathlib import Path
import json
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.dates import DateFormatter, YearLocator
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results/latest"
ORDER = ["etf", "baseline", "monthly_tlh", "monthly_hybrid", "weekly_annual"]
LABELS = {
    "etf": "ETF · deemed disposal",
    "baseline": "Stocks · retain departures",
    "monthly_tlh": "Monthly loss harvesting",
    "monthly_hybrid": "Monthly losses + annual hybrid gains",
    "weekly_annual": "Weekly losses + annual same-share gains",
}
SHORT = {
    "etf": "ETF",
    "baseline": "Stock baseline",
    "monthly_tlh": "Monthly losses",
    "monthly_hybrid": "Monthly + hybrid gains",
    "weekly_annual": "Weekly + same-share gains",
}
INK, MUTED, TEAL, GOLD, LINE = "#173544", "#536875", "#087f8c", "#bc7c26", "#dde6e9"
COLORS = ["#a8b8c1", "#6e8794", "#25a3a7", "#087f8c", "#173544"]
PAGE_COUNT = 5
UNDERPERFORMER_LABELS = {
    "any_loss": "Harvest any monthly loss ≥ €1",
    "monthly_gains": "Review gains every month",
    "retain_gains": "Retain departures; gains only",
}
UNDERPERFORMER_CONTROLS = {"annual_monthly_control": "A", "annual_only": "B"}


def money(value, signed=False):
    amount = float(value)
    if round(amount) == 0:
        amount = 0.0
    return f"€{amount:+,.0f}" if signed else f"€{amount:,.0f}"


def monthly_money(value):
    return f"€{float(value):,.2f}"


def contribution_summary(manifest, schedule):
    initial = float(schedule.contribution_eur.iloc[0])
    final = float(schedule.contribution_eur.iloc[-1])
    total = float(schedule.contribution_eur.sum())
    fixed_total = initial * len(schedule)
    change = total - fixed_total
    difference = (f"{money(abs(change))} {'more' if change > 0 else 'less'} contributed than keeping the initial monthly amount fixed"
                  if abs(change) >= .5 else "the same total contributions as keeping the initial monthly amount fixed")
    return dict(initial=initial, final=final, total=total, count=len(schedule),
                reviews=int(manifest["contribution_schedule"]["annual_reviews"]),
                difference_from_fixed=difference,
                subtitle=f"Starts at {money(initial)}/month · Irish CPI each September · {money(total)} contributed")


def contribution_chart(fig, schedule, summary):
    fig.text(.06, .852,
             f"Monthly amount: {monthly_money(summary['initial'])} initially → {monthly_money(summary['final'])} finally"
             f"  |  {summary['reviews']} anniversary reviews  |  {summary['count']} contributions",
             fontsize=9, color=INK)
    ax = fig.add_axes([.13, .685, .80, .135])
    ax.step(schedule.date, schedule.contribution_eur, where="post", color=TEAL, lw=1.8)
    reviews = schedule.loc[schedule.date.dt.month.eq(9)]
    ax.scatter(reviews.date, reviews.contribution_eur, s=10, color=TEAL, zorder=3)
    ax.xaxis.set_major_locator(YearLocator(4))
    ax.xaxis.set_major_formatter(DateFormatter("%Y"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"€{value:,.0f}"))
    ax.set_ylabel("Monthly contribution", fontsize=8)
    ax.tick_params(labelsize=8)
    ax.grid(axis="y", alpha=.17)
    ax.set_axisbelow(True)
    ax.set_xlim(schedule.date.iloc[0], schedule.date.iloc[-1])


def page(title, subtitle, number):
    fig = plt.figure(figsize=(11.7, 8.3), facecolor="white")
    fig.text(.06, .945, title, fontsize=21, weight="bold", color=INK)
    fig.text(.06, .900, subtitle, fontsize=10, color=MUTED)
    fig.text(.06, .03, "NASDAQ AFTER TAX  /  Hypothetical research  /  2010–2026", fontsize=8, color=MUTED)
    fig.text(.94, .03, f"{number} / {PAGE_COUNT}", fontsize=8, color=MUTED, ha="right")
    return fig


def paragraphs(fig, texts, y=.84, width=125, size=10, x=.06, gap=.018):
    for value in texts:
        wrapped = textwrap.fill(value, width=width)
        fig.text(x, y, wrapped, fontsize=size, color=INK, va="top", linespacing=1.4)
        y -= .024 * size / 10 * (wrapped.count("\n") + 1) + gap
    return y


def table(fig, rows, columns, box, widths, size=9):
    ax = fig.add_axes(box)
    ax.axis("off")
    tab = ax.table(cellText=rows, colLabels=columns, colWidths=widths,
                   cellLoc="right", bbox=[0, 0, 1, 1])
    tab.auto_set_font_size(False)
    tab.set_fontsize(size)
    for (r, c), cell in tab.get_celld().items():
        cell.set_edgecolor(LINE)
        cell.set_linewidth(.6)
        cell.PAD = .035
        if r == 0:
            cell.set_facecolor(INK)
            cell.set_text_props(color="white", weight="bold")
        elif r % 2:
            cell.set_facecolor("#f2f6f7")
        if c == 0:
            cell.set_text_props(ha="left")
    return tab


def strategy_bars(ax, comparison):
    values = comparison.final_cash.to_numpy()
    yy = np.arange(len(comparison))
    ax.barh(yy, values, color=COLORS, height=.6)
    ax.set_yticks(yy, [LABELS[k] for k in comparison.key], fontsize=10)
    ax.invert_yaxis()
    ax.set_xlim(0, max(values) * 1.19)
    for y, value in zip(yy, values):
        ax.text(value + max(values) * .014, y, money(value), va="center", color=INK, fontsize=11, weight="bold")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"€{x / 1e3:,.0f}k"))
    ax.grid(axis="x", alpha=.14)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    ax.set_xlabel("Nominal final cash after liquidation, modelled taxes and costs", color=MUTED)
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)


def context_label(value):
    return SHORT.get(value, str(value).replace("_", " ").capitalize())


def marginal_chart(data):
    height = max(5.3, 2.1 + .51 * len(data))
    fig, ax = plt.subplots(figsize=(12, height))
    fig.subplots_adjust(left=.43, right=.87, top=.84, bottom=.16)
    values = data.after_tax_gain_eur.to_numpy()
    yy = np.arange(len(data))
    labels = [f"{r.feature}\n{context_label(r.context)}" for r in data.itertuples()]
    ax.barh(yy, values, height=.66, color=[TEAL if value >= 0 else GOLD for value in values])
    ax.set_yticks(yy, labels, fontsize=9)
    ax.invert_yaxis()
    limit = max(float(np.abs(values).max()), 1)
    ax.set_xlim(min(float(values.min()), 0) - limit * .25, max(float(values.max()), 0) + limit * .32)
    for y, value in zip(yy, values):
        ax.text(value + limit * (.025 if value >= 0 else -.025), y, money(value, True),
                ha="left" if value >= 0 else "right", va="center", fontsize=9, color=INK)
    ax.axvline(0, color=INK, lw=.8)
    if "presentation" in data.columns:
        sensitivity = np.flatnonzero(data.presentation.to_numpy() == "sensitivity")
        if len(sensitivity) and sensitivity[0] > 0:
            ax.axhline(sensitivity[0] - .5, color=LINE, lw=1, ls="--")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"€{x / 1e3:,.0f}k"))
    ax.grid(axis="x", alpha=.15)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    ax.set_xlabel("Change in final after-tax wealth versus the matched control")
    fig.text(.04, .95, "What changes when one rule changes?", fontsize=20, weight="bold", color=INK)
    fig.text(.04, .90, "Matched comparisons · Effects include portfolio changes; do not sum effects from different controls", fontsize=10, color=MUTED)
    fig.text(.04, .04, "Annual exemption rows switch the allowance off/on. Gain-harvesting rows change trading rules; they are different experiments.", fontsize=9, color=MUTED)
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)
    fig.savefig(OUT / "marginal_effects.png", dpi=170, facecolor="white")
    plt.close(fig)


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


def underperformance_page(data, baseline_cash):
    fig = page("Previously weak rules, tested again", "Selected from the earlier fixed-contribution study; this replay uses matched CPI-indexed cashflows", 5)
    controls = data.groupby("comparator").comparator_final_cash.first().to_dict()
    paragraphs(fig, [
        f"Control A ({money(controls['annual_monthly_control'])}): monthly loss harvesting at 5% and €25, quarterly tax-budget departure reviews and annual same-share gain harvesting. Control B ({money(controls['annual_only'])}): the same departure and gain rules, without discretionary loss harvesting. Results include final liquidation, taxes and costs.",
    ], y=.842, width=136, size=9.6)
    rows = [[f"{UNDERPERFORMER_LABELS[r.key]}\nControl {UNDERPERFORMER_CONTROLS[r.comparator]}", money(r.final_cash), money(r.difference_vs_comparator_eur, True),
             money(r.additional_transaction_cost_eur, True), money(r.cgt_reduction_eur, True)] for r in data.itertuples()]
    table(fig, rows, ["Change / matched comparator", "Final cash", "Wealth change\nvs control", "Extra trading\ncosts", "CGT reduction\nvs control"],
          [.06, .565, .88, .175], [.39, .16, .16, .14, .15], size=9.2)
    notes = []
    for row in data.itertuples():
        baseline_note = f" Versus the plain stock baseline: {money(row.final_cash - baseline_cash, True)}." if row.key == "retain_gains" else ""
        notes.append(
            f"{UNDERPERFORMER_LABELS[row.key].upper()}  •  {str(row.explanation).strip()}{baseline_note}"
        )
    bottom = paragraphs(fig, notes, y=.512, width=139, size=9.1, gap=.010)
    if bottom < .255:
        raise ValueError("Underperformer explanations are too long for a readable fifth page")
    evidence = [[UNDERPERFORMER_LABELS[r.key],
                 f"{int(r.harvest_sale_count):,} / {int(r.comparator_harvest_sale_count):,}",
                 f"{int(r.gain_harvest_sale_count):,} / {int(r.comparator_gain_harvest_sale_count):,}",
                 money(r.tlh_realised_net_loss_eur), money(r.additional_nominal_exemption_shelter_eur, True)] for r in data.itertuples()]
    table(fig, evidence, ["Ledger evidence", "Loss sales\nvariant / control", "Gain sales\nvariant / control", "Net TLH\nlosses realised", "Extra nominal\nexemption relief"],
          [.06, .108, .88, .14], [.35, .16, .16, .16, .17], size=8.1)
    paragraphs(fig, [
        "Selection from the earlier study does not predetermine this replay's ranking. Fees, holdings, tax basis and later decisions all change; the comparisons do not separately attribute each mechanism. Lower tax can also reflect lower investment gains.",
    ], y=.082, width=144, size=8.5)
    return fig


def main():
    frames = read_inputs()
    manifest = frames["manifest"]
    schedule = frames["contribution_schedule"]
    contributions = contribution_summary(manifest, schedule)
    comparison, effects, relief, interactions = [frames[k] for k in ["comparison", "marginal_effects", "tax_relief", "interactions"]]
    shown_effects = effects.loc[effects.presentation.isin(["main", "sensitivity"])] if "presentation" in effects else effects
    weekly_exemption = effects.loc[effects.feature.eq("Annual exemption") & effects.variant.eq("weekly_annual")].iloc[0]
    by_key = comparison.set_index("key")
    best = comparison.loc[comparison.final_cash.idxmax()]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "text.color": INK, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": INK})
    chart, ax = plt.subplots(figsize=(12, 5.7))
    chart.subplots_adjust(left=.36, right=.97, bottom=.16, top=.81)
    strategy_bars(ax, comparison)
    chart.text(.035, .94, "Nasdaq-100, after Irish tax", fontsize=22, weight="bold", color=INK)
    chart.text(.035, .875, contributions["subtitle"], fontsize=10.5, color=MUTED)
    chart.savefig(OUT / "strategy_comparison.png", dpi=170, facecolor="white")
    plt.close(chart)
    marginal_chart(shown_effects)

    destination = OUT / "report.pdf"
    with PdfPages(destination, metadata={"Title": "Nasdaq After Tax — Current Study", "Author": "Nasdaq After Tax", "Subject": "Hypothetical Irish ETF and direct-share tax comparison"}) as pdf:
        fig = page("Nasdaq-100, after Irish tax", contributions["subtitle"], 1)
        ax = fig.add_axes([.355, .435, .60, .365])
        strategy_bars(ax, comparison)
        rows = [[SHORT[r.key], money(r.total_tax), money(r.transaction_costs), money(r.difference_vs_baseline_eur, True)] for r in comparison.itertuples()]
        table(fig, rows, ["Scenario", "Total modelled tax", "Trading costs", "Wealth vs stock baseline"],
              [.06, .18, .88, .205], [.40, .20, .18, .22], size=9)
        paragraphs(fig, [f"Highest selected result: {LABELS[best.key]} ({money(best.final_cash)}). Every strategy uses the same CPI-indexed contributions. Results are nominal, after final liquidation. The stock baseline retains departures without discretionary harvesting; differences include changed investments as well as tax."], y=.125, width=137, size=9)
        pdf.savefig(fig); plt.close(fig)

        fig = page("Measure each change against its own control", "Effects measured against different controls should not be added together", 2)
        rows = [[f"{r.feature}\n{context_label(r.context)}", money(r.after_tax_gain_eur, True), money(r.cgt_reduction_eur, True), money(r.additional_nominal_exemption_shelter_eur, True), money(r.additional_cost_eur, True)] for r in shown_effects.itertuples()]
        table(fig, rows, ["Feature / existing rules", "After-tax\nwealth change", "CGT\nreduction", "Extra nominal\nexemption relief", "Extra\ntrading costs"],
              [.06, .39, .88, .46], [.40, .16, .14, .17, .13], size=8.7 if len(rows) <= 8 else 7.8)
        notes = [
            "Wealth change compares complete replays. CGT reduction is the difference in modelled CGT paid; changed investments can also change taxable returns. Nominal exemption relief is 33% of the difference in exempt gains on the two ledgers. Neither number is a separate bonus to add to final wealth.",
            f"Exemption sensitivities switch the allowance off/on; gain-harvesting comparisons change trading rules. In the weekly case, the allowance changes full-strategy wealth by {money(weekly_exemption.after_tax_gain_eur)}, but nominal exemption relief is {money(weekly_exemption.additional_nominal_exemption_shelter_eur)}. Tax capacity changes later holdings and cash decisions: the wealth change is not an allowance tax saving. Four interaction-control pairs remain in marginal_effects.csv.",
        ]
        if len(interactions):
            interaction_text = "; ".join(f"{context_label(r.context)}: {money(r.interaction_eur, True)}" for r in interactions.itertuples())
            notes.append(f"Interaction between loss and gain harvesting: {interaction_text}. These measure how the loss-harvesting effect changes when gain harvesting is enabled. Standalone effects cannot simply be combined; differences along a consistent sequence of controls do sum correctly.")
        paragraphs(fig, notes, y=.335, width=134, size=9.3, gap=.015)
        pdf.savefig(fig); plt.close(fig)

        fig = page("The rules, and the relief actually used", "All three selected stock strategies review departed holdings quarterly", 3)
        rules = [
            ["Monthly loss harvesting", "Monthly losses; no annual gain review."],
            ["Monthly + hybrid gains", "Monthly losses; December gains sell departed holdings first, then restore current shares."],
            ["Weekly + same-share gains", "Friday loss reviews; December gains sell and repurchase eligible current shares."],
        ]
        table(fig, rules, ["Selected strategy", "Loss and gain review schedule"], [.06, .655, .88, .18], [.33, .67], size=9.2)
        rows = [[SHORT[r.key], money(r.exemption_used_before_final_eur), str(int(r.exemption_fully_used_before_final_years)), money(r.nominal_cgt_sheltered_by_exemption_eur), money(r.tlh_realised_net_loss_eur)] for r in relief.itertuples()]
        table(fig, rows, ["Strategy", "Exempt gains\nbefore final year", "Earlier years\nusing full allowance", "Nominal relief\nincluding final year", "Net losses from\nTLH disposals"],
              [.06, .415, .88, .19], [.32, .18, .16, .17, .17], size=8.6)
        paragraphs(fig, [
            "Loss review: sell an eligible whole holding when its euro loss after fees reaches both 5% and €25. Require no same-class purchase in the preceding 29 days and block repurchase for the next 29 days. Reinvest into eligible current underweights; every strategy shares the CPI-indexed contribution schedule.",
            "Departure review: sell confirmed former constituents only when existing realised losses, carried losses and the remaining exemption cover the gain without increasing CGT at that review. A profitable departure can therefore remain in the portfolio.",
            "Annual gain review: partial FIFO sales use losses before the €1,270 allowance. Same-share mode ranks by gain per euro sold; hybrid ranks departures then current overweights. Immediate replacement requires non-losing selected lots, current membership and the purchase restriction; both legs pay costs. Hybrid departure sales fund current underweights.",
            "Harvested losses are not permanent relief equal to loss × 33%: replacement shares can have lower cost basis and a larger later gain. This study touches 17 tax years, including partial 2010 and final-liquidation 2026. All figures are hypothetical; no unrelated gains consume the exemption.",
        ], y=.37, width=136, size=9.1, gap=.014)
        pdf.savefig(fig); plt.close(fig)

        fig = page("Contributions, evidence and practical limits", "Annual Irish CPI adjustments use information available at the time; all reported wealth is nominal", 4)
        contribution_chart(fig, schedule, contributions)
        paragraphs(fig, [
            f"CASHFLOWS  •  Each September: {monthly_money(contributions['initial'])} × August CPI / August 2010 CPI, rounded to cents and fixed for 12 payments. Both inflation and deflation apply. CSO all-items CPI uses December 2006=100 and releases predating each review; a current snapshot relies on CSO's non-revision policy. Identical scheduled amounts fund both cases; three stock payments post next trading session. There is {contributions['difference_from_fixed']}; wealth remains nominal.",
            "PERIOD AND INPUTS  •  30 September 2010 to 30 September 2026. Stock prices extend through the final session; ETF/FX observations through 2 October. Last usable weights: 31 August, available 7 September. September weights were unavailable until 7 October. Membership, weights, dividends and corporate actions remain provisional; some unquoted holdings use nontradable valuation marks.",
            "SELECTION  •  Strategies were selected retrospectively from the earlier fixed-contribution exploration. Causal trade rules do not make that selection an out-of-sample test. CPI-linked cashflows can change holdings, tax capacity, triggers and rankings. Matched controls describe this replay, not a universally best strategy.",
            "FROZEN TAX AND COSTS  •  33% share CGT; €1,270 annual exemption; 52.35% dividend tax; 38% ETF fund tax with eight-year deemed disposal. Losses precede the exemption; withholding credits are included. Non-euro share trades incur 0.15% FX per side; no extra spread or slippage is modelled. ETF NAV embeds fund costs. Assumed rates are not each year's law or anyone's actual tax status.",
            "INTERPRETATION  •  Share matching, foreign reorganisations and compulsory receipts retain documented assumptions. CGT reserves and annual settlements approximate payment timing. Audits check arithmetic and trade eligibility, not tax rulings, historical broker availability or executable fills.",
            "REPRODUCE LOCALLY  •  Run python historical/run_tax_optimization_study.py --workers 3 with the required inputs, then python historical/run_tax_optimization_report.py. Current tables, contribution_schedule.csv, ledgers and input/code hashes are in historical/results/latest/. The schedule records CPI evidence and availability; the manifest documents its method.",
        ], y=.632, width=139, size=9.0, gap=.013)
        fig.text(.06, .105, "Read the assumptions before interpreting small differences as an investable advantage.", fontsize=10, color=TEAL, weight="bold")
        fig.text(.06, .083, "Research only, not tax, legal or investment advice. See the README legal notice.", fontsize=8.2, color=MUTED)
        links = [
            ("Revenue · CGT calculation and exemption", "https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/how-to-calculate-cgt.aspx"),
            ("Revenue · Share matching restrictions", "https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/selling-or-disposing-of-shares.aspx"),
        ]
        for i, (label, url) in enumerate(links):
            fig.text(.06 + i * .46, .064, label, fontsize=8, color=TEAL, url=url)
        pdf.savefig(fig); plt.close(fig)
        fig = underperformance_page(frames["underperformers"], float(by_key.loc["baseline", "final_cash"]))
        pdf.savefig(fig); plt.close(fig)
    print(json.dumps({"report": "historical/results/latest/report.pdf", "pages": PAGE_COUNT,
                      "contributions_eur": contributions["total"],
                      "initial_monthly_eur": contributions["initial"],
                      "final_monthly_eur": contributions["final"],
                      "best_selected_historical_case": best.key,
                      "best_final_cash": float(best.final_cash),
                      "stock_baseline_final_cash": float(by_key.loc["baseline", "final_cash"])}, indent=2))


if __name__ == "__main__":
    main()
