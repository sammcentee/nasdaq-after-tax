"""Prepare the corrected study's explicitly provisional stock inputs.

Public downloads and manual event repairs remain separate from the accepted
ETF benchmark. This runner does not replace missing held assets with survivors.
Missing purchase targets reserve cash; unresolved held valuations still fail.
"""
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent

CANONICAL_IDS = {
    "tts-832260": "tts-377137730", "tts-63081317": "tts-377137730",  # Fiserv
    "tts-177780551": "tts-282720976",  # Symantec / NortonLifeLock / Gen
    "tts-43902240": "tts-222568848",  # Facebook / Meta
}


def canonical(value):
    return CANONICAL_IDS.get(value, value)


def add_provisional_marks(p):
    """Seed unquoted successors with documented values, never executable history.

    Marks start on their original observation/entitlement date. Preparation
    carries their USD values with current FX, without trading eligibility. Actual eventual
    corporate consideration still governs the cash received. This is a disclosed
    limitation of the provisional reconstruction, not a claim of daily prices.
    """
    records, evidence = [], []
    def add(day, security, value, source, quality):
        if ((p.security_id == security) & (p.date == pd.Timestamp(day))).any():
            return
        records.append(dict(date=pd.Timestamp(day), security_id=security,
                            price_usd=value, dividend_usd=0., source=source,
                            quality=quality, tradable=False))
        evidence.append(dict(date=day, security_id=security, price_usd=value,
                             source=source, quality=quality))
    def quote(security, day):
        q = p[(p.security_id == security) & (p.date <= day)].sort_values("date")
        return float(q.iloc[-1].price_usd) if len(q) else np.nan
    adp = quote("tts-15888595", "2014-10-01")
    add("2014-10-01", "yahoo:CDK", 3*adp*.1264/.8736,
        "https://s205.q4cdn.com/887941133/files/doc_downloads/faq/IRS_Form_8937.pdf",
        "first_close_inferred_from_issuer_rounded_FMV_allocation; daily_prices_and_dividends_missing")
    add("2017-02-01", "yahoo:LOGM", 108.10,
        "https://d18rn0p25nwr6d.cloudfront.net/CIK-0001420302/48509cd3-d1c6-4ad2-a0f5-f518990b4d6b.pdf",
        "documented_Jan31_close_carried_to_distribution; daily_prices_and_dividends_missing")
    add("2019-02-08", "yahoo:CVET", 41.54,
        "https://s206.q4cdn.com/399858780/files/doc_downloads/IRS-Form-8937.pdf",
        "issuer_documented_distribution_day_VWAP_proxy; daily_prices_missing")
    add("2012-10-02", "yahoo:KRFT", 45.42,
        "https://www.mondelezinternational.com/assets/PDFs/2--report-of-organizational-actions-affecting-basis-of-securities-form-8937.pdf",
        "issuer_documented_first_close; daily_prices_and_dividends_missing")
    # Sparse Amec/Wood history: infer an initial retained-share mark from the
    # last actually observed predecessor quote and stated exchange terms.
    amfw = max(.01, (quote("tts-2880955", "2014-12-03") - 16.)/.8998)
    add("2015-01-20", "yahoo:AMFW", amfw,
        "quantiacs_FWLT_last_quote_and_primary_cash_share_exchange_terms",
        "inferred_stale_predecessor_value; no_AMFW_daily_prices_or_dividends")
    add("2017-10-09", "yahoo:WG.L", amfw/.75,
        "primary_AMFW_to_Wood_0.75_exchange_terms",
        "retained_value_carry_proxy; no_Wood_daily_prices_or_dividends")
    add("2020-09-15", "yahoo:QRTEP", 100.,
        "Qurate_8_percent_preferred_100_dollar_liquidation_preference",
        "par_value_proxy_NOT_observed_market_price; no_preferred_daily_quotes")
    add("2025-02-24", "yahoo:QVCGA", quote("tts-137012693", "2025-02-21"),
        "last_quoted_QRTEA_close_before_same_issuer_ticker_change",
        "stale_predecessor_mark; no_executable_quotes_until_documented_cancellation")
    add("2024-11-13", "yahoo:SUNN.SW", 45.20,
        "https://www.libertyglobal.com/investors/share-information/share-cost-basis/",
        "issuer_documented_Nov13_SNRE_ADS_close; Swiss_ordinary_quotes_from_Nov15; conversion_costs_not_reconstructed")
    add("2021-11-02", "yahoo:VMW", 130.73,
        "https://investors.delltechnologies.com/static-files/4afe078b-0cdc-4419-82c2-36d9d68f9229",
        "issuer_documented_Nov2_high_low_mean_FMV_NOT_close; Dell_spin_recipients_excluded_from_prior_27.40_dividend")
    add("2016-12-09", "yahoo:LGF-B", 25.70,
        "https://www.sec.gov/Archives/edgar/data/929351/000092935117000006/lgf2016123110-q.htm",
        "issuer_estimated_Dec8_FMV_NOT_Dec9_close; daily_history_and_dividends_missing")
    # Zero-volume vendor indication predates the Swiss listing. Carry the known
    # US ADS close for Nov14; use actual Swiss quotes from Nov15 onwards.
    p = p[~(p.security_id.eq("yahoo:SUNN.SW") & p.date.eq(pd.Timestamp("2024-11-14")))].copy()
    if records:
        p = pd.concat([p, pd.DataFrame(records)], ignore_index=True)
    p["tradable"] = p.get("tradable", True).fillna(True).astype(bool)
    return p, evidence


def prepare(audit_dir=None):
    inputs = ROOT / "inputs/best_effort"
    source = ROOT / "prices/best_effort"
    out = Path(audit_dir) if audit_dir is not None else ROOT / "results/latest/input_audit"
    out.mkdir(parents=True, exist_ok=True)
    p = pd.read_csv(source / "prices_usd.csv.gz", parse_dates=["date"])
    p = p.rename(columns={"close_usd": "price_usd", "dividend_usd": "dividend_usd"})
    p, provisional_marks = add_provisional_marks(p)
    w = pd.read_csv(inputs / "best_effort_weights.csv")
    m = pd.read_csv(inputs / "metadata.csv")
    membership = pd.read_csv(inputs / "membership.csv")
    actions = pd.read_csv(source / "actions.csv", parse_dates=["date"])
    splits = pd.read_csv(source / "split_events.csv", parse_dates=["date"])
    # Legal same-share ticker transitions use one full, unit-checked history.
    # This also makes the same-class four-week restrictions span old tickers.
    p = p[~p.security_id.isin(CANONICAL_IDS)].copy()
    for frame in (w, m, membership, actions):
        frame["security_id"] = frame.security_id.map(canonical)
    actions["new_security_id"] = actions.new_security_id.map(canonical)
    splits = splits[~splits.security_id.isin(CANONICAL_IDS)].copy()
    # The vendor's 1.472 price-adjustment factors represent preferred-share
    # distributions, not extra common shares. Explicit LILAP events replace them.
    splits = splits[~(splits.security_id.isin(["yahoo:LILA", "yahoo:LILAK"]) &
                      splits.date.eq(pd.Timestamp("2026-06-17")))].copy()
    w = w.groupby(["effective_date", "available_date", "security_id"], as_index=False).weight.sum()
    m["share_class"] = m.security_id
    m = m.drop_duplicates("security_id", keep="last")
    membership = membership.drop_duplicates(["effective_date", "security_id"], keep="last")
    if not splits.empty:
        manual_split_keys = set(zip(actions.loc[actions.event_type == "split", "date"],
                                    actions.loc[actions.event_type == "split", "security_id"]))
        splits = splits[[key not in manual_split_keys for key in zip(splits.date, splits.security_id)]].copy()
        splits["event_type"] = "split"
        splits["priority"] = 0
    actions = pd.concat([actions, splits], ignore_index=True)
    actions["priority"] = actions.priority.fillna(20)
    actions = actions.sort_values(["date", "priority"], kind="stable")
    # Explicit action repairs override provider split-factor approximations.
    actions = actions.drop_duplicates(["date", "security_id", "event_type", "new_security_id"], keep="first")
    calendar = pd.read_csv(ROOT / "benchmark/indexes/NASDAQ100.csv", parse_dates=[0])
    calendar = pd.DatetimeIndex(calendar.loc[calendar.iloc[:, 1].notna(), calendar.columns[0]])
    calendar = calendar[(calendar >= "2010-09-30") & (calendar <= "2026-09-30")]
    p = p[p.date.isin(calendar)].copy()
    provisional_rows = []
    for mark in provisional_marks:
        security, first = mark["security_id"], pd.Timestamp(mark["date"])
        actual = p.loc[p.security_id.eq(security) & p.tradable & p.date.gt(first), "date"]
        stop = actual.min() if len(actual) else calendar[-1]+pd.Timedelta(days=1)
        # Forward marks are valuation assumptions, never reconstructed trades.
        for day in calendar[(calendar > first) & (calendar < stop)]:
            ratios = actions.loc[actions.security_id.eq(security) & actions.event_type.eq("split") &
                                 actions.date.gt(first) & actions.date.le(day), "ratio"]
            provisional_rows.append(dict(date=day, security_id=security,
                    price_usd=mark["price_usd"]/ratios.prod(), dividend_usd=0.,
                    source=mark["source"], quality=mark["quality"], tradable=False))
    p = pd.concat([p, pd.DataFrame(provisional_rows)], ignore_index=True)
    p["tradable"] = p.tradable.astype(bool)
    # Replace the vendor distribution when the separately sourced corporate
    # action records the same economic payment. Preserve ordinary dividends.
    replaced_dividends = []
    for a in actions[actions.event_type.eq("cash_dividend")].to_dict("records"):
        mask = p.security_id.eq(a["security_id"]) & p.date.eq(a["date"]) & p.dividend_usd.gt(0)
        for row in p.loc[mask].to_dict("records"):
            replaced_dividends.append(dict(security_id=row["security_id"], date=str(row["date"].date()),
                                           vendor_dividend_usd=row["dividend_usd"], action_dividend_usd=a["cash_usd_per_share"]))
        p.loc[mask, "dividend_usd"] = 0.
    fx = pd.read_csv(ROOT / "benchmark/issuer/cndx_nav_eur.csv", parse_dates=["date"])
    fx = fx.drop_duplicates("date").set_index("date").usd_per_eur
    fx = fx.reindex(fx.index.union(calendar)).sort_index().ffill().reindex(calendar)
    p["price_eur"] = p.price_usd / p.date.map(fx)
    p["dividend_eur"] = p.dividend_usd.fillna(0.) / p.date.map(fx)
    prices = p.set_index(["security_id", "date"]).price_eur.sort_index()
    changes, unresolved = [], []
    legal_terminations = {}
    for a in actions.to_dict("records"):
        k = calendar.searchsorted(a["date"])
        if k == len(calendar):
            continue
        day = calendar[k]
        if a["date"] < calendar[0]:
            continue
        old = a["security_id"]
        kind = a["event_type"]
        new = a.get("new_security_id")
        if kind == "symbol_change":
            if old == new:
                continue
            kind = "stock_exchange"
        row = dict(date=day, security_id=old, event_type=kind,
                   source=a.get("source", ""), notes=a.get("notes", ""),
                   priority=a["priority"], source_date=a["date"])
        if kind == "worthless":
            row["event_type"] = "cash_merger"
            row["cash_eur_per_share"] = 0.
            legal_terminations[old] = day
        elif kind in ("cash_merger", "mixed_merger", "capital_distribution", "cash_dividend", "contingent_cash"):
            row["cash_eur_per_share"] = a["cash_usd_per_share"] / fx.loc[day]
            if a.get("cash_currency") == "GBP":
                gbp = pd.read_csv(source / "yf_GBPUSD=X.csv")
                gbp["date"] = pd.to_datetime(gbp.Date.str[:10])
                rate = gbp.loc[gbp.date <= day, "Close"].iloc[-1]
                row["cash_eur_per_share"] = a["cash_native_per_share"] * rate / fx.loc[day]
        if kind == "contingent_right":
            row.update(successor_id=new, ratio=a["ratio"])
        if kind in ("stock_exchange", "mixed_merger", "spinoff"):
            row.update(successor_id=new, ratio=a["ratio"], tax_treatment="rollover")
            # Explicit best-effort tax assumption: qualification of each foreign
            # reorganisation has not been independently certified for Ireland.
            row["tax_classification_quality"] = a.get("irish_tax_status", "provisional_rollover")
            child_value = prices.get((new, day), np.nan)
            parent_value = prices.get((old, day), np.nan)
            if kind == "mixed_merger":
                row["stock_value_eur_per_old_share"] = child_value * a["ratio"]
            elif kind == "spinoff":
                child_per_old = child_value * a["ratio"]
                companions = actions[(actions.security_id == old) & (actions.date == a["date"]) &
                                     actions.event_type.isin(["mixed_merger", "stock_exchange"])]
                if not companions.empty:
                    # A multi-security takeover is represented by distribution
                    # of the extra class, then a mixed exchange. The old quote
                    # still includes the extra class, so cannot be the residual.
                    companion = companions.iloc[-1]
                    primary_stock = prices.get((companion.new_security_id, day), np.nan)
                    companion_cash = companion.cash_usd_per_share if pd.notna(companion.cash_usd_per_share) else 0.
                    parent_value = companion_cash/fx.loc[day] + companion.ratio*primary_stock
                row["basis_fraction"] = child_per_old / (child_per_old + parent_value)
            if pd.isna(child_value):
                unresolved.append(dict(date=str(day.date()), security_id=old,
                                       successor_id=new, issue="No contemporaneous successor quote"))
        elif kind == "split":
            row["ratio"] = a["ratio"]
        elif kind == "capital_distribution":
            row["remaining_value_eur_per_share"] = prices.get((old, day), np.nan)
        changes.append(row)
    events = pd.DataFrame(changes).sort_values(["date", "priority"], kind="stable")
    # All known extinguished/converted classes become ineligible for purchases,
    # including stale fund reports that still show residual holdings.
    term = events[events.event_type.isin(["cash_merger", "stock_exchange", "mixed_merger"])]
    removal = pd.DataFrame({"effective_date": term.date, "available_date": term.date-pd.Timedelta(days=1),
                            "security_id": term.security_id, "is_member": False})
    membership = pd.concat([membership, removal], ignore_index=True)
    membership["effective_date"] = pd.to_datetime(membership.effective_date)
    membership["available_date"] = pd.to_datetime(membership.available_date)
    membership = membership.drop_duplicates(["effective_date", "security_id"], keep="last")
    # For confirmed bankruptcies only, the last observed untradeable mark is
    # retained until legal cancellation. It is not an executable quote or sale.
    m["max_stale_sessions"] = 10
    # Shares were suspended after the Dec 3 quote, then compulsorily acquired
    # on Jan 20. Retain the last mark; there is no executable intervening sale.
    m.loc[m.security_id == "tts-2880955", "max_stale_sessions"] = 60
    for security, day in legal_terminations.items():
        m.loc[m.security_id == security, "max_stale_sessions"] = 1000
    for mark in provisional_marks:
        security = mark["security_id"]
        if security not in set(m.security_id):
            m = pd.concat([m, pd.DataFrame([dict(security_id=security, share_class=security,
                           currency="USD", ticker=security, max_stale_sessions=10000)])], ignore_index=True)
        m.loc[m.security_id == security, "max_stale_sessions"] = 10000
    events.to_csv(out / "events_prepared.csv", index=False)
    pd.DataFrame(unresolved).to_csv(out / "missing_action_quote_review.csv", index=False)
    input_paths = [source / "prices_usd.csv.gz", source / "actions.csv", source / "split_events.csv",
                   inputs / "best_effort_weights.csv", inputs / "membership.csv", inputs / "metadata.csv"]
    audit = {"classification": "PROVISIONAL_CONSTITUENT_RECONSTRUCTION",
             "price_rows": len(p), "securities": p.security_id.nunique(), "events": len(events),
             "missing_action_quotes": len(unresolved),
             "input_sha256": {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in input_paths},
             "assumptions": [
                 "Current tax and broker fee scenario replayed on historical market data",
                 "Source weights frozen between available snapshots; early weights are stale",
                 "Unresolved purchase weight reserves cash, never renormalized to covered winners",
                 "Foreign stock reorganisations/spin-offs provisionally treated as rollover; cash taxed by part-disposal",
                 "Same-day corporate-action cash settlement and ex-date dividend accrual",
                 "Confirmed bankrupt stocks remain untradeable through missing quote interval until legal cancellation",
                 "Fractional successor entitlements retained; exact broker cash-in-lieu not reconstructed",
                 "Today's broker fractional availability and fee policy assumed; historical broker offerings not reconstructed",
             ]}
    (out / "input_audit.json").write_text(json.dumps(audit, indent=2))
    (out / "provisional_valuation_marks.json").write_text(json.dumps(provisional_marks, indent=2))
    (out / "replaced_vendor_dividends.json").write_text(json.dumps(replaced_dividends, indent=2))
    return p, w, events, m, membership, out
