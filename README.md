<div align="center">

# ![Nasdaq After Tax](docs/assets/readme-header.svg)

**Recreate a Nasdaq-100 ETF by buying individual company shares directly, manage and rebalance it ourselves, then compare the Irish tax outcome.**

Starts at €1,000/month · Annual Irish CPI reviews · 16 years · €210,936.48 contributed

[Current results](#current-results) · [Robustness checks](historical/results/latest/robustness.csv) · [Two-page summary](historical/results/latest/report.pdf) · [Compare strategies](historical/results/latest/comparison.csv) · [Inspect marginal effects](historical/results/latest/marginal_effects.csv)

<sub>Python · Reproducible historical simulation</sub>

</div>

---

This project models **recreating a Nasdaq-100 ETF in our own brokerage account by buying the underlying company shares directly**. We aim to hold the full basket of underlying company shares in the available target proportions, and take responsibility for buying, rebalancing, reinvesting dividends and managing sales ourselves. The comparison asks what an Irish investor keeps after tax versus simply buying an accumulating ETF.

**How we keep the portfolio close to the index:** use historical membership and target weights with recorded availability dates. Some dates rely on assumed publication lags. New contributions, after-tax dividends and sale proceeds buy eligible current members below their target weights. New members become purchase targets once their weights are known; stocks that leave stop receiving new purchases. Each strategy below controls when holdings are sold, including for tax losses and the annual CGT exemption.

This is an approximate, self-managed replica. We allow holdings to drift instead of automatically selling every overweight stock to restore exact weights. Retained former members, purchase restrictions and missing data can leave differences or cash, so the model does not claim to own every constituent at every date.

**Results and transaction ledgers are hypothetical historical simulations.**

**Research only; not tax, legal or investment advice.** Read the [legal notice](#legal-notice) before relying on any material.

## Model fixes applied

The current study applies the corrections found during the accuracy review:

- **Later execution:** a closing-price decision fixes sale quantities or purchase cash budgets. Orders execute at a later eligible session. The ledger records both dates. Actual prices determine gains and tax. A planned loss can become a gain.
- **December timing:** annual gain reviews occur on 15 December, or the preceding weekday. Repurchases execute after the sale, on a later session. This leaves time before the tax year ends. The [timing controls](historical/results/latest/execution_timing.csv) separate this calendar change from the execution change.
- **ETF cash use:** a same-day contribution pays tax first. Only the shortfall requires a unit sale. This alone raises the ETF balance by €3,606 under otherwise identical assumptions.
- **Cash-flow repairs:** 42 CDK and LogMeIn dividend schedules now preserve entitlement before payment. Issuer reports confirm 41 payments. One remains declaration-only. All ex-dates are explicitly derived from exchange rules. Compulsory corporate cash receipts incur no trade FX fee.
- **Broader checks:** separate replays test different investment periods, later weight availability, added trading costs, and quarterly sales toward target weights. These are retrospective checks, not independent forecasts.

The corrections improve the model. Missing daily prices, assumed publication dates, personal tax details and corporate-action tax classifications still limit the results. No overall accuracy percentage is justified. The [earlier assessment](docs/ACCURACY_ASSESSMENT.md) is archived against its original revision.

## Current results

All five cases receive **€210,936.48 across 192 scheduled contributions**, then liquidate on 30 September 2026. Amounts are nominal euros after modelled taxes and costs. The changes below combine all corrections. They are not isolated execution effects.

| Strategy | Before corrections | Current result | Change |
|:---|---:|---:|---:|
| Hold the accumulating ETF | €750,729 | **€754,335** | +€3,606 |
| Direct shares; retain departed stocks | €952,619 | **€951,256** | −€1,363 |
| Monthly loss reviews | €988,601 | **€981,373** | −€7,227 |
| Monthly losses; December gains, departed stocks first | €994,222 | **€993,123** | −€1,099 |
| Weekly losses; December gains in current stocks | €998,425 | **€950,304** | −€48,121 |

**The former weekly winner no longer leads.** The monthly hybrid is highest among these five displayed cases. The tiny-loss variant in the wider 14-case study reaches €996,419. The earlier selection therefore does not establish an optimal rule. We retain the original comparison set instead of choosing a new winner after seeing the revised results.

![Final proceeds after modelled taxes and costs](historical/results/latest/strategy_comparison.png)

The gap from the ETF includes different holdings, concentration, costs, dividend treatment and tax timing. It is not a measure of tax savings alone. Before-correction values come from [commit 83afc81](https://github.com/sammcentee/nasdaq-after-tax/blob/83afc81af7c8f19ce180888b4a8286343f4677ba/historical/results/latest/comparison.csv). [Current balances](historical/results/latest/comparison.csv) and [all stock summaries](historical/results/latest/ledgers/all_summaries.json) provide the underlying figures.

## What the stronger checks show

- **Exposure matters.** Quarterly target trimming reduces the weekly portfolio's prefinal top-ten stock weight from 69.49% to 50.89%. Final wealth falls from €950,304 to €840,908. The last known targets allocate 46.38% to their top ten, at an earlier date. This is closer target concentration, not proof of equal ETF exposure or measured tracking error.
- **Publication timing matters.** An extra five business days before weights become available raises the weekly result to €995,389 and reverses the ranking. Later weights are not proven better. This shows that assumed release dates can materially change the conclusion.
- **No rule wins consistently.** Fixed rules are replayed over eight periods. Twelve of the 38 stock attempts cannot finish because a held security lacks a usable terminal quote. These failures remain visible. The complete shorter-period tests also reverse rankings. All periods reuse selected historical rules. None is an untouched holdout.
- **Timing effects are separate.** At unchanged December month-end review dates, later execution reduces weekly wealth by €27,658. Moving those reviews to 15 December reduces it by a further €20,527 on this path. The second change improves same-year exemption use but lowers wealth. Neither amount is pure tax savings.

The [robustness table](historical/results/latest/robustness.csv), [timing controls](historical/results/latest/execution_timing.csv), and [cost stresses](historical/results/latest/accuracy_sensitivities.csv) preserve the full results. The monthly hybrid remains ahead of the other three headline stock cases at the tested extra costs of 5 and 25 basis points per side.

**Verification:** 163 unit and synthetic checks pass. Independent ledger checks reconcile all 14 main stock cases. A fresh full replay reproduces 92 output files exactly after parsing. These checks establish software consistency. They do not validate every market input or tax classification.

## Why direct ownership changes the tax comparison

The model assumes an Irish-resident individual investing personally in ordinary company shares, compared with an accumulating Irish-domiciled ETF within the investment-fund tax regime. ETF classification and personal circumstances matter; this is not a rule for every product called an ETF.

| Tax question | Own the individual company shares | Own the accumulating ETF modelled here |
|:---|:---|:---|
| **Tax on gains** | Generally **33% CGT** on taxable realised gains, after allowable costs, losses and reliefs. | **38% fund tax** is the comparison assumption for taxable gains. |
| **Hold without selling** | Ordinary shares have **no eight-year deemed disposal**. Tax can still arise on dividends or other taxable events. | Gains can be taxed at each **eight-year anniversary of a purchase**, even without a sale. Earlier deemed-disposal tax is credited when calculating subsequent tax due. |
| **Annual exemption** | The **€1,270 personal CGT exemption** can shelter net gains each tax year. It is shared across the person's eligible gains, not available separately for every stock. | The ordinary €1,270 CGT exemption does not apply to this fund-tax regime. |
| **Loss harvesting** | Allowable realised losses can offset chargeable capital gains, with unused allowable losses carried forward. Share-matching and four-week repurchase restrictions matter. | No ordinary CGT loss netting against gains on other investments; credit or repayment of earlier deemed-disposal tax is a separate mechanism. |
| **Dividends** | Dividends are generally subject to Income Tax, USC and PRSI as applicable, even if reinvested. Foreign withholding and available tax credits must also be considered. | The accumulating fund retains its underlying income. Fund-level taxes affect NAV; investor-level fund tax is modelled on disposal and deemed disposal. |
| **Rebalancing** | Selling shares to follow index changes can realise taxable gains. The investor controls discretionary sales. | Trading inside the fund does not itself dispose of the investor's ETF units. Selling those units can trigger fund tax. |

Sources: Revenue's [CGT calculation and exemption](https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/how-to-calculate-cgt.aspx), [share-disposal rules](https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/selling-or-disposing-of-shares.aspx), [dividend guidance](https://www.revenue.ie/en/additional-incomes/dividend-income/index.aspx) and [investment-undertaking guidance](https://www.revenue.ie/en/tax-professionals/tdm/income-tax-capital-gains-tax-corporation-tax/part-27/27-01a-02.pdf).

The 38% fund rate applies from [1 January 2026](https://www.revenue.ie/en/tax-professionals/ebrief/2026/no-0162026.aspx). The study freezes its tax assumptions across the comparison period; it does not reconstruct each year's legislation. The 52.35% dividend-tax assumption is one modelled Income Tax/USC/PRSI scenario, not the rate for every higher-rate taxpayer.

The strategies test whether managing sales, harvesting eligible losses and using available annual CGT exemption can improve final after-tax wealth. Direct ownership also brings dividend taxes, trading costs, tracking differences and more record-keeping. All of those affect the comparison; a harvested loss is not an immediate cash refund, and a lower tax bill does not necessarily mean a better investment outcome.

## Contributions that follow Irish inflation

Monthly contributions start at **€1,000 in September 2010**. At each subsequent September review, the new monthly amount is **€1,000 × that August’s Irish all-items CPI ÷ August 2010 CPI (101.9)**, using the same December 2006 reference base. The August index must have been published before the review date. Round the result to cents and hold it through the following August; both inflation and deflation apply.

The 15 annual reviews produce **€210,936.48 across 192 contributions**, ending at **€1,301.28 per month** for September 2025–August 2026. The schedule includes reductions in September 2016 and September 2020. Every strategy uses the same scheduled amounts and dates; stock contributions scheduled for 30 March 2018, 31 May 2021 and 29 March 2024 post on the next available stock-market session.

These are **nominal euro results**, not final wealth expressed in constant purchasing power. This schedule invests **€18,936.48 more** than the earlier fixed-€1,000 study, so changes from that study’s final balances also reflect different cash contributions.

Source: CSO Ireland’s [CPM02 national CPI series](https://data.cso.ie/table/CPM02). The [contribution schedule](historical/results/latest/contribution_schedule.csv) records each payment, reference index and publication date. The [CPI methodology and provenance](historical/inflation/README.md) explain rounding and the current official snapshot: historical release dates are checked, but archived API vintages are not reconstructed.

## What do the extra sale rules contribute?

![Matched marginal effects on final after-tax wealth](historical/results/latest/marginal_effects.png)

Each comparison repeats the whole portfolio with one rule changed. On the corrected full-period path, December gain reviews change the monthly hybrid balance by **+€11,750**. December gain reviews change the weekly balance by **−€34,065**. These effects depend on the other rules and this historical path.

A harvested loss is not a cash refund. A lower cost basis can increase later tax. Nominal exemption relief is the used exemption multiplied by 33%. It is not extra terminal wealth.

Complete wealth effects include changed holdings, cash deployment, costs and taxes. Do not add effects from different controls. The [matched comparisons](historical/results/latest/marginal_effects.csv) and [interaction table](historical/results/latest/interactions.csv) retain those distinctions.

## How the stock strategies trade

| Review | Rule |
|:---|:---|
| Monthly contributions | Queue purchases of eligible current members below their last known target weights. Net dividends accumulate until a contribution date unless another disposal triggers investment. |
| Loss reviews | Use the signal price to test a whole-position loss of both 5% and €25. Require no same-class purchase in the preceding 29 days. Actual losing fills block repurchase for 29 days. |
| Quarterly departure reviews | Queue a whole-holding sale only when the signal estimate fits known losses and remaining exemption. Actual fill prices can create additional CGT. |
| Annual gain reviews | On 15 December, or the preceding weekday, use known losses first, then remaining €1,270 exemption capacity. The monthly hybrid considers departed stocks first. The weekly version considers current stocks. Same-stock repurchases require actual non-losing lots and available after-tax sale proceeds. |
| Quarterly target control | Separately trim eligible overweights toward dated targets, even if this realizes tax. Retained unweighted holdings, tax reserves, restrictions and later prices can prevent exact tracking. |
| Final liquidation | Cancel pending orders, require usable final quotes, sell the holdings, and settle remaining modelled taxes. |

The buy-and-hold stock baseline has no voluntary sales before final liquidation. Compulsory events still apply. The three active headline strategies share quarterly departure reviews. Their loss-review dates and December rules differ.

## Previously weak rules, tested again

These rules were weak in the earlier study. That label does not describe every corrected result: the €1 loss threshold now beats its matched control on the full-period path.

| Previously tested rule | Final wealth | Matched control key | Difference |
|:---|---:|:---|---:|
| Monthly losses from €1 | €996,419 | annual_monthly_control | +€6,896 |
| Retain departures; annual gain reviews | €954,519 | annual_only | −€27,445 |
| Monthly gain reviews | €955,859 | annual_monthly_control | −€33,663 |

`annual_monthly_control` uses monthly losses of at least 5% and €25, plus December gain reviews in current stocks. `annual_only` uses December gain reviews and quarterly departure sales, without voluntary loss harvesting. The [variant table](historical/results/latest/underperformers.csv) records taxes, costs and trade counts for each matched pair.

## Read and reproduce

| Artifact | Contents |
|:---|:---|
| [Current summary](historical/results/latest/report.pdf) | Two pages: corrected balances, applied fixes and remaining limits. |
| [Archived accuracy assessment](docs/ACCURACY_ASSESSMENT.md) | The pre-correction review, with evidence pinned to its original revision. |
| [Arithmetic and exposure audit](historical/results/latest/accuracy_audit.json) | Independent ledger checks, sequential wealth differences, concentration, and trade counts. |
| [Data accuracy evidence](historical/results/latest/accuracy_data_audit.json) | Source age, coverage, provisional marks, all 42 restored dividend schedules, and corrected corporate cash fees. |
| [Robustness checks](historical/results/latest/robustness.csv) | Eight investment periods, publication-delay controls and quarterly target-trimming controls. Unavailable cases remain explicit. |
| [Execution timing controls](historical/results/latest/execution_timing.csv) | Separate the effects of later execution and the December review date. |
| [Cost and tax sensitivities](historical/results/latest/accuracy_sensitivities.csv) | Complete cost replays and separate ETF tax controls. These are diagnostic scenarios. |
| [Independent ETF funding control](historical/results/latest/accuracy_etf_funding.json) | Independent lot arithmetic and a contribution-first tax-payment policy. |
| [Full replay verification](historical/results/latest/accuracy_replay.json) | Exact parsed-data agreement across 92 study outputs. |
| [Contribution schedule](historical/results/latest/contribution_schedule.csv) | All 192 payments, annual reviews, CPI observations and publication dates. |
| [Irish CPI inputs](historical/inflation/README.md) | Official source, funding formula, vintage limitations and provenance links. |
| [Headline comparison](historical/results/latest/comparison.csv) | ETF, baseline and three selected stock strategies. |
| [Matched effects](historical/results/latest/marginal_effects.csv) | Complete-control wealth differences, CGT changes, exemption relief and costs. |
| [Previously weak variants](historical/results/latest/underperformers.csv) | The selected variants replayed with CPI-indexed funding, their matched comparators and explanatory evidence. |
| [Tax relief](historical/results/latest/tax_relief.csv) | Actual exemption usage and realised loss-harvesting amounts. |
| [Annual tax ledger](historical/results/latest/annual_tax_and_exemptions.csv) | Year-by-year gains, losses, exemption use and carried losses. |
| [Study manifest](historical/results/latest/study_manifest.json) | Assumptions, selection caveats, freshness and input/code hashes. |
| [Policy definitions](historical/results/latest/policy_definitions.json) | Exact configurations for all stock replays and diagnostic controls. |
| [Independent ledger audit](historical/results/latest/independent_ledger_audit.json) | Cash, cost-basis, tax and trade-eligibility checks. |
| [Attribution audit](historical/results/latest/attribution_audit.json) | Checks that reported marginal effects and interactions match the underlying replays. |

Run from the repository root with the cached market inputs. The recorded environment uses **Python 3.14 on Linux**.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# Rebuild the report and charts from the current saved results.
python historical/run_tax_optimization_report.py

# Replay the stock strategies, controls and ETF benchmark.
python historical/run_tax_optimization_study.py --workers 3
```

Parallel execution uses Unix `fork`; use `--workers 1` where it is unavailable or memory is constrained. Replaying is substantially slower than rendering and overwrites the current generated study outputs.

```bash
python -m unittest discover -s historical/model -p 'test_*.py'
python -m unittest discover -s historical/tax -p 'test_*.py'
python -m unittest discover -s historical -p 'test_contributions.py'
python -m unittest discover -s historical -p 'test_verified_dividends.py'
python -m unittest discover -s historical/checks -p 'test_*.py'
python -m unittest discover -s historical/providers -p 'test_*.py'
python historical/checks/independent_policy_checks.py
python historical/checks/independent_checks.py
python historical/checks/audit_ledgers.py
python historical/checks/check_attribution.py

# Rebuild the accuracy evidence. Sensitivity replays take longer.
python historical/checks/assess_accuracy.py
python historical/checks/accuracy_data_checks.py
python historical/checks/accuracy_etf_funding.py
python historical/checks/accuracy_sensitivities.py --workers 3
python historical/checks/robustness_study.py --workers 3
python historical/checks/execution_timing_checks.py
python historical/checks/verify_replay.py --workers 3
python historical/run_tax_optimization_report.py
```

<details>
<summary><strong>Project map</strong></summary>

```text
historical/
├── model/                         ETF and individual-share engines; tests
├── tax/                           Irish tax helpers; tests
├── checks/                        Independent economic and ledger checks
├── benchmark/                     Issuer ETF benchmark and source audits
├── inflation/                     Irish CPI observations and publication evidence
├── inputs/                        Dated weights, membership and metadata
├── membership/                    Membership evidence and source tooling
├── prices/                        Market data and corporate-action repairs
├── results/latest/                One current report, tables, charts and ledgers
├── contributions.py               Publication-aware annual CPI contribution schedule
├── study_inputs.py                Shared input preparation
├── run_tax_optimization_study.py   Focused comparison and matched controls
└── run_tax_optimization_report.py  Current report and charts
```

Acquisition and repair scripts are separate from replay engines. Refreshing source data can change results; review the associated provenance and assumptions.

</details>

## Sources and acknowledgements

This study uses Quantiacs market data and toolbox code, historical membership work by Jeff McCarrell and thuningxu, iShares and SEC-filed fund holdings, Yahoo Finance via yfinance, Nasdaq/FRED series, ECB exchange rates, [Irish CPI from the Central Statistics Office](https://data.cso.ie/table/CPM02), and issuer, Revenue and broker documentation. See [source credits and third-party notices](THIRD_PARTY_NOTICES.md) for authors, upstream revisions, retained licences and links to the detailed provenance records; the [CPI source notes](historical/inflation/README.md) include the CSO attribution and licence.

A [free-data replacement](historical/providers/README.md) is being evaluated using Tiingo and the public-domain WIKI archive. The candidate readers are separate from the active study: existing figures still use the sources above, and no completed migration or new publication clearance is claimed.

## Assumptions that change the interpretation

- **Horizon:** 30 September 2010 to 30 September 2026; 192 monthly contributions. The period touches 17 calendar tax years.
- **Funding:** €1,000 initially, reviewed each September using already-published August CPI, with decreases allowed. Total nominal outlay is €210,936.48; all portfolio outcomes are nominal euros. The final CPI observation used is August 2025, with no 2026 inflation estimate needed.
- **Data freshness:** corrected stock prices through 30 September 2026; ETF/FX source cache contains observations through 2 October. Last eligible target weights are dated 31 August and available 7 September. September weights were not yet available for September decisions.
- **Frozen taxes:** 33% stock CGT, €1,270 annual exemption, 52.35% marginal dividend tax and 38% ETF fund tax. These are hypothetical comparison assumptions, not each year’s historical law or a person’s tax status.
- **Relief:** current and carried losses precede the exemption; unused exemption expires. No unrelated gains consume the allowance. Dividend withholding credits are included.
- **Costs:** 0.15% FX per non-euro market purchase and sale. No extra spread or slippage in the reference case. Compulsory cash receipts have no trade fee. Separate 5 and 25 basis-point stresses add market-trade costs. ETF NAV includes fund expenses and fund-level withholding. Historical broker availability and execution quality are not certified.
- **Provisional reconstruction:** historical weights, delisted-stock dividends, corporate-action tax treatment and some successor valuations remain incomplete or approximate. Some unquoted holdings use explicit nontradable marks. Small performance differences deserve caution.

Share matching and later winner repurchases are documented modelling interpretations, not a Revenue ruling. See Revenue’s guidance on [CGT calculation and exemption](https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/how-to-calculate-cgt.aspx) and [share disposals](https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/selling-or-disposing-of-shares.aspx).

## Licence

The project's original source code and associated documentation are licensed under the [MIT License](LICENSE), copyright (c) 2026 sammcentee. You may use, modify and redistribute them, including commercially, provided you retain the copyright and licence notices in copies or substantial portions of the software.

This licence does not cover third-party software, datasets, issuer documents or market-data-derived reports and results. Their existing terms and restrictions remain separate; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The research disclaimer below does not restrict uses permitted by the MIT License.

## Legal notice

**Research and educational use; Irish-law notice.** Nasdaq After Tax, including its source code, datasets, simulations, reports and documentation (the “Materials”), is made available without charge for general research and educational purposes. Nothing in the Materials is intended to constitute tax, legal, accounting or investment advice, a personalised recommendation, or an offer or solicitation to acquire or dispose of any investment. Publication, access or use does not, of itself, establish an adviser–client, fiduciary or other professional relationship with the authors, maintainers or contributors.

**Independent assessment.** The Materials do not take account of your circumstances. Independently verify their information and obtain advice from appropriately qualified professionals before making investment decisions, adopting a tax strategy or preparing a tax return. You remain responsible for your decisions and for complying with applicable tax and legal obligations.

**No assurance of outcomes.** Results are hypothetical historical simulations, subject to assumptions, data limitations and possible errors. They are not promises of future performance or confirmation that a tax treatment will be accepted by the Irish Revenue Commissioners or a court. Laws, guidance and market conditions may change.

**Disclaimer of warranties and limitation of liability.** To the fullest extent permitted by applicable law, the Materials are provided “as is” and “as available”, without warranties concerning accuracy, completeness, currency, suitability or fitness for a particular purpose. Subject to the following paragraph, the authors, maintainers and contributors exclude liability, whether in contract, tort (including negligence) or otherwise, arising from use of or reliance on the Materials, including investment losses, tax liabilities, penalties, interest and loss of data.

**Mandatory rights preserved.** Nothing in this notice excludes or limits liability for fraud or fraudulent misrepresentation, death or personal injury caused by negligence, or any liability that cannot lawfully be excluded or limited. Mandatory statutory rights and remedies, including applicable consumer protections, are preserved.

**Applicable law.** Insofar as a choice of law is legally effective, this notice is governed by Irish law. It does not displace mandatory protections under another applicable law or restrict any right to bring proceedings before a court having jurisdiction under mandatory law.
