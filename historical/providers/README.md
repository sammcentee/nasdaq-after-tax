# Free market-data replacement

Reviewed 3 October 2026. **The current study still uses its existing inputs.** This directory prepares and tests replacement access; it does not certify a completed migration or relabel old results as independently sourced.

## Tiingo: free access, aggregate research outputs

[Tiingo's terms, sections 1.6(a) and 1.6(c)](https://app.tiingo.com/tos/) allow qualifying aggregate backtest outputs that cannot substitute for or reconstruct its data. The free plan requires transient processing in memory: no saved raw data, caches, backups or price-bearing ledgers. The reader therefore has no data writer. A subsequent study runner must respect the same restriction.

The [Starter plan](https://www.tiingo.com/about/pricing) offers 500 symbols per month, 50 requests per hour and 1,000 per day. A free account and API token are required. Public symbol lists include reservations; they do not prove historical prices exist. [Recycled ticker histories can be unavailable](https://www.tiingo.com/documentation/appendix/symbology).

The reader uses [unadjusted close, cash dividends and split factors](https://www.tiingo.com/documentation/end-of-day). Using total-return-adjusted close and also crediting dividends would double-count income. Dividend observations are dated on the ex-date; split factors can also reflect distributions and require corporate-action review.

## Run the access and coverage probe

Install `requirements-data.txt` in the project's virtual environment. Save the token as the only line in `private/tiingo.key`; `private/` is ignored by Git. Alternatively, set `TIINGO_API_KEY` in the process environment. The token is sent in an authentication header and is never printed.

```bash
.venv/bin/python historical/providers/tiingo.py \
  --symbols AAPL ALTR DELL SNDK LIFE CEPH BMC \
  --start 2010-09-01 --end 2026-09-30 \
  --key-file private/tiingo.key

.venv/bin/python -m unittest discover -s historical/providers -p 'test_*.py'
```

The probe reports aggregate counts only. It makes up to two calls per symbol and accepts at most 25 symbols; previous calls can consume part of the hourly allowance. Authentication and rate-limit failures stop the probe. Missing symbols are counted. No live-data test runs as part of the unit suite; its observations are invented examples.

**A successful probe does not establish issuer identity or complete study coverage.** In particular, modern ALTR, DELL, LIFE or SNDK observations must not silently stand in for older securities bearing those tickers. Dates must be checked against each holding's actual required interval, including its terminal corporate action.

## Historical supplement under investigation

Nasdaq describes the [WIKI stock-price dataset](https://data.nasdaq.com/databases/WIKIP) as public-domain prices, dividends and splits. It is a historical archive ending in 2018, so cannot replace the full study by itself. Archive coverage and old-issuer identity must be verified before any rows enter the model.

The extractor uses version 1 of the [marketneutral archive mirror](https://www.kaggle.com/datasets/marketneutral/quandl-wiki-prices-us-equites). It downloads approximately 463 MB to a temporary file, checks the ZIP and CSV schema, and retains only the requested symbols and dates. `extraction.json` records the archive hash, extract hashes, full source date bounds and selected row counts. The temporary archive is removed afterwards. The rights basis is Nasdaq's dataset-specific public-domain description; the mirror's generic licence field is marked unknown.

```bash
.venv/bin/python historical/providers/wiki.py \
  --symbols ALTR SNDK LIFE DELL BMC CEPH PPDI \
  --start 2010-09-01 --end 2018-03-27 \
  --output private/provider-migration/wiki
```

The archive check found candidate old Altera prices through 24 December 2015 and old SanDisk prices through 11 May 2016. Altera's five rows in March 2018 must be excluded as a later use of the same ticker. Old Dell has prices through 29 October 2013, followed by 35 zero-volume rows that must be excluded. Its dividend column is entirely zero, despite [Dell's annual report confirming cash dividends](https://www.sec.gov/Archives/edgar/data/826083/000082608313000005/dellfy1310k.htm), so that series needs independently verified repairs before tax modelling. The archive lacks BMC, CEPH and PPDI; its LIFE series starts in 2015 and does not cover the old Life Technologies holding. The extractor preserves the source observations for review and never declares candidates study-ready or substitutes an issuer automatically.

The migration inventory and candidate archive checks remain in ignored `private/provider-migration/`. Before switching the active study, independently source prices and identities, check held-date coverage and corporate actions, remove Quantiacs fallback dependencies, and rerun the tax comparisons. ETF NAV and historical weight sources require their own publication review. Only non-reconstructable aggregate outputs from Tiingo would be candidates for publication.
