<div align="center">

# ![Nasdaq After Tax](docs/assets/readme-header.svg)

**Compare direct ownership of Nasdaq-100 shares with an accumulating ETF, after Irish taxes and costs.**

€1,000/month initially · Annual Irish CPI reviews · 16 years · €210,936.48 contributed

[View the report](historical/results/latest/report.pdf) · [Results table](historical/results/latest/comparison.csv) · [Reproduce the study](docs/REPRODUCING.md)

</div>

## What this project does

Nasdaq After Tax asks what an Irish investor keeps after tax from two approaches: buy an accumulating ETF, or buy the company shares directly. The direct-share strategies use historical Nasdaq-100 membership and target weights. They manage dividends, departed stocks, tax losses and the annual capital gains exemption.

New cash buys eligible shares below their target weights. Holdings can drift from those weights. The portfolios are approximate replicas of the index.

The ETF is **[iShares NASDAQ 100 UCITS ETF USD (Acc)](https://www.ishares.com/uk/individual/en/products/253741/ishares-nasdaq-100-ucits-etf)**, ISIN **IE00B53SZB19**. It is based in Ireland and reinvests dividends. The same share class trades as **CNDX** in London (USD) and **SXRV** on Xetra (EUR). The study uses the issuer's daily net asset value (NAV), converted to euros with ECB exchange rates.

## Results

The study runs from **30 September 2010 to 30 September 2026**. Each strategy receives **192 monthly contributions, for a total of €210,936.48**. All assets sell at the end. The figures below show final cash in nominal euros after the model's taxes and costs.

| Strategy | Final cash |
|:---|---:|
| Hold iShares NASDAQ 100 UCITS ETF (Acc) | **€754,335** |
| Hold direct shares and retain departed stocks | **€951,188** |
| Monthly loss reviews | **€981,304** |
| Monthly loss reviews; December gains, departed stocks first | **€993,051** |
| Weekly loss reviews; December gains in current stocks | **€950,234** |

The three active share strategies also review departed stocks quarterly. The monthly strategy with December gain reviews has the highest balance among these five cases. This comparison does not establish an optimal strategy.

![Final cash after modeled taxes and costs](historical/results/latest/strategy_comparison.png)

The difference from the ETF includes holdings, concentration, dividend treatment, costs and tax. **It is not a measure of tax savings alone.** The [two-page report](historical/results/latest/report.pdf) explains the results and their limits.

## Main assumptions

- **Contributions:** start at €1,000 per month. Each September, adjust the amount with the August Irish CPI published before that review. Both inflation and deflation apply.
- **Stock taxes:** fixed 33% capital gains tax, a €1,270 annual exemption and 52.35% dividend tax. The model includes loss relief and foreign withholding credits.
- **ETF taxes:** fixed 38% fund tax, with deemed disposal at each purchase's eight-year anniversary.
- **Trades:** share orders execute after the signal date. Annual gain reviews occur on 15 December or the previous weekday. Non-euro market trades incur a 0.15% FX fee. The reference case adds no spread or slippage.

These tax rates remain fixed throughout the comparison. They do not reproduce each year's legislation or every investor's personal tax position. ETF NAV includes fund expenses and fund-level taxes.

**The results are provisional historical simulations, not forecasts.** Prices, dividends, historical weights and some corporate-action tax treatments remain incomplete or approximate. Assumed publication dates and actual broker access also limit the comparison. Different investment periods, costs and trade dates can change the result and the order of the strategies.

## Use the study

Open the [report](historical/results/latest/report.pdf) to read the summary. The [comparison CSV](historical/results/latest/comparison.csv) contains the figures. The [robustness results](historical/results/latest/robustness.csv) compare other periods and assumptions.

For a local replay, follow the environment setup and commands in [Reproduce the study](docs/REPRODUCING.md). That guide also links the full strategy definitions, source records and checks.

## Sources and license

Sources include Quantiacs, historical membership research, iShares and SEC fund records, Yahoo Finance, Nasdaq/FRED, ECB exchange rates and Irish CPI from the Central Statistics Office. See the [source credits and third-party notices](THIRD_PARTY_NOTICES.md) and [CPI source notes](historical/inflation/README.md).

Original source code and documentation use the [MIT License](LICENSE). Third-party software, data, documents and derived results retain their separate terms.

**Research only. No tax, legal or investment advice.** Read the [legal notice](LEGAL.md).
