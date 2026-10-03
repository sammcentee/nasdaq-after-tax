"""Build causal best-effort source weights without removing unsupported weight.

This crosswalk does not certify prices or Irish corporate-action tax treatment.
Run after optional additional_identity_overrides.json has been supplied. Never
rewrite canonical source inputs, interpolate weights, or use future snapshots.
"""
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd

P = Path(__file__).resolve().parent
H = P.parents[1]
CASH = "__CASH__"

SOURCES = {
    "ALTR": "https://www.sec.gov/Archives/edgar/data/768251/000119312515414631/d102231d8k.htm",
    "LIFE": "https://www.sec.gov/Archives/edgar/data/1073431/000119312514033495/d655804d8k.htm",
    "VIP": "https://www.sec.gov/Archives/edgar/data/1468091/000119312517103808/d320784dex991.htm",
    "OLD_FOX": "https://www.sec.gov/Archives/edgar/data/1308161/000119312513281456/d562317dex991.htm",
    "KFT": "https://www.sec.gov/Archives/edgar/data/1103982/000119312512411522/d418430dex991.htm",
    "LMCA": "https://www.libertymedia.com/investors/stock-data/faq",
    "WLTW": "https://investors.wtwco.com/news-releases/news-release-details/willis-towers-watson-announces-nasdaq-ticker-symbol-change-wltw",
    "YHOO": "https://www.sec.gov/Archives/edgar/data/1011006/000119312517206955/d389206d8k.htm",
    "LILA": "https://www.libertyglobal.com/investors/share-information/share-cost-basis/",
    "GOLD": "https://www.sec.gov/Archives/edgar/data/1175580/000114420419000112/tv510199_ex99-3.htm",
}

def resolve(row, extensions):
    """Return ID, status, evidence. Date limits prevent reused-ticker errors."""
    ticker, date = row["ticker"], row["effective_date"]
    if ticker == "ALTR" and date < "2016-01-01":
        return "tts-130097863", "primary_CIK_identity_repaired", SOURCES["ALTR"]
    if ticker == "LIFE" and date < "2014-02-04":
        return "tts-88339869", "primary_CIK_identity_repaired", SOURCES["LIFE"]
    if ticker == "VIP":
        return "tts-120075582", "primary_issuer_rename", SOURCES["VIP"]
    if (ticker == "FOXA" and date < "2019-03-20") or (ticker == "NWSA" and date < "2013-07-01"):
        return "tts-161284560", "historical_issuer_class_A", SOURCES["OLD_FOX"]
    if ticker == "FOX" and date < "2019-03-20":
        return "tts-161284558", "historical_issuer_class_B", SOURCES["OLD_FOX"]
    if ticker == "KFT":
        # Same parent identity. Pre-October prices and the child KRFT spin still
        # require explicit price/action records if the strategy owns it then.
        return "tts-51210920", "primary_parent_rename_requires_spinoff_ledger", SOURCES["KFT"]
    if ticker in ("LMCA", "LMCK") and date >= "2016-04-18":
        return ("tts-117027845" if ticker == "LMCA" else "tts-117027846"), "post_recapitalization_rename_only", SOURCES["LMCA"]
    for extension in extensions:
        if ticker not in extension.get("tickers", []):
            continue
        if not extension.get("from_date", "0000") <= date <= extension.get("to_date", "9999"):
            continue
        if extension.get("original_security_id") and extension["original_security_id"] != row["security_id"]:
            continue
        return extension["security_id"], extension["quality"], extension["source_url"]
    if row.get("price_id", ""):
        return row["price_id"], "existing_candidate_crosswalk", "../dated_security_identity_map.csv"
    return row["security_id"], "unresolved_price_identity", ""


def main():
    assets = pd.read_csv(H / "prices/quantiacs_asset_coverage.csv").fillna("")
    weights = pd.read_csv(H / "inputs/target_weights.csv").fillna("")
    canonical_unresolved = int(weights.price_id.eq("").sum())
    extra_source = P / "usaa_20100630_source_weights.csv"
    if extra_source.exists():
        weights = pd.concat([weights, pd.read_csv(extra_source).fillna("")], ignore_index=True)
    quarterly_source = P / "usaa_quarterly_source_weights.csv"
    if quarterly_source.exists():
        weights = pd.concat([weights, pd.read_csv(quarterly_source).fillna("")], ignore_index=True)
    member = pd.read_csv(H / "inputs/membership_snapshots_dated.csv").fillna("")
    extension_path = P / "additional_identity_overrides.json"
    extensions = json.loads(extension_path.read_text()) if extension_path.exists() else []
    original_unresolved = int(weights.price_id.eq("").sum())
    for frame in (weights, member):
        frame["original_security_id"] = frame.security_id
        frame["original_price_id"] = frame.price_id
        mapped = [resolve(row, extensions) for row in frame.to_dict("records")]
        frame[["security_id", "repair_quality", "repair_source_url"]] = pd.DataFrame(mapped, index=frame.index)
        frame["price_id"] = frame.security_id.where(frame.repair_quality.ne("unresolved_price_identity"), "")
    weights.to_csv(P / "source_weights_with_repairs.csv", index=False)
    member.to_csv(P / "membership_snapshots_with_repairs.csv", index=False)

    # Keep every unsupported source name in the evidence file; combine only its
    # engine allocation into an explicit non-investing, zero-interest cash target.
    rows = []
    for (effective, available), group in weights.groupby(["effective_date", "available_date"], sort=True):
        for security, part in group.groupby("security_id"):
            unresolved = part.price_id.eq("").all()
            rows.append(dict(effective_date=effective, available_date=available,
                             security_id=CASH if unresolved else security,
                             weight=float(part.weight.sum()), source=str(part.source.iloc[0])))
    engine = pd.DataFrame(rows).groupby(["effective_date", "available_date", "security_id", "source"], as_index=False).weight.sum()
    assert np.allclose(engine.groupby(["effective_date", "available_date"]).weight.sum(), 1.0)
    engine.to_csv(P / "best_effort_weights.csv", index=False)

    # Convert complete membership snapshots to additions/removals. Initialize all
    # source identities explicitly so departed 2009 names are not bought in 2010.
    # Membership publication timing remains a declared community-data assumption.
    universe = set(weights.security_id) | set(member.security_id) | {CASH}
    first_date = member.effective_date.min()
    state = {security: False for security in universe}
    updates = []
    for date, group in member.groupby("effective_date", sort=True):
        current = set(group.security_id)
        for security in sorted(universe):
            value = security in current and security != CASH
            if date == first_date or value != state[security]:
                updates.append(dict(effective_date=date, available_date=date,
                                    security_id=security, is_member=value,
                                    reason="historical_membership_snapshot",
                                    availability_quality="ASSUMED_public_by_effective_date_used_only_after_date"))
            state[security] = value
    # Some fund snapshots retain tiny accounting balances after redemption.
    # They do not authorize fresh purchases of an extinguished security.
    for date, security, reason in [
        ("2014-02-04", "tts-88339869", "LIFE_cash_redemption"),
        ("2015-12-28", "tts-130097863", "ALTR_cash_redemption"),
        ("2019-03-20", "tts-161284560", "old_FOXA_merger"),
        ("2019-03-20", "tts-161284558", "old_FOX_merger"),
    ]:
        updates.append(dict(effective_date=date, available_date=date, security_id=security,
                            is_member=False, reason=reason,
                            availability_quality="effective_action_date_next_session"))
    updates = pd.DataFrame(updates).drop_duplicates(["effective_date", "security_id"], keep="last").sort_values(["effective_date", "security_id"])
    updates.to_csv(P / "membership.csv", index=False)

    meta = []
    by_id = assets.set_index("id").to_dict("index")
    for security in sorted(universe):
        group = weights[weights.security_id.eq(security)]
        a = by_id.get(security, {})
        meta.append(dict(security_id=security, share_class=security,
                         currency="EUR" if security == CASH else "USD",
                         ticker="|".join(sorted(set(group.ticker))) or a.get("symbol", ""),
                         name=" | ".join(sorted(set(group.name))) or a.get("name", ""),
                         vendor_cik=a.get("cik", ""),
                         price_identity_resolved=bool(security in set(weights.loc[weights.price_id.ne(""), "security_id"])),
                         dividend_withholding=0.0 if security == CASH else 0.15,
                         withholding_assumption="zero_interest_cash" if security == CASH else "15_percent_generic_model_assumption_not_issuer_specific"))
    pd.DataFrame(meta).to_csv(P / "metadata.csv", index=False)
    unresolved = weights[weights.price_id.eq("")]
    unresolved.groupby(["ticker", "security_id"], as_index=False).agg(
        first_source_date=("effective_date", "min"), last_source_date=("effective_date", "max"),
        source_rows=("weight", "size"), maximum_snapshot_weight=("weight", "max"),
        names=("name", lambda s: " | ".join(sorted(set(s))))
    ).to_csv(P / "unresolved_identities.csv", index=False)
    weights.loc[weights.original_security_id.ne(weights.security_id)].groupby(
        ["ticker", "original_security_id", "security_id", "repair_quality", "repair_source_url"], as_index=False
    ).agg(first_source_date=("effective_date", "min"), last_source_date=("effective_date", "max"), source_rows=("weight", "size")).to_csv(P / "identity_repairs.csv", index=False)

    contributions = pd.read_csv(H / "results/latest/etf/events.csv.gz")
    dates = sorted(contributions.loc[contributions.event.eq("contribution"), "date"])
    snapshots = sorted(set(zip(weights.effective_date, weights.available_date)))
    coverage = []
    for date in dates:
        eligible = [pair for pair in snapshots if pair[0] <= date and pair[1] < date]
        assert eligible, date
        effective, available = eligible[-1]
        target = weights[(weights.effective_date == effective) & (weights.available_date == available)]
        current_updates = updates[(updates.effective_date <= date) & (updates.available_date < date)].drop_duplicates("security_id", keep="last")
        current = set(current_updates.loc[current_updates.is_member, "security_id"])
        unknown = target.price_id.eq("")
        departed = ~target.security_id.isin(current)
        reference_ids = set(target.security_id)
        coverage.append(dict(
            purchase_date=date, source_effective_date=effective, source_available_date=available,
            source=str(target.source.iloc[0]), source_age_days=(pd.Timestamp(date) - pd.Timestamp(effective)).days,
            mapped_snapshot_weight=float(target.loc[~unknown, "weight"].sum()),
            unresolved_weight_reserved_as_cash=float(target.loc[unknown, "weight"].sum()),
            mapped_current_member_target_weight=float(target.loc[~unknown & ~departed, "weight"].sum()),
            departed_source_weight_not_bought=float(target.loc[departed & ~unknown, "weight"].sum()),
            unresolved_tickers="|".join(sorted(set(target.loc[unknown, "ticker"]))),
            new_members_without_source_weight=len(current - reference_ids),
            no_future_snapshot_used=available < date and effective <= date,
        ))
    coverage = pd.DataFrame(coverage)
    coverage.to_csv(P / "purchase_date_coverage.csv", index=False)
    validation = {
        "complete_snapshot_sums_preserved": bool(np.allclose(weights.groupby(["effective_date", "available_date"]).weight.sum(), engine.groupby(["effective_date", "available_date"]).weight.sum())),
        "no_duplicate_engine_target": bool(not engine.duplicated(["effective_date", "available_date", "security_id"]).any()),
        "no_duplicate_membership_update": bool(not updates.duplicated(["effective_date", "security_id"]).any()),
        "all_192_deposits_use_strictly_prior_information": bool(len(coverage) == 192 and coverage.no_future_snapshot_used.all()),
        "first_deposit_source_date": str(coverage.iloc[0].source_effective_date),
        "first_deposit_source_age_days": int(coverage.iloc[0].source_age_days),
        "first_deposit_new_members_without_weight": int(coverage.iloc[0].new_members_without_source_weight),
        "first_deposit_current_member_mapped_weight": float(coverage.iloc[0].mapped_current_member_target_weight),
        "first_deposit_explicit_missing_cash_weight": float(coverage.iloc[0].unresolved_weight_reserved_as_cash),
        "last_unresolved_source_purchase_date": str(coverage[coverage.unresolved_weight_reserved_as_cash > 0].purchase_date.max()),
    }
    assert all(v for v in validation.values() if isinstance(v, bool)), validation
    (P / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    manifest = {
        "status": "BEST_EFFORT_CAUSAL_INPUTS; price and corporate-action certification is separate",
        "source_snapshots": len(snapshots), "source_rows": len(weights),
        "canonical_original_unresolved_rows": canonical_unresolved,
        "original_unresolved_rows": original_unresolved, "remaining_unresolved_rows": len(unresolved),
        "identity_rows_repaired": original_unresolved - len(unresolved),
        "remaining_unresolved_unique_tickers": sorted(set(unresolved.ticker)),
        "monthly_deposits_audited": len(coverage),
        "mean_unresolved_target_weight": float(coverage.unresolved_weight_reserved_as_cash.mean()),
        "max_unresolved_target_weight": float(coverage.unresolved_weight_reserved_as_cash.max()),
        "mean_mapped_current_member_target_weight": float(coverage.mapped_current_member_target_weight.mean()),
        "all_trade_source_dates_strictly_prior": bool(coverage.no_future_snapshot_used.all()),
        "assumptions": [
            "Latest effective source snapshot is used only when its available date is strictly before the trade date.",
            "No future weight interpolation, current-constituent backfill, or normalization excluding missing names.",
            "Unresolved source allocation is explicitly __CASH__, earns zero interest, and must remain cash in the caller's engine.",
            "A mapped price identity does not certify its daily prices, corporate actions, distribution classification, or successor tax basis.",
            "The June2010 USAA Nasdaq100 Fund equity portfolio, filed August27, supplies a more recent causal initial proxy; the September2009 QQQ snapshot is retained only as older source evidence.",
            "Thirteen additional SEC-filed USAA Nasdaq100 Fund reports supply quarterly source weights through September2013, usable strictly after each filing date.",
            "Later source weights are held fixed between available snapshots. January-June 2017 missing snapshots are not interpolated.",
            "Monthly CNDX publication uses an unverified five-business-day lag; membership changes are assumed known on their effective date and used strictly afterward.",
            "Known deletions bar new purchases; held shares remain until a loss sale, mandatory corporate action, or final liquidation.",
            "Additions with no weight in the latest available source receive no invented weight.",
            "Historical Trading 212 availability, fractional shares and exact spreads are not established by these market data.",
            "Some old source tickers are retroactively relabeled by the fund provider; historical ISIN, source date and issuer records govern the crosswalk.",
        ],
        "primary_identity_sources": SOURCES,
        "input_sha256": {str(path.relative_to(H)): hashlib.sha256(path.read_bytes()).hexdigest() for path in [H / "inputs/target_weights.csv", H / "inputs/membership_snapshots_dated.csv", H / "prices/quantiacs_asset_coverage.csv", extra_source, quarterly_source, extension_path] if path.exists()},
    }
    (P / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: v for k, v in manifest.items() if k not in ("assumptions", "primary_identity_sources", "input_sha256")}, indent=2))


if __name__ == "__main__":
    main()
