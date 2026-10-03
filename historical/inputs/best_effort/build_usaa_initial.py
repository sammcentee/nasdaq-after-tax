"""Recover the complete 2010-06-30 USAA Nasdaq-100 Fund equity portfolio.

This is a contemporaneously published index-fund proxy, not official Nasdaq
index weights. The source held all 100 equities plus index futures covering
its cash. Normalize its reported equity sleeve without removing any names.
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
URL = "https://www.sec.gov/Archives/edgar/data/908695/000090869510000170/ncsrsnas063010.htm"


def main():
    source = P / "usaa_20100630_semiannual.html"
    text = BeautifulSoup(source.read_text(), "html.parser").get_text()
    block = text[text.index("PORTFOLIO OF INVESTMENTS\n"):]
    block = block[:block.index("Total Common Stocks")]
    parsed = re.findall(r"^\s*([\d,]+)\s{2,}(.+?)\s{2,}(?:\$\s*)?([\d,]+)\s*$", block, re.M)
    assert len(parsed) == 100
    assert sum(int(v.replace(",", "")) for _, _, v in parsed) == 154982
    names = json.loads((H / "membership/qqq_name_ticker_mapping_initial.json").read_text())
    base = pd.read_csv(H / "inputs/target_weights.csv").fillna("")
    # The historical annual source is used only as an issuer-name crosswalk.
    # No 2010-09-30 price or weight is used in this June snapshot.
    base = base[base.effective_date.eq("2010-09-30")].set_index("ticker")
    def normalize(name):
        return re.sub("[^a-z]", "", re.sub(r"\([^)]*\)", "", name).lower())
    rows, anchors = [], []
    for shares, name, value in parsed:
        matched = max(names, key=lambda key: SequenceMatcher(None, normalize(name), normalize(key)).ratio())
        score = SequenceMatcher(None, normalize(name), normalize(matched)).ratio()
        assert score >= .75, (name, matched, score)
        ticker = names[matched]
        assert ticker in base.index, (ticker, name)
        row = base.loc[ticker].to_dict()
        value = int(value.replace(",", "")) * 1000
        shares = int(shares.replace(",", ""))
        row.update(
            effective_date="2010-06-30", available_date="2010-08-30", ticker=ticker,
            name=re.sub(r"\([^)]*\)", "", name).rstrip("*"),
            weight=value / 154982000, source_weight=value / 154982000,
            source="USAA_Nasdaq100_SEC_semiannual",
            source_url=URL, weight_reference_date="2010-06-30",
            weight_quality="index_fund_equity_proxy_reported_values_rounded_to_1000USD",
            availability_quality="verified_SEC_filing_next_US_session",
            published_date="2010-08-27", source_total_equity_weight=.985,
        )
        rows.append(row)
        anchors.append(dict(date="2010-06-30", ticker=ticker, name=name,
                            original_security_id=row["security_id"], shares=shares,
                            reported_value_usd=value,
                            approximate_raw_close_usd=value / shares,
                            price_rounding_bound_usd=.5 * 1000 / shares,
                            equity_weight=value / 154982000,
                            source_url=URL, filed_date="2010-08-27"))
    result = pd.DataFrame(rows)
    assert result.ticker.nunique() == 100
    assert abs(result.weight.sum() - 1) < 1e-12
    result.to_csv(P / "usaa_20100630_source_weights.csv", index=False)
    pd.DataFrame(anchors).to_csv(P / "usaa_20100630_share_value_anchors.csv", index=False)
    filings = pd.DataFrame(json.loads((P / "CIK0000908695-submissions-002.json").read_text()))
    filing = filings[filings.accessionNumber.eq("0000908695-10-000170")].iloc[0].to_dict()
    manifest = dict(
        source_url=URL, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        report_date="2010-06-30", filed_date=filing["filingDate"],
        accepted=filing["acceptanceDateTime"], available_date="2010-08-30",
        holding_count=100, reported_equity_value_usd=154982000,
        equity_value_sum_matches_report=True, all_100_names_preserved=True,
        normalization="All reported ordinary equities normalized over USD154982000; no price-survivor filtering",
        limitations=[
            "USAA index fund's actual portfolio is a close contemporaneous proxy, not certified exact Nasdaq index weights.",
            "Reported stock values are rounded to USD1000; implied raw closes are rounding-bounded anchors, not precise executions.",
            "Fund report shows common stocks at98.5% of NAV plus Nasdaq futures at1.6% exposure; only equity-sleeve relative weights are used.",
            "June snapshot is still92days old at first contribution, but replaces the former365day-old September2009 snapshot.",
            "No prices, weights or returns from the later September2010 annual report enter these values; it supplies historical issuer labels only.",
        ],
    )
    (P / "usaa_20100630_source_audit.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
