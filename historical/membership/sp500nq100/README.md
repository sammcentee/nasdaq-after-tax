# S&P 500 / Nasdaq-100 historical membership

Point-in-time constituent lists for the **S&P 500** and **Nasdaq-100**, in the
[fja05680](https://github.com/fja05680/sp500) CSV format:

```
date,tickers
2007-02-01,"AAPL,ADBE,ADSK,..."
```

Each row is the **full membership snapshot effective on that date**. A new row
is emitted only when membership (or a constituent's ticker) changes. To get the
index on any date `D`, take the most recent row with `date <= D`.

| File | Range | Rows |
|---|---|---|
| `sp500_components_history.csv`     | 1996-01-02 .. present | ~2.7k |
| `nasdaq100_components_history.csv` | 2007-02-01 .. present | ~110 |

## How it's built

`build.py` parses the **structured "changes" tables** maintained on Wikipedia
(dated add/remove pairs with citations) — **not** raw page-history/revision
diffs, which are noisy (vandalism, reverts, formatting edits) and unnecessary.

- **S&P 500** — the [fja05680] file (1996 → 2026-01-14) is an authoritative,
  curated base and is kept **pinned** as a fixed historical anchor. Only the
  post-base gap is computed here, by applying the Wikipedia
  *"Selected changes to the list of S&P 500 components"* table **forward** from
  2026-01-14.
- **Nasdaq-100** — reconstructed **backward** from the current Wikipedia
  components table by un-applying the *"Component changes"* table (which reaches
  back to Feb 2007). This anchors on a state that is directly verifiable
  (today's index) instead of an old base, and turns any external reference
  (e.g. the [Reddit 2017 list]) into an optional cross-check rather than a
  dependency.

### Validation gates (run on every build)

- **S&P 500**: forward-reconstructed membership as-of today must equal the
  independently-parsed current components table → **PASS (identical)**.
- **Nasdaq-100**: the latest reconstructed snapshot must equal the current
  components table → **PASS (identical)**.
- Integrity: every recorded `add` must be present in the forward membership at
  its date (catches missing removals / renames). Residual: 2 (see below).
- Spot checks (first appearance): PLTR/MSTR/AXON `2024-12-23`, META `2022-06-09`,
  FB `2012-12-12`, GOOGL `2014-04-03`, TSLA `2013-07-15` — all correct.

## Ticker conventions

- Share classes use a **dot**: `BRK.B`, `BF.B`, `GOOGL`/`GOOG`.
- **Point-in-time symbols**: ticker renames (which are *not* index changes and
  are excluded from the Wikipedia changes tables by policy) are applied by date,
  so each snapshot shows the symbol that traded then. Handled explicitly:
  `BK→BNY` (2026-05-21), `FB→META` (2022-06-09), `PCLN→BKNG` (2018-02-27),
  `KFT→MDLZ` (2012-10-02), `HANS→MNST` (2012-01-05), `GOOG→GOOGL` class-A
  (2014-04-03), plus reconstruction-only pairings (`WTW/WLTW`, `TCOM/CTRP`,
  `WFM/WFMI`, `NWSA→`21CF, `FI→FISV`). A rename produces its own dated row.

## Known limitations

- **Pending changes are excluded** until effective. `--as-of` (default: today)
  is a hard cutoff; e.g. the S&P 500 `MRVL/FLEX ↔ POOL/CPB` swap announced for
  2026-06-22 is omitted from a June-6 build and will appear automatically once
  `as-of >= 2026-06-22`.
- **Nasdaq-100 pre-2017 is reliable but imperfect.** 2017→present is clean.
  Earlier, two removals are missing from Wikipedia's table — **ENDP** (added
  2015-12-21) and **CMCSK** (Comcast class K, added 2014-12-22) — so those names
  are absent for the windows they should occupy. A few departed constituents in
  2007-2014 may carry a later symbol, and the 2015-2017 multi-class era
  legitimately shows 105-108 securities (Google/Fox/Discovery/Liberty multi-class
  lines). None of this affects the modern, high-traffic window.
- **fja base is pinned** (the `(01-17-2026)` file). The Wikipedia bridge covers
  everything after 2026-01-14, so fja updates are not required; bump the URL in
  `build.py` only if you want to re-anchor.
- The [Reddit 2017] dataset could not be fetched (Reddit blocks automated
  access); it was only ever a cross-check / pre-2007 extension, not load-bearing.

## Updating (quarterly)

```bash
python build.py fetch     # re-download Wikipedia (keeps pinned fja base)
python build.py build     # reparse, reconstruct, validate, rewrite both CSVs
```

`fetch` pulls the current Wikipedia revisions; `build` recomputes as-of today.
New index changes published to the Wikipedia changes tables are picked up
automatically. Confirm both validation gates print **PASS** after each run.
Pass `--as-of YYYY-MM-DD` to reproduce membership as of a past date.

[fja05680]: https://github.com/fja05680/sp500
[Reddit 2017 list]: https://www.reddit.com/r/investing/comments/6kuf5y/nasdaq_100_component_history_by_date_industry/
