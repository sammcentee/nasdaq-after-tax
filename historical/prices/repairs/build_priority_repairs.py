"""Auditable partial corporate-action repairs; never certifies the full universe.

Run from the repository root with .venv/bin/python. Original files are read-only.
Prices use contemporaneous share units. Stock splits and distributions must be
applied to quantities using the ledger; do NOT add them again as cash dividends.
Tax basis is deliberately not inferred from US tax treatment.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
import xarray as xr

P = Path(__file__).resolve().parent
SOURCE = P.parent
IDS = {
    "EBAY": "tts-832177", "PYPL": "tts-91263224",
    "GOOGL": "tts-71625495", "GOOG": "tts-1947579",
    "CELG": "tts-832022", "BMY": "tts-818515",
    "ALXN": "tts-831866", "AZN": "tts-203249662",
    "ATVI": "tts-827879", "BMYRT": "right:BMYRT:2019",
}
SOURCES = {
    "ebay_terms": "https://www.ebayinc.com/stories/news/ebay-inc-board-approves-completion-of-ebay-and-paypal-separation/",
    "ebay_raw_extrema": "https://ebay.q4cdn.com/610426115/files/doc_financials/financials/2015/2015_ebay_annual_report.pdf",
    "google_2014": "https://www.sec.gov/Archives/edgar/data/1288776/000112760215001601/xslF345X03/form4.xml",
    "google_2014_exdate": "https://ir.nasdaq.com/node/81631",
    "google_2015": "https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2015-52",
    "celgene_terms": "https://news.bms.com/news/details/2019/Bristol-Myers-Squibb-Completes-Acquisition-of-Celgene-Creating-a-Leading-Biopharma-Company/default.aspx",
    "celgene_split_2014": "https://www.sec.gov/Archives/edgar/data/816284/000119312514241821/d744699dex991.htm",
    "cvr_expiry": "https://www.bms.com/investors/shareholder-services/shareholder-faq.html",
    "alexion_terms": "https://www.astrazeneca.com/media-centre/press-releases/2020/astrazeneca-to-acquire-alexion.html",
    "alexion_close": "https://www.astrazeneca.com/media-centre/press-releases/2021/acquisition-of-alexion-completed.html",
    "alexion_split_2011": "https://www.sec.gov/Archives/edgar/data/899866/000119312511137689/dex991.htm",
    "azn_conversion": "https://www.sec.gov/Archives/edgar/data/901832/000165495426000464/a4875p.htm",
    "azn_conversion_completed": "https://www.astrazeneca.com/investor-relations/faqs.html",
    "atvi_cash": "https://www.sec.gov/Archives/edgar/data/789019/000119312523255762/d537928d8k.htm",
}


def main():
    ndx = xr.open_dataarray(SOURCE / "quantiacs_ndx_all.nc").sortby("time")
    general = xr.open_dataarray(P / "quantiacs_general_priority.nc").sortby("time")
    (P / "primary_sources.json").write_text(json.dumps(SOURCES, indent=2))
    quotes, raw_source = {}, {}
    for symbol, asset in IDS.items():
        if symbol == "BMYRT":
            continue
        data = general if symbol == "BMY" else ndx
        q = data.sel(asset=asset, field=["close", "divs", "split_cumprod"]).to_pandas().T
        q = q.dropna(subset=["close"]).copy()
        raw_source[symbol] = q.copy()
        q["raw_close_usd"] = q["close"] / q["split_cumprod"]
        q["cash_dividend_usd_per_share"] = q["divs"] / q["split_cumprod"]
        q["quality"] = "split_factor_normalized; other_source_errors_not_excluded"
        q["source_asset_id"] = asset
        q["symbol"] = symbol
        quotes[symbol] = q

    # Calibrate to a primary issuer table, not to the problematic divs field.
    # Issuer's 2015 annual report PDF page 41 lists ACTUALLY REPORTED closes,
    # and expressly says historical prices were subsequently spin-adjusted.
    eb = quotes["EBAY"]
    anchor = eb.loc["2015-07-01":"2015-07-17", "raw_close_usd"].max()
    factor = 66.29 / anchor
    before = eb.index < pd.Timestamp("2015-07-20")
    eb.loc[before, "raw_close_usd"] *= factor
    eb.loc[before, "quality"] = "inferred_constant_spin_unadjustment_calibrated_to_issuer_extrema"
    eb.loc["2015-07-20", "cash_dividend_usd_per_share"] = 0.0
    checks = []
    for lo, hi, high, low in [
        ("2014-01-01", "2014-03-31", 59.30, 51.78),
        ("2014-04-01", "2014-06-30", 56.04, 48.25),
        ("2014-07-01", "2014-09-30", 56.63, 50.18),
        ("2014-10-01", "2014-12-31", 57.53, 47.88),
        ("2015-01-01", "2015-03-31", 60.81, 53.00),
        ("2015-04-01", "2015-06-30", 63.23, 55.79),
        ("2015-07-01", "2015-07-17", 66.29, 60.43),
    ]:
        q = eb.loc[lo:hi, "raw_close_usd"]
        for label, actual, expected in [("high", q.max(), high), ("low", q.min(), low)]:
            checks.append(dict(period_start=lo, period_end=hi, statistic=label,
                               reconstructed=float(actual), issuer=float(expected),
                               error_usd=float(actual-expected)))
    check_df = pd.DataFrame(checks)
    check_df.to_csv(P / "ebay_unadjustment_issuer_checks.csv", index=False)
    assert check_df.error_usd.abs().max() < 0.02

    # Class A prices include a hidden 2014 2-for-1 adjustment although the
    # holder received a different security. Restore A and explicitly retain C.
    ga = quotes["GOOGL"]
    ga.loc[ga.index < "2014-04-03", "raw_close_usd"] *= 2
    ga.loc[ga.index < "2014-04-03", "quality"] = "class_A_hidden_2014_factor_2_reversed"
    ga.loc["2014-04-03", "cash_dividend_usd_per_share"] = 0.0
    # GOOG was a distinct when-issued security only from March 2014; discard
    # pre-regular-trading rows from this executable entitlement price bundle.
    gc = quotes["GOOG"].loc["2014-04-03":].copy()
    gc.loc[gc.index < "2015-04-27", "raw_close_usd"] *= 1.0027455
    gc.loc[gc.index < "2015-04-27", "quality"] = "inferred_2015_stock_distribution_adjustment_reversed"
    quotes["GOOG"] = gc
    quotes["PYPL"] = quotes["PYPL"].loc["2015-07-20":].copy()

    # Delisted CELG and ALXN have split-adjusted prices but all-one source
    # split factors, so known plain splits must also be restored explicitly.
    missing_splits = [("CELG", "2014-06-26", "celgene_split_2014"),
                      ("ALXN", "2011-05-23", "alexion_split_2011")]
    for symbol, date, _ in missing_splits:
        q = quotes[symbol]
        assert np.isclose(q.split_cumprod.dropna(), 1).all()
        q.loc[q.index < date, "raw_close_usd"] *= 2
        q.loc[q.index < date, "cash_dividend_usd_per_share"] *= 2
        q.loc[q.index < date, "quality"] = "issuer_verified_2_for_1_split_missing_from_source_factor_restored"

    # AZN changes quoted units six sessions before the legal ADR conversion.
    # Divide just those observations by 2, and apply quantity /2 on Feb 2.
    # This is a flagged inference, not an independently verified daily quote.
    # Earlier AZN 2015 adjustment problems are outside the retained-ALXN path.
    az = quotes["AZN"].loc["2021-07-21":].copy()
    az.loc["2026-01-23":"2026-01-30", "raw_close_usd"] /= 2
    az.loc["2026-01-23":"2026-01-30", "quality"] = "inferred_early_ADR_to_ordinary_unit_change_divided_by_2"
    quotes["AZN"] = az

    events = []
    def event(event_id, date, symbol, action, destination="", ratio=0,
              cash=0, timing="before_close", source_keys=(), notes="", status="terms_verified", **extra):
        events.append(dict(event_id=event_id, economic_date=date, old_symbol=symbol,
                           old_asset_id=IDS[symbol], action=action,
                           new_symbol=destination, new_asset_id=IDS.get(destination, ""),
                           new_shares_per_old_share=ratio, cash_usd_per_old_share=cash,
                           timing=timing, status=status, irish_tax_basis_status="unresolved",
                           sources=" | ".join(SOURCES[k] for k in source_keys), notes=notes, **extra))

    event("GOOGLE_CLASS_C_2014", "2014-04-03", "GOOGL", "retain_parent_add_child", "GOOG", 1,
          source_keys=("google_2014", "google_2014_exdate"),
          notes="Payment 2014-04-02 after close; retain every Class A share and receive one Class C share; fake cash dividend removed.")
    event("GOOGLE_CLASS_C_ADJUSTMENT_2015", "2015-04-27", "GOOG", "stock_distribution_same_class", "GOOG", 0.0027455,
          source_keys=("google_2015",), status="fractional_share_and_payment_timing_approximation",
          notes="Record 2015-04-02; ex 2015-04-27; paid 2015-05-04. Ledger accrues fractional entitlement on ex date. Issuer paid cash in lieu of fractions; broker account aggregation/CIL cash is unresolved.")
    event("EBAY_PAYPAL_2015", "2015-07-20", "EBAY", "retain_parent_add_child", "PYPL", 1,
          source_keys=("ebay_terms", "ebay_raw_extrema"), status="terms_verified_price_unadjustment_inferred",
          notes="Distributed 2015-07-17 after close, first regular trading 2015-07-20. Retain both securities. Hidden historical parent-price factor reversed; source divs 38.39 removed.")
    event("CELGENE_BMY_2019", "2019-11-20", "CELG", "replace_parent_stock_cash_and_right", "BMY", 1, 50,
          timing="after_close", source_keys=("celgene_terms",), status="partial_missing_CVR_marks_and_basis",
          notes="Also receive one BMYRT CVR per CELG share; do not omit or sell it. New securities regular trading 2019-11-21. Interim rights marks and tax basis unresolved.",
          right_asset_id=IDS["BMYRT"], rights_per_old_share=1)
    event("BMYRT_CONTRACTUAL_EXPIRY_2021", "2021-01-01", "BMYRT", "contractual_right_expires", cash=0,
          source_keys=("cvr_expiry",), status="contractual_zero_verified_other_legal_claims_unresolved",
          notes="Contract terminated automatically without payment. This does not settle any separate litigation rights or provide interim valuation/tax-basis history.")
    event("ALEXION_AZN_2021", "2021-07-21", "ALXN", "replace_parent_stock_cash", "AZN", 2.1243, 60,
          source_keys=("alexion_terms", "alexion_close"), status="terms_verified_fractional_settlement_and_tax_unresolved",
          notes="Successor units are ADSs representing half an ordinary share; new ADS trading 2021-07-22. Fractional entitlements kept for analytical valuation; actual cash-in-lieu and settlement lag unresolved.")
    event("ATVI_CASH_2023", "2023-10-13", "ATVI", "replace_parent_cash", cash=95,
          source_keys=("atvi_cash",), notes="Mandatory cash entitlement; final quoted close94.42 is not redemption95. Cash receipt/reinvestment settlement timing must be configured.")
    event("AZN_ADR_ORDINARY_2026", "2026-02-02", "AZN", "replace_units_same_ticker", "AZN", 0.5,
          source_keys=("azn_conversion", "azn_conversion_completed"), status="terms_verified_six_source_quotes_inferred",
          notes="Two ADRs become one ordinary share. Source doubles six sessions early; Jan23-Jan30 quotes divided by2. No independent price crosscheck for those sessions.")
    for symbol, date, source_key in missing_splits:
        event(f"{symbol}_VERIFIED_MISSING_SPLIT_{date}", date, symbol,
              "ordinary_split", symbol, 2, source_keys=(source_key,),
              notes="Issuer verifies 2-for-1 split. Source historical prices were adjusted but split_cumprod stayed1; pre-event prices restored by2.")

    # Regular split factors cover contemporaneous units for these securities.
    for symbol, q in quotes.items():
        sf = q.split_cumprod
        changes = (sf / sf.shift()).dropna()
        for date, ratio in changes[~np.isclose(changes, 1)].items():
            event(f"{symbol}_SOURCE_SPLIT_{date.date()}", str(date.date()), symbol,
                  "ordinary_split", symbol, float(ratio), status="source_factor_not_independently_verified",
                  notes="Derived from source split_cumprod; multiply quantity by ratio. Quote and cash dividend already normalized to current-day units.")
    pd.DataFrame(events).sort_values(["economic_date", "event_id"]).to_csv(P / "priority_corporate_actions.csv", index=False)

    rows = []
    for symbol, q in quotes.items():
        x = q.reset_index(names="date")
        x["date"] = x.date.dt.strftime("%Y-%m-%d")
        rows.append(x)
    out = pd.concat(rows, ignore_index=True)
    out.to_csv(P / "priority_daily_quotes.csv.gz", index=False, compression="gzip")
    for symbol, q in quotes.items():
        assert (q.raw_close_usd > 0).all()
        assert not q.index.duplicated().any()

    # Economic boundary checks retain the child stock, with no reinvestment.
    boundary = []
    for parent, date, prior, child, ratio, cash in [
        ("EBAY", "2015-07-20", "2015-07-17", "PYPL", 1, 0),
        ("GOOGL", "2014-04-03", "2014-04-02", "GOOG", 1, 0),
        ("ALXN", "2021-07-21", "2021-07-20", "AZN", 2.1243, 60),
        ("ATVI", "2023-10-13", "2023-10-12", None, 0, 95),
    ]:
        parent_value = float(quotes[parent].loc[date, "raw_close_usd"]) if parent in ["EBAY", "GOOGL"] else 0
        child_value = ratio * float(quotes[child].loc[date, "raw_close_usd"]) if child else 0
        prior_value = float(quotes[parent].loc[prior, "raw_close_usd"])
        original = raw_source[parent]
        naive = float((original.loc[date, "close"] + original.loc[date, "divs"]) / original.loc[prior, "close"] - 1) if date in original.index else None
        boundary.append(dict(parent=parent, date=date, prior_raw_value=prior_value,
                             parent_post_value=parent_value, retained_child_value=child_value,
                             cash_entitlement=cash,
                             repaired_gross_event_return=(parent_value+child_value+cash)/prior_value-1,
                             original_naive_return=naive))
    pd.DataFrame(boundary).to_csv(P / "economic_boundary_checks.csv", index=False)
    assert 0.03 < boundary[0]["repaired_gross_event_return"] < 0.06
    assert abs(boundary[1]["repaired_gross_event_return"]) < 0.03
    az_prior = float(az.loc["2026-01-30", "raw_close_usd"])
    az_after = float(az.loc["2026-02-02", "raw_close_usd"]) * 0.5
    assert abs(az_after/az_prior-1) < 0.1

    # Flag counts are not a count of actual corporate actions: they overlap,
    # and some are legitimate large market moves or genuine cash dividends.
    flag_rows = []
    handled = {("distribution", IDS["EBAY"], "2015-07-20"): "partial_repair_parent_child_prices; tax_unresolved",
               ("distribution", IDS["GOOGL"], "2014-04-03"): "partial_repair_parent_child_prices; tax_unresolved",
               ("extreme_return", IDS["EBAY"], "2015-07-20"): "partial_repair_parent_child_prices; tax_unresolved",
               ("extreme_return", IDS["GOOGL"], "2014-04-03"): "partial_repair_parent_child_prices; tax_unresolved",
               ("extreme_return", IDS["AZN"], "2026-01-23"): "inferred_unit_repair; independent_quote_unresolved",
               ("terminal_gap", IDS["ATVI"], "2023-10-12"): "cash_event_verified; Irish_realization_timing_unresolved",
               ("terminal_gap", IDS["CELG"], "2019-11-20"): "successor_downloaded; rights_marks_tax_unresolved",
               ("terminal_gap", IDS["ALXN"], "2021-07-20"): "successor_retained; quote_inference_tax_unresolved"}
    for kind, filename, col in [
        ("distribution", "required_large_distribution_review.csv", "date"),
        ("extreme_return", "required_extreme_daily_return_review.csv", "date"),
        ("terminal_gap", "required_terminal_price_gaps_review.csv", "last_price")]:
        flags = pd.read_csv(SOURCE / filename)
        for _, row in flags.iterrows():
            key = (kind, row.id, row[col])
            flag_rows.append(dict(flag_type=kind, asset_id=row.id, symbol=row.symbol,
                                  date=row[col], repair_status=handled.get(key, "unreviewed")))
    flags = pd.DataFrame(flag_rows)
    flags.to_csv(P / "remaining_review_queue.csv", index=False)

    summary = {
        "status": "partial_repair_bundle_not_validated_full_backtest",
        "original_data_mutated": False,
        "priority_chains_with_verified_terms": 5,
        "additional_linked_events_recorded": 5,
        "quote_series": len(quotes), "quote_observations": len(out),
        "new_non_NDX_successor_downloaded": "BMY tts-818515",
        "ebay_hidden_price_multiplier": float(factor),
        "ebay_independent_issuer_extrema_checks": len(checks),
        "ebay_max_extrema_error_usd": float(check_df.error_usd.abs().max()),
        "azn_inferred_quote_sessions": 6,
        "flag_counts": {kind: dict(total=len(grp), addressed_at_least_partially=int((grp.repair_status != "unreviewed").sum()), unreviewed=int((grp.repair_status == "unreviewed").sum())) for kind, grp in flags.groupby("flag_type")},
        "full_chains_validated_for_Irish_after_tax_TLH": 0,
        "unresolved": [
            "Other required securities/actions remain unreviewed; flag lists overlap and are not exhaustive.",
            "Irish treatment and lot-basis allocation for all stock/spin/mixed mergers is not supplied by this bundle.",
            "BMYRT interim daily marks unavailable; contractual expiry is known but separate litigation claims need review.",
            "GOOG 2015 cash in lieu of fractional stock and distribution settlement not reconstructed.",
            "AZN six daily quotes are inferred unit corrections and were not verified with an independent price source.",
            "Raw EBAY historical factor is inferred constant and independently checked against fourteen issuer price extrema.",
            "Fractional-share cash in lieu and actual broker settlement lags unresolved for merger successors.",
            "Source dividend dates are ex dates, not confirmed payment dates; withholding and ADR fees not classified.",
            "Regular split factors remain provider-derived, and other hidden adjustment errors cannot be excluded.",
        ],
        "data_requests": {
            "general_assets": "https://data-api.quantiacs.io/assets?min_date=2010-09-01&max_date=2026-10-02&type=",
            "general_data": {"url": "https://data-api.quantiacs.io/data", "method": "POST", "json": {"assets": [IDS[k] for k in IDS if k != "BMYRT"], "min_date": "2010-09-01", "max_date": "2026-10-02", "type": ""}},
            "general_data_note": "AZN requested but absent from general response; existing NDX data supplies AZN. General endpoint shares adjusted-price anomalies with NDX endpoint.",
            "yahoo_fallback": "Four unauthenticated chart requests returned HTTP429; no credentials/account requests used.",
        },
        "input_sha256": {str(f.relative_to(P.parent)): hashlib.sha256(f.read_bytes()).hexdigest() for f in [SOURCE / "quantiacs_ndx_all.nc", P / "quantiacs_general_priority.nc", P / "quantiacs_general_assets.json"]},
    }
    (P / "repair_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k not in ["data_requests", "input_sha256", "unresolved"]}, indent=2))


if __name__ == "__main__":
    main()
