"""Normalize the saved primary-source CNDX NAV and ECB FX downloads.

Run with standard-library Python. Uses same-day ECB reference FX, or the latest
earlier reference observation on holidays; never a future rate. NAV already
includes fund expenses and accumulating dividends. These are valuation proxies,
not guaranteed exchange execution prices. No additional TER should be deducted.
"""

from pathlib import Path
from datetime import datetime, timezone, date
from bisect import bisect_right
from statistics import median
import csv
import hashlib
import io
import json
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parent
SS = "urn:schemas-microsoft-com:office:spreadsheet"
NS = {"s": SS}
SOURCES = {
    "fund_page": "https://www.ishares.com/uk/individual/en/products/253741/ishares-nasdaq-100-ucits-etf",
    "fund_download": "https://www.blackrock.com/varnish-api/uk-retail01-product-data/product-data/api/v1/get-fund-document?appSubType=ISHARES&appType=PRODUCT_PAGE&component=fundDownloadV2&locale=en_GB&portfolioId=253741&targetSite=ishares-uk&userType=individual",
    "ecb_zip": "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip",
    "ecb_api": "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?startPeriod=2010-01-01&endPeriod=2026-10-02&format=csvdata",
    "ecb_reference_description": "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html",
}


def read_nav():
    nav = {}
    workbook = ET.parse(ROOT / "cndx_fund_download.xls").getroot()
    for sheet in workbook.findall("s:Worksheet", NS):
        if sheet.get(f"{{{SS}}}Name") != "Historical NAVs":
            continue
        for row in sheet.findall(".//s:Row", NS):
            cells = [c.text for c in row.findall("s:Cell/s:Data", NS)]
            if len(cells) != 2:
                continue
            when = datetime.strptime(cells[0].replace("Sept", "Sep"), "%d/%b/%Y").date()
            value = float(cells[1].replace(",", ""))
            assert when.isoformat() not in nav, f"duplicate NAV: {when}"
            nav[when.isoformat()] = value
    assert len(nav) > 4200 and min(nav) == "2010-01-26"
    assert nav["2010-09-30"] == 105.42
    assert nav["2026-09-30"] == 1747.11
    return nav


def read_ecb():
    with zipfile.ZipFile(ROOT / "ecb_eurofxref_hist.zip") as archive:
        csv_text = archive.read("eurofxref-hist.csv").decode()
    rows = csv.DictReader(io.StringIO(csv_text))
    ecb = {r["Date"]: float(r["USD"]) for r in rows if r["USD"] != "N/A"}
    with (ROOT / "ecb_usd_api.csv").open() as source:
        api = {r["TIME_PERIOD"]: float(r["OBS_VALUE"])
               for r in csv.DictReader(source) if r["OBS_VALUE"]}
    overlaps = ecb.keys() & api.keys()
    assert len(overlaps) > 4200
    assert all(abs(ecb[d] - api[d]) < 1e-10 for d in overlaps)
    assert ecb["2010-09-30"] == 1.3648
    assert ecb["2026-09-30"] == 1.1355
    return ecb, len(overlaps)


def yahoo_closes(symbol):
    raw = json.loads((ROOT.parent / f"{symbol}.json").read_text())
    series = raw["chart"]["result"][0]
    return {
        datetime.fromtimestamp(ts, timezone.utc).date().isoformat(): value
        for ts, value in zip(series["timestamp"], series["indicators"]["quote"][0]["close"])
        if value is not None
    }


def main():
    nav = read_nav()
    ecb, overlaps = read_ecb()
    fx_dates = sorted(ecb)
    normalized = []
    for when, value in sorted(nav.items()):
        fx_date = fx_dates[bisect_right(fx_dates, when) - 1]
        gap = (date.fromisoformat(when) - date.fromisoformat(fx_date)).days
        assert 0 <= gap <= 4
        rate = ecb[fx_date]
        normalized.append({"date": when, "nav_usd": value,
                           "usd_per_eur": rate, "fx_date": fx_date,
                           "nav_eur": value / rate})
    with (ROOT / "cndx_nav_eur.csv").open("w") as target:
        writer = csv.DictWriter(target, fieldnames=list(normalized[0]))
        writer.writeheader()
        writer.writerows(normalized)
    with (ROOT / "cndx_nav_eur_2010-09-30_to_2026-09-30.csv").open("w") as target:
        writer = csv.DictWriter(target, fieldnames=list(normalized[0]))
        writer.writeheader()
        writer.writerows(r for r in normalized if "2010-09-30" <= r["date"] <= "2026-09-30")

    published_returns = {2016: 6.7, 2017: 32.3, 2018: -0.4, 2019: 38.8,
                         2020: 48.2, 2021: 27.0, 2022: -32.7, 2023: 54.4,
                         2024: 25.3, 2025: 20.5}
    calendar_validation = []
    for year, published in published_returns.items():
        previous = max(d for d in nav if d.startswith(str(year - 1)))
        year_end = max(d for d in nav if d.startswith(str(year)))
        calculated = 100 * (nav[year_end] / nav[previous] - 1)
        assert round(calculated, 1) == published, f"Issuer annual return mismatch: {year}"
        calendar_validation.append({
            "year": year, "previous_year_end_nav_date": previous,
            "year_end_nav_date": year_end, "nav_return_percent": calculated,
            "published_return_percent": published,
            "difference_percentage_points": calculated - published,
            "rounds_to_published": True,
        })
    by_date = {r["date"]: r for r in normalized}
    market = {symbol: yahoo_closes(symbol) for symbol in ("SXRV.DE", "CNDX.L")}
    comparisons = []
    for when, row in sorted(by_date.items()):
        comparison = dict(row)
        for symbol, denominator, prefix in [("SXRV.DE", "nav_eur", "sxrv"),
                                            ("CNDX.L", "nav_usd", "cndx")]:
            close = market[symbol].get(when)
            comparison[prefix + "_yahoo_close"] = close
            comparison[prefix + "_deviation"] = None if close is None else close / row[denominator] - 1
        comparisons.append(comparison)
    with (ROOT / "yahoo_vs_nav_audit.csv").open("w") as target:
        writer = csv.DictWriter(target, fieldnames=list(comparisons[0]))
        writer.writeheader()
        writer.writerows(comparisons)

    years = sorted({r["date"][:4] for r in comparisons})
    annual = {}
    for year in years:
        annual[year] = {}
        for name in ["sxrv", "cndx"]:
            values = [r[name + "_deviation"] for r in comparisons
                      if r["date"].startswith(year) and r[name + "_deviation"] is not None]
            if values:
                annual[year][name] = {"observations": len(values), "median_deviation": median(values),
                                     "max_abs_deviation": max(abs(v) for v in values),
                                     "count_abs_deviation_gt_10pct": sum(abs(v) > .10 for v in values)}

    errors = [r for r in comparisons if r["sxrv_deviation"] is not None and abs(r["sxrv_deviation"]) > .10]
    audit = {
        "as_of": "2026-10-03",
        "accepted_series": "cndx_nav_eur.csv",
        "rows": len(normalized), "start": normalized[0]["date"], "end": normalized[-1]["date"],
        "ecb_api_vs_zip_matching_observations": overlaps,
        "fx_prior_date_used_count": sum(r["date"] != r["fx_date"] for r in normalized),
        "sources": SOURCES,
        "source_sha256": {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest()
                          for f in ["cndx_fund_download.xls", "ecb_eurofxref_hist.zip", "ecb_usd_api.csv"]},
        "spot_checks": [r for r in comparisons if r["date"] in ["2010-09-30", "2011-09-30", "2016-09-30", "2026-09-30"]],
        "sxrv_discrepancy_gt_10pct": {"count": len(errors), "first": errors[0]["date"] if errors else None,
                                    "last": errors[-1]["date"] if errors else None},
        "annual_yahoo_audit": annual,
        "calendar_return_validation": calendar_validation,
        "limitations": [
            "NAV valuation rather than exchange execution; London/Xetra close before final US-close NAV, so small daily differences are expected.",
            "ECB rates are reference observations, not broker executable FX; same-day US NAV and ECB FX are not synchronous.",
            "NAV already reflects fund expenses, fund-level withholding, accumulation, and other tracking effects; do not subtract TER or fund dividend withholding again.",
            "The legacy direct eurofxref-hist.csv URL returned stale data with obvious outliers; it was rejected. ZIP and SDMX API independently agree.",
            "A 10% market-price/NAV threshold is only an anomaly flag. On 2025-04-09 both European closes were about 10% below final US-close NAV, consistent with non-synchronous valuation during a volatile day. This is not classified as a data error.",
        ],
    }
    (ROOT / "benchmark_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps({k: audit[k] for k in ["rows", "start", "end", "ecb_api_vs_zip_matching_observations", "fx_prior_date_used_count", "sxrv_discrepancy_gt_10pct", "spot_checks"]}, indent=2))


if __name__ == "__main__":
    main()
