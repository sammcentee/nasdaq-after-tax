"""Parse 13 SEC-published Nasdaq-100 index-fund portfolios, 2010-2013.

Issuer names are joined using historical name dictionaries. Later records
supply identity labels only, never historical values, holdings or weights.
"""
from pathlib import Path
from difflib import SequenceMatcher
import hashlib
import json
import re

from bs4 import BeautifulSoup
import pandas as pd

P = Path(__file__).resolve().parent
H = P.parents[1]


def norm(text):
    return re.sub("[^a-z]", "", re.sub(r"\([^)]*\)", "", text).lower().replace("class", "").replace("series", ""))


def main():
    filings = pd.read_csv(P / "usaa_quarterly_filings.csv").fillna("")
    canonical = pd.read_csv(H / "inputs/target_weights.csv").fillna("")
    names = json.loads((H / "membership/qqq_name_ticker_mapping_initial.json").read_text())
    names.update(canonical[canonical.effective_date.le("2013-09-30")].set_index("name").ticker.to_dict())
    rows, anchors, audits, joins = [], [], [], []
    for filing in filings.sort_values("reportDate").to_dict("records"):
        date = filing["reportDate"]
        source = P / ("usaa_" + date.replace("-", "") + "_" + filing["form"].replace("-", "") + ".html")
        text = BeautifulSoup(source.read_text(), "html.parser").get_text()
        start = text.index("PORTFOLIO OF INVESTMENTS")
        end = text.index("Total Common Stocks", start)
        block = text[start:end]
        parsed = re.findall(r"^\s*([\d,]+)\s{2,}(.+?)\s{2,}(?:\$\s*)?([\d,]+)\s*$", block, re.M)
        assert len(parsed) in (100, 101), (date, len(parsed))
        total = sum(int(value.replace(",", "")) for _, _, value in parsed)
        reported_total = int(re.search(r"Total Common Stocks.*?([\d,]+)\s*\n", text[end:]).group(1).replace(",", ""))
        assert total == reported_total, (date, total, reported_total)
        pct = float(re.search(r"COMMON STOCKS\s*\(([\d.]+)%\)", block).group(1)) / 100
        url = "https://www.sec.gov/Archives/edgar/data/908695/" + filing["accessionNumber"].replace("-", "") + "/" + filing["primaryDocument"]
        for shares, name, value in parsed:
            matched = max(names, key=lambda key: SequenceMatcher(None, norm(name), norm(key)).ratio())
            score = SequenceMatcher(None, norm(name), norm(matched)).ratio()
            if "Orchard Supply" in name:
                ticker = "OSH_OLD"
                row = {column: "" for column in canonical.columns}
                row.update(security_id="unresolved:ORCHARD_SUPPLY_2011", price_id="", identity_quality="unresolved_identity",
                           identity_notes="Old Sears spin-off; no executable price identity recovered. Not modern reused OSH issuer.")
            else:
                assert score >= .9 or "Sirius Satellite" in name or "Patterson Companies" in name, (name, matched, score)
                ticker = names[matched]
                candidates = canonical[canonical.ticker.eq(ticker)].copy()
                assert not candidates.empty, ticker
                candidates["distance"] = (pd.to_datetime(candidates.effective_date) - pd.Timestamp(date)).abs()
                row = candidates.sort_values("distance").iloc[0].drop("distance").to_dict()
            value = int(value.replace(",", "")) * 1000
            shares = int(shares.replace(",", ""))
            row.update(effective_date=date, available_date=filing["filingDate"], ticker=ticker,
                       name=re.sub(r"\([^)]*\)", "", name).rstrip("* "),
                       weight=value / (total * 1000), source_weight=value / (total * 1000),
                       source="USAA_Nasdaq100_SEC_quarterly", source_url=url,
                       weight_reference_date=date,
                       weight_quality="index_fund_equity_proxy_reported_values_rounded_to_1000USD",
                       availability_quality="verified_SEC_filing_date_engine_requires_strictly_later_trade_date",
                       published_date=filing["filingDate"], source_total_equity_weight=pct)
            rows.append(row)
            anchors.append(dict(date=date, ticker=ticker, name=name, original_security_id=row["security_id"], shares=shares,
                                reported_value_usd=value, approximate_raw_close_usd=value / shares,
                                price_rounding_bound_usd=500 / shares, equity_weight=value / (total * 1000),
                                source_url=url, filed_date=filing["filingDate"]))
            joins.append(dict(date=date, source_name=name, matched_historical_name=matched,
                              historical_ticker=ticker, string_similarity=score,
                              exception="verified_old_Orchard_identity_no_prices" if ticker == "OSH_OLD" else ""))
        audits.append(dict(report_date=date, filed_date=filing["filingDate"], accepted=filing["acceptanceDateTime"],
                           row_count=len(parsed), reported_equity_value_usd=total * 1000,
                           reported_equity_nav_fraction=pct, source_url=url,
                           sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
    result = pd.DataFrame(rows)
    sums = result.groupby(["effective_date", "available_date"]).weight.sum()
    assert ((sums - 1).abs() < 1e-12).all()
    result.to_csv(P / "usaa_quarterly_source_weights.csv", index=False)
    pd.DataFrame(anchors).to_csv(P / "usaa_quarterly_share_value_anchors.csv", index=False)
    pd.DataFrame(joins).to_csv(P / "usaa_quarterly_name_join_audit.csv", index=False)
    (P / "usaa_quarterly_source_audit.json").write_text(json.dumps({
        "snapshots": audits,
        "causality": "Each report is used strictly after its actual SEC filing date; no future portfolio data or interpolation.",
        "normalization": "Every reported common-stock row retained and normalized over reported stock value; no survivor exclusions.",
        "limitations": [
            "These are an index fund's contemporaneous equity holdings, not certified exact Nasdaq index weights.",
            "All USD values were reported rounded to USD1000. Share/value anchors are approximate, with rounding bounds retained.",
            "Fund cash and derivatives are excluded from relative stock weights; futures generally supply the omitted cash exposure.",
            "2011-12-31 includes a tiny Orchard Supply common-stock spin-off; unpriced exposure remains explicit cash.",
            "2013-06-30 separately lists News Corp A and Twenty-First Century Fox A at identical implied prices; they map to the same continuing old class and engine weights aggregate them.",
            "Future issuer records can establish historical identity but never supply historical holdings, prices, or values.",
        ],
    }, indent=2) + "\n")
    print(f"Parsed {len(audits)} complete reports and {len(rows)} rows; all values sum to reported equity totals.")


if __name__ == "__main__":
    main()
