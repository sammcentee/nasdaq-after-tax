# Sources and third-party notices

Nasdaq After Tax builds on the work of the authors and providers credited below. Source credits do not imply endorsement. Software licences apply to the identified software; they do not grant new rights in market data, issuer documents or other third-party material.

The root [MIT License](LICENSE) applies to this project's original source code and associated documentation. It does not relicense the third-party software, datasets, documentary evidence or market-data-derived reports and results described here. Retain the applicable upstream licences and notices; material without an explicit licence is not made MIT-licensed by inclusion in this repository.

## Copied software

### Quantiacs toolbox — QuantNet LLC and contributors

Copyright (c) 2019 QuantNet LLC. The full, unmodified MIT licence is retained in [historical/prices/LICENSE.quantiacs](historical/prices/LICENSE.quantiacs).

The following reference files were verified on 3 October 2026 to match [Quantiacs toolbox commit `9e5274c`](https://github.com/quantiacs/toolbox/tree/9e5274c5ce102a66debc799fd2a2300969fb90f6) byte for byte. The local filenames differ; the file contents are unchanged. The licence covers these five files, not this project's market-data caches or independently written research code.

| Local file | Original file at the verified revision |
|:---|:---|
| [qnt_common.py](historical/prices/qnt_common.py) | [qnt/data/common.py](https://github.com/quantiacs/toolbox/blob/9e5274c5ce102a66debc799fd2a2300969fb90f6/qnt/data/common.py) |
| [qnt_stocks.py](historical/prices/qnt_stocks.py) | [qnt/data/stocks.py](https://github.com/quantiacs/toolbox/blob/9e5274c5ce102a66debc799fd2a2300969fb90f6/qnt/data/stocks.py) |
| [qnt_secgov.py](historical/prices/qnt_secgov.py) | [qnt/data/secgov.py](https://github.com/quantiacs/toolbox/blob/9e5274c5ce102a66debc799fd2a2300969fb90f6/qnt/data/secgov.py) |
| [qnt_secgov_fundamental.py](historical/prices/qnt_secgov_fundamental.py) | [qnt/data/secgov_fundamental.py](https://github.com/quantiacs/toolbox/blob/9e5274c5ce102a66debc799fd2a2300969fb90f6/qnt/data/secgov_fundamental.py) |
| [qnt_secgov_indicators.py](historical/prices/qnt_secgov_indicators.py) | [qnt/data/secgov_indicators.py](https://github.com/quantiacs/toolbox/blob/9e5274c5ce102a66debc799fd2a2300969fb90f6/qnt/data/secgov_indicators.py) |

### Nasdaq-100 ticker history — Jeff McCarrell and contributors

Copyright (c) 2021 - 2025 Jeff McCarrell. The [n100tickers snapshot](historical/membership/n100tickers) comes from [upstream commit `cf7c894`](https://github.com/jmccarrell/n100tickers/tree/cf7c89419941316ff8523726ccba136125f2c11c). Its full [MIT licence](historical/membership/n100tickers/LICENSE) is retained. This source supplies historical membership evidence; project corrections are documented separately in the [membership audit](historical/membership/membership_coverage_audit.json). Upstream also credits [Wikipedia's Nasdaq-100 change history and its contributors](https://en.wikipedia.org/wiki/Nasdaq-100#Yearly_changes).

### Historical membership lists — thuningxu and contributors

The [sp500nq100 snapshot](historical/membership/sp500nq100) comes from [upstream commit `1cc1de2`](https://github.com/thuningxu/sp500nq100/tree/1cc1de2770874293597a418b41b079e5337b260c). No explicit software licence was found in that snapshot; this credit does not assign one. Its [README](historical/membership/sp500nq100/README.md) credits Wikipedia change tables and, for its S&P 500 data, [fja05680/sp500](https://github.com/fja05680/sp500). The upstream Nasdaq history draws on [Wikipedia's Nasdaq-100 article and its contributors](https://en.wikipedia.org/wiki/Nasdaq-100); the [article history](https://en.wikipedia.org/w/index.php?title=Nasdaq-100&action=history) records authorship. This snapshot is retained as membership research evidence, rather than as the sole authority for the current study.

## Data and documentary evidence

The table identifies the principal providers and how their material is used. Original URLs, dates, adjustments and limitations are recorded in the linked provenance files. Project reconstructions and simulations are the project's own calculations, not results published or approved by those providers.

| Source | Contribution and project provenance |
|:---|:---|
| [Quantiacs market data](https://quantiacs.com/documentation/en/user_guide/data.html) | Stock prices, distributions, split factors and asset identities, including successor securities. See the [download manifest](historical/prices/quantiacs_download_manifest.json) and [successor-data manifest](historical/prices/best_effort/general_download_manifest.json). The toolbox's MIT licence is a software licence, not a licence to the downloaded data. |
| [Yahoo Finance](https://finance.yahoo.com/) and [yfinance — Ran Aroussi and contributors](https://github.com/ranaroussi/yfinance) | Supplementary prices, distributions, splits, foreign-currency quotes and benchmark cross-checks. See the [Yahoo manifest](historical/prices/best_effort/yahoo_download_manifest.json) and [currency-price manifest](historical/prices/best_effort/foreign_currency_price_manifest.json). yfinance's software licence is separate from Yahoo and other providers' data terms. |
| [BlackRock / iShares Nasdaq 100 UCITS ETF](https://www.ishares.com/uk/individual/en/products/253741/ishares-nasdaq-100-ucits-etf) | Historical holdings support dated target weights; issuer NAV supplies the accepted ETF benchmark. See the [membership evidence](historical/membership/membership_coverage_audit.json) and [benchmark audit](historical/benchmark/issuer/benchmark_audit.json). |
| [Invesco PowerShares QQQ filings](https://www.sec.gov/Archives/edgar/data/1067839/000110465910064790/a10-18275_1n30b2.htm) and [USAA Nasdaq-100 Index Fund filings](https://www.sec.gov/Archives/edgar/data/908695/000090869510000170/ncsrsnas063010.htm), hosted by the US SEC's EDGAR service | Early holdings and dated fund reports support weight reconstruction. The [input manifest](historical/inputs/best_effort/manifest.json) identifies which observations are used, including the USAA initial and quarterly proxies. Credit for the filings belongs to their authors; SEC hosting identifies the access source. |
| [Nasdaq announcements](https://ir.nasdaq.com/node/69796) and [Nasdaq Trader notices](https://nasdaqtrader.com/TraderNews.aspx?id=fpnews2011-018) | Index membership changes, the 2011 special rebalance and corporate-action evidence. Specific notices are linked in the [membership audit](historical/membership/membership_coverage_audit.json) and individual [action records](historical/prices/best_effort/actions.csv). |
| Nasdaq index series via [FRED, Federal Reserve Bank of St. Louis](https://fred.stlouisfed.org/series/NASDAQ100/) | NASDAQ100 observations provide the study's trading calendar. NASDAQXNDX is retained as an additional index reference, rather than the accepted ETF return series. FRED identifies Nasdaq as the source of these series. |
| [European Central Bank reference exchange rates](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html) | EUR/USD reference rates convert USD prices and NAV to euros. See the [benchmark audit](historical/benchmark/issuer/benchmark_audit.json). Conversions and simulations are project calculations; the ECB does not supply broker execution rates. |
| [Central Statistics Office, Ireland — CPM02](https://data.cso.ie/table/CPM02) | All-items Irish CPI, December 2006=100, indexes monthly contributions at annual September reviews. Contains Irish Government Data licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), under the [CSO copyright policy](https://www.cso.ie/en/aboutus/whoweare/copyrightpolicy/). Statistical data © Government of Ireland, published by the Central Statistics Office. The project selected August observations, joined original release dates and calculated contributions; CSO does not endorse those calculations. See the [CPI source notes](historical/inflation/README.md) and [provenance](historical/inflation/provenance.json). |
| Issuer investor-relations releases, financial reports and SEC filings | Merger consideration, spin-offs, cancellations, splits and provisional valuation evidence. Each event retains its source in [actions.csv](historical/prices/best_effort/actions.csv); additional references appear in [primary_sources.json](historical/prices/repairs/primary_sources.json) and [study input preparation](historical/study_inputs.py). |
| [Irish Revenue Commissioners](https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/how-to-calculate-cgt.aspx) and the [Irish Statute Book](https://www.irishstatutebook.ie/eli/1997/act/39/section/581/enacted/en/html) | Tax guidance and legislation consulted for model assumptions. See the dated [tax evidence](historical/tax/evidence/irish_tax_optimization_evidence.json) and [current study manifest](historical/results/latest/study_manifest.json). The model's interpretations and frozen tax scenarios are not official guidance. |
| [Trading 212 Help Centre](https://helpcentre.trading212.com/hc/en-us/articles/34159237080861-Can-I-choose-the-currency-in-which-to-buy-sell-assets-for-Invest-accounts) and [API documentation](https://docs.trading212.com/api/accounts) | Public documentation informs broker currency assumptions; see [broker evidence](historical/tax/evidence/broker_currency_constraints.json). Historical availability and executable prices are not certified by the study. |

The Nasdaq-authored 2011 special-rebalance presentation was accessed through [Il Sole 24 Ore's document archive](https://st.ilsole24ore.com/pdf2010/SoleOnLine5/_Oggetti_Correlati/Documenti/Finanza%20e%20Mercati/2011/04/NDXSpecialRebalancePresentation%5B1%5D.pdf?uuid=d4dfeea2-5f69-11e0-b482-a582cb592628).

[Stooq](https://stooq.com/) was also queried during exploratory data recovery. The retained [attempt log](historical/prices/best_effort/stooq_download_manifest.json) records failed downloads; those responses are not price observations used by the current study. Likewise, cached Yahoo ETF quotes are cross-checks, while the accepted ETF benchmark uses issuer NAV and ECB exchange rates.

## Other software

The project also uses the Python packages and versions listed in [requirements.txt](requirements.txt) and [requirements-data.txt](requirements-data.txt). Credit belongs to their respective authors and contributors; their licences remain with the packages. Those dependencies are installed separately from the copied source snapshots identified above.
