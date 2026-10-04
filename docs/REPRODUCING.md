# Reproduce the study

Run these commands from the repository root. The recorded environment uses Python 3.14 on Linux. Use the cached inputs to reproduce the saved study. A source refresh can change the results.

## Set up the environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Open or rebuild the report

Open the saved [two-page report](../historical/results/latest/report.pdf). To rebuild the report and charts from saved results, run:

```bash
python historical/run_tax_optimization_report.py
```

The report checks the saved evidence against the study files. If inputs, code or results change, repeat the applicable checks before you rebuild the report.

## Replay the portfolios

This command repeats the stock strategies, matched controls and ETF benchmark. It overwrites the main study outputs in `historical/results/latest/`.

```bash
python historical/run_tax_optimization_study.py --workers 3
```

Parallel execution uses Unix `fork`. Use `--workers 1` where `fork` is unavailable or memory is limited. A full replay takes substantially longer than a report rebuild.

## Repeat the checks

These commands check the engines, input readers, tax helpers, synthetic cases and saved ledgers.

```bash
python -m unittest discover -s historical/model -p 'test_*.py'
python -m unittest discover -s historical/tax -p 'test_*.py'
python -m unittest discover -s historical -p 'test_contributions.py'
python -m unittest discover -s historical -p 'test_verified_dividends.py'
python -m unittest discover -s historical -p 'test_input_repairs.py'
python -m unittest discover -s historical/checks -p 'test_*.py'
python -m unittest discover -s historical/providers -p 'test_*.py'
python historical/checks/independent_policy_checks.py
python historical/checks/independent_checks.py
python historical/checks/audit_ledgers.py
python historical/checks/check_daily_positions.py
python historical/checks/check_attribution.py
```

After a main study replay, repeat the evidence steps below in order. The cost, period and execution controls require additional portfolio replays. The final command rebuilds the report from the new evidence.

```bash
python historical/checks/assess_accuracy.py
python historical/checks/accuracy_data_checks.py
python historical/checks/accuracy_etf_funding.py
python historical/checks/accuracy_sensitivities.py --workers 3
python historical/checks/robustness_study.py --workers 3
python historical/checks/execution_timing_checks.py
python historical/checks/verify_replay.py --workers 3
python historical/run_tax_optimization_report.py
```

The execution controls also use Unix `fork`. These checks establish consistency under the model's rules. They do not validate every market input, historical broker feature or tax classification.

## Model rules

Monthly contributions start at €1,000 in September 2010. Each September review sets the amount to €1,000 × that August's Irish all-items CPI ÷ August 2010 CPI (101.9). The CPI series uses the December 2006 reference base. CSO must publish the August index before the review date. The model rounds the amount to cents and keeps it through the next August.

All strategies use the same scheduled contribution amounts and dates. Stock contributions that fall outside stock-market sessions move to the next available session. All outcomes use nominal euros. They do not express final wealth in constant purchasing power.

| Rule | Model behavior |
|:---|:---|
| Purchases | Contributions, net dividends and sale proceeds buy eligible current members below the last known target weights. Unresolved target weights reserve cash. |
| Stock baseline | No voluntary sales before final liquidation. Compulsory corporate events still apply. |
| Loss reviews | The signal price must indicate a whole-position loss of at least 5% and €25. Recent same-class purchases prevent a sale. Actual loss sales impose a 29-day voluntary repurchase block. |
| Departure reviews | The active headline cases review departures quarterly. Signal-date estimates seek whole-holding sales within known losses and the unused exemption. Later fill prices can create additional tax. |
| Annual gain reviews | Reviews occur on 15 December or the previous weekday. Current and carried losses precede the annual exemption. The monthly hybrid considers departed stocks first. The weekly version considers current stocks. |
| Execution | Signal dates fix sale units or purchase cash budgets. Orders execute at a later eligible session. Actual prices set gains, losses and tax. |
| Final liquidation | Pending orders are canceled. Usable final quotes are required. The model sells all holdings and settles remaining modeled taxes. |

The main study uses 33% CGT, a €1,270 annual exemption, 52.35% dividend tax and 38% fund tax throughout the period. These are fixed comparison assumptions. The model does not reconstruct each year's legislation. It assumes no unrelated gains consume the exemption. Tax reserves and January CGT settlements approximate payment dates.

The main stock case charges 0.15% FX per non-euro market purchase or sale. Compulsory corporate cash receipts incur no trade fee. Separate controls add 5 or 25 basis points per side. ETF NAV includes fund expenses and fund-level tax effects. Fractional orders and historical broker access remain assumptions.

The stock portfolios can retain departed members and drift from target weights. Some unquoted successors use explicit nontradable marks. Price and dividend coverage, assumed source publication dates and corporate-action tax classifications remain limits. The model's share-matching rules are not a Revenue decision.

Tax references: Revenue's [CGT calculation and exemption](https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/how-to-calculate-cgt.aspx), [share disposals](https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/selling-or-disposing-of-shares.aspx), [dividend guidance](https://www.revenue.ie/en/additional-incomes/dividend-income/index.aspx) and [investment-undertaking guidance](https://www.revenue.ie/en/tax-professionals/tdm/income-tax-capital-gains-tax-corporation-tax/part-27/27-01a-02.pdf).

## Results and evidence

| Artifact | Contents |
|:---|:---|
| [Latest review](../historical/results/latest/review_verification.json) | Verified checks, corrections, result changes and remaining limits from 4 October 2026. |
| [Study manifest](../historical/results/latest/study_manifest.json) | Assumptions, source dates and input/code hashes. |
| [Daily position audit](../historical/results/latest/daily_position_audit.json) | Holdings, cash, dividend claims and valuations rebuilt from transaction records for every main case. |
| [Policy definitions](../historical/results/latest/policy_definitions.json) | Configurations for all stock cases and matched controls. |
| [All stock summaries](../historical/results/latest/ledgers/all_summaries.json) | Results for the wider 14-case study. The five headline cases do not establish an optimal strategy. |
| [Contribution schedule](../historical/results/latest/contribution_schedule.csv) | Scheduled payments, CPI observations, annual reviews and publication dates. |
| [CPI methodology](../historical/inflation/README.md) | Official source, formula and current-snapshot limitations. |
| [Matched effects](../historical/results/latest/marginal_effects.csv) | Complete portfolio comparisons with one rule changed. Wealth effects include holdings, costs, tax and reinvestment. |
| [Interactions](../historical/results/latest/interactions.csv) | Combined rule effects. Effects from different controls must not be added. |
| [Previously weak variants](../historical/results/latest/underperformers.csv) | Retrospective variants and matched controls. The original labels do not describe every current result. |
| [Annual tax ledger](../historical/results/latest/annual_tax_and_exemptions.csv) | Gains, losses, exemption use and carried losses. |
| [Ledger audit](../historical/results/latest/independent_ledger_audit.json) | Cash, cost basis, tax and trade-eligibility checks. |
| [Attribution audit](../historical/results/latest/attribution_audit.json) | Agreement between reported effects and portfolio results. |
| [Arithmetic and exposure audit](../historical/results/latest/accuracy_audit.json) | Arithmetic, holdings concentration and trade counts. |
| [Data evidence](../historical/results/latest/accuracy_data_audit.json) | Source age, coverage, provisional marks and dividend evidence. |
| [ETF cash control](../historical/results/latest/accuracy_etf_funding.json) | Independent lot arithmetic and contribution-first tax payments. |
| [Cost and tax controls](../historical/results/latest/accuracy_sensitivities.csv) | Extra market-trade costs and separate ETF tax assumptions. |
| [Period and exposure controls](../historical/results/latest/robustness.csv) | Other periods, later weight availability and quarterly target sales. Failed cases remain explicit. |
| [Execution controls](../historical/results/latest/execution_timing.csv) | Separate effects of later execution and the December review date. |
| [Full replay check](../historical/results/latest/accuracy_replay.json) | Exact parsed-data comparison against a fresh run with the same cached inputs. |
| [Archived assessment](ACCURACY_ASSESSMENT.md) | Pre-correction findings, with evidence pinned to their original revision. |

All strategy choices and period controls reuse the historical record. They are retrospective comparisons, not independent forecasts or untouched holdout tests. The current December review date changes the strategy calendar as well as the earlier execution model. The execution controls separate those effects.

Acquisition and repair scripts are separate from the replay engines. The [candidate data readers](../historical/providers/README.md) are also separate from the active study. Their presence does not establish a completed source migration or publication permission. See [third-party notices](../THIRD_PARTY_NOTICES.md) for source attribution and terms.
