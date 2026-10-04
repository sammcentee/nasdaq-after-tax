# Pre-correction accuracy assessment (archived)

**Historical record:** This assessment describes the results at commit `83afc81`, before the model corrections. Its balances and statements about missing features do not describe the current model. See the [current results and fixes](../README.md). Evidence links below point to that earlier revision.

Assessment date: 4 October 2026. Study period: 30 September 2010 to 30 September 2026.
The assessment covers the committed CPI-linked study and its cached inputs.

## Assessment

**The results support a conditional historical simulation. They do not establish the return of an executable, tax-compliant Nasdaq-100 replica.**

The arithmetic checks support the reported balances under the model's rules. That conclusion does not validate every price, dividend, tax classification, or execution assumption. The portfolio differs substantially from its target weights. The study also selects strategies after observation of the same historical path.

There is no defensible percentage for overall accuracy. There is no measured error interval for final wealth. Values to the nearest euro show simulation output precision, not real-world accuracy.

| Question | Assessment | Basis and limit |
|:---|:---|:---|
| Do the saved calculations agree? | Supported by independent ledger arithmetic and replay checks. | These checks use the same market inputs. They cannot detect every shared data error. |
| Does the ETF series represent the fund's historical value? | Stronger source support than the reconstructed stock basket. | The benchmark uses issuer NAV and ECB reference FX. Neither is a guaranteed execution price. |
| Does the stock portfolio closely replicate the ETF? | Not established. Substantial weight drift is present. | The selected weekly portfolio has about 70% in its ten largest share classes before final sale. |
| Are all cash flows and tax classifications complete? | No. | Verified missing dividends and provisional corporate-action treatment remain. Their total effect is unknown. |
| Can a retail investor execute the exact path? | Not established. | Same-close decisions, fractional orders, settlement assumptions, and historical instrument access require further checks. |
| Is the selected winner likely to win in future? | Not established. | One retrospectively selected market path provides no independent test of future superiority. |

## What the reported advantage measures

All cases receive 192 scheduled contributions with a total of €210,936.48. The model sells all assets at the end. Final balances are nominal euros. They are not constant-purchasing-power values or annual returns.

| Sequential comparison | Increase in final wealth |
|:---|---:|
| ETF → direct shares with retained former members | €201,890.00 |
| Direct-share baseline → quarterly tax-budget sales of former members | €27,379.73 |
| Quarterly sales → additional weekly loss sales | €9,107.50 |
| Weekly loss sales → additional December gain sales and repurchases | €9,318.89 |
| Total: ETF → selected weekly strategy | **€247,696.12** |

The final difference is 32.99% of the ETF's final balance. This is a terminal wealth difference, not annual outperformance. The direct-share baseline accounts for 81.51% of that difference before the three extra rules.

Each sequential stock comparison changes one policy and repeats the complete simulation. The differences therefore measure each policy's conditional wealth effect on this path. They include changes in tax, fees, securities, and reinvestment. They do not isolate tax savings alone.

The selected weekly strategy records €391,459.97 of total investor tax. The ETF records €330,840.48. Thus, the strategy with more final wealth also pays €60,619.49 more nominal tax. Neither tax total measures the return lost through early tax payments. A balance plus tax payments is an accounting total, not a no-tax counterfactual.

The weekly strategy exceeds the monthly hybrid by only €4,202.94, or 0.42% of the monthly balance. That narrow lead needs stronger evidence than the much larger ETF comparison. The two strategies also use different December rules. Their difference does not isolate weekly versus monthly loss reviews.

Sources: [headline balances](https://github.com/sammcentee/nasdaq-after-tax/blob/83afc81af7c8f19ce180888b4a8286343f4677ba/historical/results/latest/comparison.csv), [matched effects](https://github.com/sammcentee/nasdaq-after-tax/blob/83afc81af7c8f19ce180888b4a8286343f4677ba/historical/results/latest/marginal_effects.csv), and [arithmetic evidence](https://github.com/sammcentee/nasdaq-after-tax/blob/83afc81af7c8f19ce180888b4a8286343f4677ba/historical/results/latest/accuracy_audit.json).

## The portfolios have different investment exposures

New cash buys underweight members. The rules do not force sales of every overweight member. A successful stock can therefore grow far above its target weight.

Immediately before final liquidation, the weekly strategy's ten largest share classes represent approximately 70.00% of gross stock value. The last available target snapshot assigns approximately 46.38% to its ten largest share classes. NVIDIA represents approximately 15.68% of held stock value versus an 8.53% target. Apple represents approximately 14.23% versus 7.43%.

The position date is 29 September 2026. The target snapshot date is 31 August, with assumed availability on 7 September. These are different dates. The comparison measures drift from the model's last known targets. It is not a contemporaneous ETF tracking-error calculation. Both top-ten measures use share classes and can include two classes of one company.

Low exposure to former index members does not prove close index replication. Concentration within current members also matters. The study does not separate the ETF gap into tax, concentration, fund costs, and security-selection effects. A matched-exposure counterfactual is necessary for that claim.

Sources: [portfolio diagnostics](https://github.com/sammcentee/nasdaq-after-tax/blob/83afc81af7c8f19ce180888b4a8286343f4677ba/historical/results/latest/accuracy_audit.json), [dated target weights](https://github.com/sammcentee/nasdaq-after-tax/blob/83afc81af7c8f19ce180888b4a8286343f4677ba/historical/inputs/best_effort/best_effort_weights.csv), and [daily stock ledgers](https://github.com/sammcentee/nasdaq-after-tax/blob/83afc81af7c8f19ce180888b4a8286343f4677ba/historical/results/latest/ledgers).

## Data accuracy and information dates

### Strengths

The input process retains historical members and corporate actions. It does not replace every unavailable former member with a present-day survivor. Unresolved target weight reserves cash instead of redistribution to the covered names. These choices reduce two common sources of upward bias.

The ETF benchmark uses issuer NAV. Its source audit compares ECB API and ZIP observations and reconciles ten annual USD NAV returns to rounded issuer returns. The fund's NAV includes fund expenses and fund-level tax effects. A second deduction of the published expense ratio counts those expenses twice. The [issuer product page](https://www.ishares.com/uk/individual/en/products/253741/ishares-nasdaq-100-ucits-etf) identifies the accumulating Irish fund and its NAV methodology.

### Remaining limits

At the 192 scheduled contribution dates, source-weight age averages 48.08 days and reaches 213 days. Forty-two dates use weights more than 60 days old. Twenty-nine exceed 90 days. Ninety-one dates contain current members without source weights. The maximum is eleven such members.

Eighty-three dates contain unresolved source weight. Its mean across all 192 dates is 0.6243%, with a maximum of 2.5286%. These are input coverage measures, not portfolio-loss estimates. Target weights remain fixed between available snapshots. Fund snapshots and proxy weights do not reconstruct each daily official index weight.

The model enforces recorded availability dates before purchases. However, some availability dates rely on an assumed publication lag. The five-business-day lag for fund snapshots lacks complete archived release-time evidence. A date guard cannot verify the date supplied to it. Current corrected data also do not constitute a full archive of information as originally published.

Some unquoted successors use explicit nontradable valuation marks. The maximum combined marked-value exposure is approximately 0.1231% of gross portfolio value in the weekly case. This denominator includes cash before the CGT reserve deduction. The recorded value is small. It does not bound valuation errors, missing dividends, missed sale opportunities, or later effects on tax and allocation.

Cash-flow completeness fails a specific check. The stock ledgers omit four documented CDK dividends and one documented LogMeIn dividend while the portfolios hold those shares. These five payments imply less than €2 of omitted gross cash in each headline stock case, at payment-date FX. This amount is illustrative. It is not the complete missing-dividend total or a corrected final balance. The model normally uses ex-date accrual, so a full correction needs those dates and subsequent portfolio replays.

Primary evidence: [CDK fiscal 2021 annual report](https://www.sec.gov/Archives/edgar/data/1609702/000160970221000058/cdk-20210630.htm) and [LogMeIn September 2018 quarterly report](https://www.sec.gov/Archives/edgar/data/1420302/000156459018025208/logm-10q_20180930.htm). Local evidence: [data diagnostics](https://github.com/sammcentee/nasdaq-after-tax/blob/83afc81af7c8f19ce180888b4a8286343f4677ba/historical/results/latest/accuracy_data_audit.json), [benchmark source audit](https://github.com/sammcentee/nasdaq-after-tax/blob/83afc81af7c8f19ce180888b4a8286343f4677ba/historical/benchmark/issuer/benchmark_audit.json), and [provisional marks](https://github.com/sammcentee/nasdaq-after-tax/blob/83afc81af7c8f19ce180888b4a8286343f4677ba/historical/results/latest/input_audit/provisional_valuation_marks.json).

## Tax realism

### Rules with primary-source support

For the stated individual-share scenario, the 33% CGT rate and €1,270 annual exemption have primary-source support. Current and carried losses precede the exemption in the model. Unused exemption expires. Other personal gains can consume that exemption, but the main cases assume none. See [Revenue's CGT calculation guidance](https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/how-to-calculate-cgt.aspx).

The model's 38% fund-tax scenario applies a rate effective from 1 January 2026 throughout the study. Revenue confirms the 2026 change from 41%. The eight-year deemed-disposal framework and credit for previous deemed-disposal tax have primary-source support. Classification of the investor and fund remains necessary. See [Revenue eBrief 016/26](https://www.revenue.ie/en/tax-professionals/ebrief/2026/no-0162026.aspx) and [investment-undertaking guidance](https://www.revenue.ie/en/tax-professionals/tdm/income-tax-capital-gains-tax-corporation-tax/part-27/27-01a-02.pdf).

The ETF engine funds interim tax from sales inside the portfolio. It includes the tax on those sales. External cash does not subsidize those payments. This is a useful budget constraint, but it does not reproduce exact tax payment dates.

The engine invests a contribution before it pays a same-day tax bill. It then sells units to fund the bill. An independent control uses that day's available contribution for tax first and invests the remainder. This feasible cash-management change raises final ETF wealth by €3,606.30, to €754,335.15.

The control preserves contribution dates and totals. It retains all other price and tax assumptions. It is not an optimized payment policy. See the [independent ETF control](https://github.com/sammcentee/nasdaq-after-tax/blob/83afc81af7c8f19ce180888b4a8286343f4677ba/historical/results/latest/accuracy_etf_funding.json).

### Rules that require qualification

**Frozen rates are a scenario, not historical legislation.** Stock CGT, dividend tax, and fund tax remain fixed in the main comparison. An ETF control with 41% before 2026 and 38% thereafter addresses one rate difference only. It does not create a full historical-law reconstruction.

**The four-week rule has specific conditions.** The model excludes voluntary recent purchases. It also blocks voluntary repurchases for 29 days after loss sales. This is a conservative schedule within a simplified strategy.

Actual share identification, same-class purchases, compulsory receipts, and restricted-loss use still require review. Immediate repurchase after a gain does not establish eligibility for every real transaction. See [Revenue's share-disposal guidance](https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/selling-or-disposing-of-shares.aspx) and [section 581 guidance](https://www.revenue.ie/en/tax-professionals/documents/notes-for-guidance/tca/part19.pdf).

**Corporate-action tax treatment remains provisional.** Prepared inputs mark 84 actions as unverified rollover or basis assumptions. The weekly case encounters 33 such actions. US issuer cost-basis guidance supports economic terms but does not by itself establish Irish tax relief.

Vodafone's 2014 return of value illustrates the need for event-specific analysis. Revenue describes election and small-shareholder provisions that the generic event treatment does not establish. See [Revenue's Vodafone guidance](https://www.revenue.ie/en/tax-professionals/tdm/income-tax-capital-gains-tax-corporation-tax/part-19/19-04-06aa.pdf). The aggregate direction and size of any correction remain unknown.

**Dividend tax is one personal-tax scenario.** The model combines 40% Income Tax, 8% USC, and 4.35% PRSI. It assumes foreign-tax credits within its simplified rules. Those rates and credit entitlements do not apply to every investor or distribution. A generic withholding rate alone does not quantify the error, because the model credits withholding against Irish tax. See [Revenue's dividend guidance](https://www.revenue.ie/en/additional-incomes/dividend-income/index.aspx).

**Tax-payment dates are approximate.** The stock engine reserves tax and settles annual CGT in January. Revenue normally requires CGT payment by 15 December for January–November disposals and by 31 January for December disposals. Early dividend-tax deductions and immediate ETF tax settlement also affect investable cash. The net effect needs a dated cash-flow replay. See [Revenue's CGT payment dates](https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/when-and-how-do-you-pay-and-file-cgt.aspx).

## Execution and operational realism

The stock engine reads a day's closing prices, evaluates loss and gain rules, and trades at those prices. The historical close becomes known at the close. The study does not establish that every price-dependent order can execute at that same price. Source-date checks do not resolve this execution problem. A next-session or documented auction-execution experiment remains necessary. Its effect on wealth and rank is unknown.

The main stock case charges 0.15% FX on each non-euro purchase and sale. It adds no spread or slippage. Trading 212 documents the FX rate and separate exchange or government charges. Its fractional-share support covers most eligible instruments, not proof of access to every historical constituent. See [FX fees](https://helpcentre.trading212.com/hc/en-us/articles/360018909758-What-is-the-FX-fee-Invest-Stocks-ISA), [other charges](https://helpcentre.trading212.com/hc/en-us/articles/11471996799517-What-are-the-fees-in-the-Invest-ISAs-and-SIPP), and [fractional shares](https://helpcentre.trading212.com/hc/en-us/articles/9511997937437-Can-I-trade-with-fractional-shares).

The weekly case records 16,739 purchase rows, with a median outlay of €10.55. Of these, 8,102 are below €10. It also records 613 discretionary sales and 3,152 dividend rows. These are simulated events, not observed broker fills. Fractional quantities, minimum orders, price precision, settlement, corporate receipts, and administrative effort affect feasibility. The model assigns no cost to the investor's time or tax-return preparation.

Of those purchases, 15,119 buy less than one share. Trading 212 introduced fractional shares in December 2019, initially for 30 instruments. Thus, a study from 2010 with these capabilities is explicitly counterfactual for that broker. See the [broker's launch announcement](https://community.trading212.com/t/fractional-shares-are-here/140).

Corporate receipts also depend on broker support. The broker can supply cash instead of shares for some events. See its [corporate-action guidance](https://helpcentre.trading212.com/hc/en-us/articles/360020001898-Will-I-get-shares-from-mergers-spin-offs-acquisitions-or-stock-dividends).

The ETF comparison also has favorable execution assumptions. It trades at NAV converted with ECB reference FX, with no investor transaction charge or spread. The ECB says its reference rates are for information and discourages their use for transactions. This affects both the ETF conversion and stock euro values. See [ECB reference-rate guidance](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html).

The result is therefore not uniformly conservative for either side. Extra stock costs tend to reduce stock wealth with trades held fixed. Complete replays can also change eligibility and holdings. ETF costs, missing stock dividends, payment dates, and tax classifications can act in different directions.

One small cost mismatch has direct evidence. The model charges FX on some compulsory corporate cash receipts. Current broker guidance exempts these payments. Recorded or inferred charges total €17.43 in the weekly case and €14.17–€25.62 across the four stock cases.

These are direct fees only. A correction's later tax and portfolio effects need a replay. See [broker currency guidance](https://helpcentre.trading212.com/hc/en-us/articles/11669719976093-What-is-a-multi-currency-account) and the [data audit](https://github.com/sammcentee/nasdaq-after-tax/blob/83afc81af7c8f19ce180888b4a8286343f4677ba/historical/results/latest/accuracy_data_audit.json).

## Sensitivity evidence

The [sensitivity table](https://github.com/sammcentee/nasdaq-after-tax/blob/83afc81af7c8f19ce180888b4a8286343f4677ba/historical/results/latest/accuracy_sensitivities.csv) repeats the four headline stock cases with additional costs of 5 and 25 basis points per side. One basis point is 0.01%. The 0.15% FX assumption remains unchanged. The model's shared cost rule also affects certain corporate cash receipts.

These costs are diagnostic stresses. They are not measured broker spreads or confidence intervals. The experiment retains the same prices, tax assumptions, signal timing, and selected history. It therefore cannot resolve those limits.

| Stock case | Published cost scenario | Extra 5 bp per side | Extra 25 bp per side |
|:---|---:|---:|---:|
| Retained-share baseline | €952,619 | €951,682 | €947,947 |
| Monthly loss sales | €988,601 | €986,899 | €979,971 |
| Monthly hybrid | €994,222 | €993,187 | €978,787 |
| Weekly loss and annual gain sales | €998,425 | €996,425 | €983,080 |

The two monthly strategies reverse order at 25 bp. The weekly strategy remains highest among these four cases. Its advantage over the equally stressed baseline falls from €45,806 to €35,133. This supports robustness to these two cost stresses only.

The ETF controls change its tax rate or remove interim deemed disposal, with final fund tax retained. A no-deemed-disposal result is a counterfactual mechanism check. It is not an available tax election. No sensitivity in this assessment proves that the study's full uncertainty lies within these balances.

| ETF control | Final wealth | Change from published ETF |
|:---|---:|---:|
| Frozen 38%, deemed disposal | €750,729 | €0 |
| Frozen 41%, deemed disposal | €714,771 | −€35,958 |
| 41% before 2026, then 38% | €736,577 | −€14,152 |
| Frozen 38%, no interim deemed disposal | €870,578 | +€119,849 |

All taxable events in the ETF replay occur from October 2018. The dated-rate control therefore uses 41% for its pre-2026 events. A full historical comparison also needs the earlier stock CGT rates and each year's dividend rules. These ETF-only controls do not correct the direct-share results.

## Statistical limits and justified conclusions

The selected strategies came from an earlier 25-case exploration. A new contribution schedule on the same market path does not create an independent sample. Fourteen policy replays share prices and many rules. They are not fourteen independent observations of expected performance.

The study does not cover the Nasdaq collapse that began in 2000 or the 2008 crisis. Its start and end dates can favor some exposures and sale rules. The study has no untouched validation period, distribution of different start dates, or calibrated confidence interval for the strategy differences. Threshold choice, data repairs, and strategy selection all need consideration in any future validation.

Supported conclusions are narrow. The selected rules change final after-tax wealth in this model. The matched comparisons measure those changes correctly within the checked evidence. The study does not prove an optimal strategy, equal investment risk, a pure tax advantage of €247,696, or future superiority of direct shares.

The most useful next checks are an executable trade schedule, matched investment exposures, and independent market histories. Event-specific Irish tax review and complete dividend records are also necessary. Those checks address larger inference gaps than more decimal places or additional tests of the same formulas.

## Reproduction and audit scope

The PDF includes the main findings. The linked JSON and CSV files contain numerical evidence. The original study balances remain the reference results. The assessment does not silently replace them with an incomplete correction.

The full study replay reproduced all 14 stock cases and the ETF in an isolated copy. Ninety generated CSV and JSON files matched exactly after parsing. Gzip timestamps do not affect that comparison. See the [replay record](https://github.com/sammcentee/nasdaq-after-tax/blob/83afc81af7c8f19ce180888b4a8286343f4677ba/historical/results/latest/accuracy_replay.json).

The 122 existing unit and synthetic checks passed with the required Python import paths. They cover contributions, tax helpers, both engines, provider readers, and independent economic and policy cases. Independent arithmetic checks passed for all 14 saved stock ledgers. The largest cash residual was below €0.000001. All 21 hashes recorded in the study manifest matched their current files. These results establish consistency, not source completeness.

Five deliberate fault checks confirm that the report rejects failed arithmetic, replay, or ETF audits, stale source hashes, and mismatched headline balances. The PDF contains eight pages and clickable source links. Visual inspection and text-boundary checks found no clipped text in the generated document.

```bash
python historical/checks/assess_accuracy.py
python historical/checks/accuracy_data_checks.py
python historical/checks/accuracy_sensitivities.py
python historical/checks/accuracy_etf_funding.py
python historical/run_tax_optimization_report.py
```

The sensitivity command repeats portfolio simulations and takes longer than the arithmetic checks. Existing model, tax, contribution, and independent ledger checks remain part of the validation procedure in the [README](../README.md#read-and-reproduce).

The checks establish the stated software and arithmetic properties only. They are not an external financial audit, a Revenue ruling, or a certification of source-data completeness.
