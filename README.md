<div align="center">

# Nasdaq After Tax

**Owning the Nasdaq-100's shares directly versus buying its ETF: what changes after Irish tax?**

€1,000 per month · 16 years · €192,000 modelled contributions · Final liquidation

[Read the report](historical/results/latest/report.pdf) · [Compare strategies](historical/results/latest/comparison.csv) · [Inspect marginal effects](historical/results/latest/marginal_effects.csv)

<sub>Python · Reproducible historical simulation · No live account access or trading</sub>

</div>

---

This project asks **what an Irish investor would keep after tax if they bought the Nasdaq-100's individual company shares directly instead of owning them through an accumulating ETF**. The direct-stock portfolio aims to approximate the index, allowing some drift when trading would incur tax or costs.

The study follows dated index membership, invests monthly contributions, and accounts for dividends, rebalancing, tax-loss harvesting, use of the annual CGT exemption and final liquidation. Its central comparison is the tax treatment of direct share ownership against the ETF's fund-tax and eight-year deemed-disposal regime.

**Every contribution, tax band, account value and transaction ledger is hypothetical or simulated.** The repository does not describe anyone’s actual income, holdings or investment activity.

**Research only; not tax, legal or investment advice.** Read the [legal notice](#legal-notice) before relying on any material.

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

## One period. Five headline scenarios.

![Final proceeds after modelled taxes and costs](historical/results/latest/strategy_comparison.png)

The strongest selected result was **€952,181**, from weekly loss reviews plus annual same-share gain harvesting. Against the matched weekly-loss strategy, adding annual gain harvesting increased final wealth by **€10,476**; additional nominal exemption relief was **€5,948**. Those are different measures, not amounts to add together.

The current study keeps three stock strategies from an earlier, broader exploration, alongside an ETF benchmark and a simpler stock baseline. All use the same 16-year contribution horizon and final liquidation. **Strategy selection is retrospective**; causal trading rules do not make the selection an out-of-sample test.

| Scenario | What it does |
|:---|:---|
| **ETF benchmark** | Accumulating ETF with eight-year deemed disposal and a frozen 38% fund-tax assumption. |
| **Stock baseline** | Buys current constituents; retains departed holdings; no discretionary loss harvesting or annual gain review. |
| **Monthly loss harvesting** | Monthly loss reviews and quarterly reviews of departed stocks; no annual gain review. |
| **Monthly losses + annual hybrid gains** | Adds December gain harvesting: handle departed stocks first, then sell and repurchase eligible current holdings. |
| **Weekly losses + annual same-share gains** | Reviews losses each Friday; December gain harvesting sells and repurchases eligible current holdings. |

## What is the tax optimisation actually worth?

![Matched marginal effects on final after-tax wealth](historical/results/latest/marginal_effects.png)

Each bar compares two complete replays that differ in one rule. Additional diagnostic controls isolate departure management, loss harvesting, annual gain harvesting and the availability of the annual exemption.

These distinctions matter:

- **Final wealth change** includes taxes, costs, reinvestment and changes in which stocks were held. It is not all tax savings.
- **Nominal exemption relief** is the exemption actually used, multiplied by 33%. It is an accounting measure, not an extra amount to add to the final balance.
- **Gain harvesting and the annual exemption are different experiments.** Gain reviews use existing losses before the allowance and change acquisition costs; separate exemption-off replays test the allowance’s availability.
- **Do not add effects measured against different controls.** Resetting a share’s tax basis changes later loss opportunities, while using a loss bank can change whether a departed holding is sold. The [interaction table](historical/results/latest/interactions.csv) measures that dependence. Differences along a consistent sequence of controls do sum correctly.

Harvesting a loss does not automatically create a permanent benefit equal to the loss times the tax rate. Replacement shares can have a lower cost basis and a larger taxable gain later. The relevant outcome is wealth after all taxes and costs.

The weekly exemption-on/off sensitivity illustrates the feedback: final wealth changes by **€28,844**, while nominal exemption relief is **€6,368**. The larger figure includes the consequences of changed tax capacity for holdings and cash; it is not €28,844 of allowance tax savings.

## How the three stock strategies trade

| Review | Common execution rules |
|:---|:---|
| **Monthly contributions** | Invest €1,000 into eligible current constituents below their dated target weights. Reinvest dividends after tax. |
| **Loss harvesting** | Sell a whole eligible holding only when its euro loss after fees reaches **both 5% and €25**. Require no same-class purchase in the preceding 29 days, then block repurchase for 29 days. |
| **Quarterly departures** | Sell confirmed former constituents when known realised losses, carried losses and the available exemption cover the gain without increasing CGT at that review. Otherwise retain them. |
| **December gains, where enabled** | Use partial FIFO sales to absorb existing losses and then use remaining **€1,270 annual exemption** capacity. Eligible current-share replacements require non-losing selected lots and incur costs on both trades. |
| **Final liquidation** | Sell all remaining holdings using required terminal quotes and settle remaining modelled taxes and costs. |

Decisions use the information available at the review; they do not anticipate later losses, recoveries or index changes. FIFO means oldest shares are sold first. The hybrid rule directs departed-stock proceeds into current underweights; same-share replacement aims to preserve current exposure, subject to costs.

## What underperformed — and why

These are the three weakest active gain-harvesting variants from the earlier exploration, rerun on the same corrected data. The plain stock baseline is already shown above. Each shortfall below is measured against an otherwise matched strategy, rather than against the historical winner.

| Underperforming rule | Final after-tax wealth | Matched comparator | Shortfall |
|:---|---:|:---|---:|
| Harvest any monthly loss of at least €1 | €909,433 | Annual gains + monthly losses at 5% / €25 | −€33,870 |
| Retain departed stocks; annual gains, no loss harvesting | €910,238 | Same rules, with quarterly tax-budget exits | −€25,861 |
| Review gains monthly instead of annually | €912,876 | Same rules, with annual gain reviews | −€30,428 |

- **Harvesting tiny losses created much more activity for little extra loss relief.** Loss sales rose from 411 to 1,408, but realised losses increased by only €1,397. Recorded costs rose by €736, while nominal exemption relief fell by €120. Changed holdings, replacement purchases and cash deployment also affected returns; the fees alone do not explain the €33,870 shortfall.
- **Keeping departed holdings preserved exposure that underperformed on this path.** Average confirmed outside-index weight was 4.74%, versus 0.21% with tax-budget exits. This version paid €12,553 less total tax and €226 less in recorded costs, yet finished €25,861 behind. It still beat the plain retained-stock baseline by €4,256: annual gain harvesting helped, but did not make retention the better rule.
- **Monthly gain reviews did not create a larger annual allowance.** They produced 717 gain sales versus 199, with €80 less nominal exemption relief. Earlier basis resets and use of tax capacity changed later loss and departure decisions. The portfolio paid less tax but also generated less wealth; this was not simply a transaction-fee problem.

These observations explain the recorded differences, not a universal claim that a strategy can never work. The study does not establish which particular missed recoveries caused the shortfalls. [Underperformer results](historical/results/latest/underperformers.csv) include the controls, trade counts, tax and cost differences; the [independent audit](historical/results/latest/attribution_audit.json) reconciles the accounting changes.

## Read and reproduce

| Artifact | Contents |
|:---|:---|
| [Current report](historical/results/latest/report.pdf) | One five-page explanation of leading strategies, underperformers, marginal effects and limits. |
| [Headline comparison](historical/results/latest/comparison.csv) | ETF, baseline and three selected stock strategies. |
| [Matched effects](historical/results/latest/marginal_effects.csv) | Complete-control wealth differences, CGT changes, exemption relief and costs. |
| [Underperformers](historical/results/latest/underperformers.csv) | Three poor historical variants, their matched comparators and explanatory evidence. |
| [Tax relief](historical/results/latest/tax_relief.csv) | Actual exemption usage and realised loss-harvesting amounts. |
| [Annual tax ledger](historical/results/latest/annual_tax_and_exemptions.csv) | Year-by-year gains, losses, exemption use and carried losses. |
| [Study manifest](historical/results/latest/study_manifest.json) | Assumptions, selection caveats, freshness and input/code hashes. |
| [Policy definitions](historical/results/latest/policy_definitions.json) | Exact configurations for all stock replays and diagnostic controls. |
| [Independent ledger audit](historical/results/latest/independent_ledger_audit.json) | Cash, cost-basis, tax and trade-eligibility checks. |
| [Attribution audit](historical/results/latest/attribution_audit.json) | Checks that reported marginal effects and interactions match the underlying replays. |

Run from the repository root. The recorded environment uses **Python 3.14 on Linux**. Cached market inputs are sufficient; broker credentials are not required.

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
python historical/checks/independent_policy_checks.py
python historical/checks/independent_checks.py
python historical/checks/audit_ledgers.py
python historical/checks/check_attribution.py
```

<details>
<summary><strong>Project map</strong></summary>

```text
historical/
├── model/                         ETF and individual-share engines; tests
├── tax/                           Irish tax helpers; tests
├── checks/                        Independent economic and ledger checks
├── benchmark/                     Issuer ETF benchmark and source audits
├── inputs/                        Dated weights, membership and metadata
├── membership/                    Membership evidence and source tooling
├── prices/                        Market data and corporate-action repairs
├── results/latest/                One current report, tables, charts and ledgers
├── study_inputs.py                Shared input preparation
├── run_tax_optimization_study.py   Focused comparison and matched controls
└── run_tax_optimization_report.py  Current report and charts
```

Acquisition and repair scripts are separate from replay engines. Refreshing source data can change results; review the associated provenance and assumptions.

</details>

## Sources and acknowledgements

This study uses Quantiacs market data and toolbox code, historical membership work by Jeff McCarrell and thuningxu, iShares and SEC-filed fund holdings, Yahoo Finance via yfinance, Nasdaq/FRED series, ECB exchange rates, and issuer, Revenue and broker documentation. See [source credits and third-party notices](THIRD_PARTY_NOTICES.md) for authors, upstream revisions, retained licences and links to the detailed provenance records.

## Assumptions that change the interpretation

- **Horizon:** 30 September 2010 to 30 September 2026; 192 monthly contributions. The period touches 17 calendar tax years.
- **Data freshness:** corrected stock prices through 30 September 2026; ETF/FX source cache contains observations through 2 October. Last eligible target weights are dated 31 August and available 7 September. September weights were not yet available for September decisions.
- **Frozen taxes:** 33% stock CGT, €1,270 annual exemption, 52.35% marginal dividend tax and 38% ETF fund tax. These are hypothetical comparison assumptions, not each year’s historical law or a person’s tax status.
- **Relief:** current and carried losses precede the exemption; unused exemption expires. No unrelated gains consume the allowance. Dividend withholding credits are included.
- **Costs:** 0.15% FX per non-euro stock purchase and sale; no extra spread or slippage. ETF NAV includes fund expenses and fund-level withholding. Historical broker availability and execution quality are not certified.
- **Provisional reconstruction:** historical weights, delisted-stock dividends, corporate-action tax treatment and some successor valuations remain incomplete or approximate. Some unquoted holdings use explicit nontradable marks. Small performance differences deserve caution.

Share matching and immediate winner repurchases are documented modelling interpretations, not a Revenue ruling. See Revenue’s guidance on [CGT calculation and exemption](https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/how-to-calculate-cgt.aspx) and [share disposals](https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/selling-or-disposing-of-shares.aspx).

The historical runners place no broker orders. Keep credentials and personal account exports outside version control.

## Legal notice

**Research and educational use; Irish-law notice.** Nasdaq After Tax, including its source code, datasets, simulations, reports and documentation (the “Materials”), is made available without charge for general research and educational purposes. Nothing in the Materials is intended to constitute tax, legal, accounting or investment advice, a personalised recommendation, or an offer or solicitation to acquire or dispose of any investment. Publication, access or use does not, of itself, establish an adviser–client, fiduciary or other professional relationship with the authors, maintainers or contributors.

**Independent assessment.** The Materials do not take account of your circumstances. Independently verify their information and obtain advice from appropriately qualified professionals before making investment decisions, adopting a tax strategy or preparing a tax return. You remain responsible for your decisions and for complying with applicable tax and legal obligations.

**No assurance of outcomes.** Results are hypothetical historical simulations, subject to assumptions, data limitations and possible errors. They are not promises of future performance or confirmation that a tax treatment will be accepted by the Irish Revenue Commissioners or a court. Laws, guidance and market conditions may change.

**Disclaimer of warranties and limitation of liability.** To the fullest extent permitted by applicable law, the Materials are provided “as is” and “as available”, without warranties concerning accuracy, completeness, currency, suitability or fitness for a particular purpose. Subject to the following paragraph, the authors, maintainers and contributors exclude liability, whether in contract, tort (including negligence) or otherwise, arising from use of or reliance on the Materials, including investment losses, tax liabilities, penalties, interest and loss of data.

**Mandatory rights preserved.** Nothing in this notice excludes or limits liability for fraud or fraudulent misrepresentation, death or personal injury caused by negligence, or any liability that cannot lawfully be excluded or limited. Mandatory statutory rights and remedies, including applicable consumer protections, are preserved.

**Applicable law.** Insofar as a choice of law is legally effective, this notice is governed by Irish law. It does not displace mandatory protections under another applicable law or restrict any right to bring proceedings before a court having jurisdiction under mandatory law.
