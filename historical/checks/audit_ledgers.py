"""Independent arithmetic, causal and tax-limit audit of saved strategy outputs.

This script does not run backtests, import the engine, or use its tax helper.
It reconstructs annual CGT from recorded lot proceeds and cost bases and checks
that proactive gains never consume more relief than was known on their date.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/latest/ledgers"
TOL = 2e-5


def near(actual, expected, label, tolerance=TOL):
    if not math.isfinite(float(actual)) or abs(float(actual)-float(expected)) > tolerance:
        raise AssertionError(f"{label}: {actual} != {expected}")


def tax(gains, losses, carry, exemption, rate):
    used = min(gains, losses+carry)
    net = gains-used
    exempt = min(net, exemption)
    return dict(tax_due=(net-exempt)*rate, losses_used=used,
                loss_carry_forward=losses+carry-used,
                exemption_used=exempt, taxable_gain=net-exempt)


def audit_case(path):
    summary = json.loads(path.read_text())
    key = path.name.removesuffix("_summary.json")
    c = summary["configuration"]
    t = pd.read_csv(OUT/f"{key}_transactions.csv.gz", parse_dates=["date"], low_memory=False)
    y = pd.read_csv(OUT/f"{key}_yearly_tax.csv")
    lots = pd.read_csv(OUT/f"{key}_lots.csv.gz")
    rate, exempt = c["cgt_rate"], c["cgt_exemption"]

    def total(event, field, reason=None):
        if field not in t:
            return 0.
        mask = t.event.eq(event)
        if reason is not None:
            mask &= t.reason.eq(reason)
        return float(t.loc[mask, field].sum())

    cash = (total("contribution", "cash_eur") + total("dividend", "net_cash_eur")
            + total("sell", "net_proceeds_eur")
            + total("lot_disposal", "net_proceeds_eur", "mixed_merger")
            + total("lot_disposal", "net_proceeds_eur", "capital_distribution")
            + total("contingent_payment", "gross_proceeds_eur")
            - total("contingent_payment", "fees_eur")
            - total("buy", "cash_outlay_eur") - total("cgt_settlement", "tax_eur"))
    near(cash, summary["final_cash"], "Final cash")
    basis_error = total("buy", "basis_eur")-total("lot_disposal", "basis_eur")
    near(basis_error, 0., "Cost-basis conservation")
    if not (lots.units.abs() < 1e-8).all() or not (lots.basis_eur.abs() < 1e-7).all():
        raise AssertionError("Open terminal lots")
    disposals = t.loc[t.event.eq("lot_disposal")].copy()
    near((disposals.net_proceeds_eur-disposals.basis_eur-disposals.realized_gain_eur).abs().max(), 0., "Lot gain formula")
    if c.get("harvest_lot_mode") == "fifo_prefix":
        harvested_parts = disposals.loc[disposals.reason.eq("harvest")]
        if (harvested_parts.realized_gain_eur > 1e-8).any():
            raise AssertionError("Loss-prefix harvest consumed a profitable lot")
    buys = t.loc[t.event.eq("buy")]
    if not (pd.to_datetime(buys.weight_available_date) < buys.date).all():
        raise AssertionError("Buy before source weight became available")

    # Independent annual reconstruction, including actual contingent cash gains.
    carry = 0.
    for annual in y.sort_values("year").itertuples():
        pnl = disposals.loc[disposals.date.dt.year.eq(annual.year), "realized_gain_eur"]
        rights = t.loc[t.event.eq("contingent_payment") & t.date.dt.year.eq(annual.year), "realized_gain_eur"]
        gains = float(pnl.clip(lower=0).sum()+rights.clip(lower=0).sum())
        losses = float(-pnl.clip(upper=0).sum()-rights.clip(upper=0).sum())
        near(gains, annual.gains_eur, f"{annual.year} annual gains")
        near(losses, annual.losses_eur, f"{annual.year} annual losses")
        near(carry, annual.brought_forward_loss_eur, f"{annual.year} carry in")
        settlement = tax(gains, losses, carry, exempt, rate)
        for field, amount in settlement.items():
            near(amount, getattr(annual, field), f"{annual.year} {field}")
        carry = settlement["loss_carry_forward"]
    near(y.tax_due.sum(), summary["total_cgt"], "Total CGT")
    near(y.dividend_tax_eur.sum(), summary["total_dividend_tax"], "Total dividend tax")

    # Respect order within each day: later loss rows never finance earlier gains.
    gains = losses = carried = 0.
    grouped_gain_parts = []
    gain_sales = []
    gain_parts_by_sale = {}
    recent_buys = {}
    loss_block = {}
    min_purchase_age = None
    repurchases = 0
    blocked_buy_violations = []
    classes = {}
    meta_path = OUT/"metadata_used.csv"
    if meta_path.exists():
        meta = pd.read_csv(meta_path)
        for row in meta.to_dict("records"):
            classes[row["security_id"]] = row.get("share_class") if pd.notna(row.get("share_class")) else row["security_id"]
    for row in t.to_dict("records"):
        event, day = row["event"], row["date"]
        security = row.get("security_id")
        klass = classes.get(security, security)
        reason = row.get("reason")
        if event == "cgt_settlement":
            settlement = tax(gains, losses, carried, exempt, rate)
            near(settlement["tax_due"], row["tax_eur"], f"CGT settlement {day}")
            near(settlement["loss_carry_forward"], row["loss_carry_forward"], f"CGT carry {day}")
            carried = settlement["loss_carry_forward"]
            gains = losses = 0.
        elif event == "lot_disposal":
            pnl = row["realized_gain_eur"]
            if reason == "gain_harvest":
                grouped_gain_parts.append(row)
            gains += max(pnl, 0.)
            losses += max(-pnl, 0.)
            if pnl < -1e-9:
                loss_block[klass] = max(loss_block.get(klass, pd.Timestamp.min), day+pd.Timedelta(days=c["reentry_days"]))
        elif event == "contingent_payment":
            gains += max(row["realized_gain_eur"], 0.)
            losses += max(-row["realized_gain_eur"], 0.)
        elif event == "sell" and reason in ("gain_harvest", "harvest", "policy_exit"):
            if klass in recent_buys:
                age = (day-recent_buys[klass]).days
                min_purchase_age = age if min_purchase_age is None else min(min_purchase_age, age)
                if age < c["reentry_days"]:
                    raise AssertionError(f"Recent same-class purchase before {reason}: {security} {day} age={age}")
            if reason == "gain_harvest":
                if row["realized_gain_eur"] <= 0:
                    raise AssertionError("Gain harvest has nonpositive aggregate gain")
                # Include only information booked up to and including this sale.
                projected = max(0., gains-losses-carried-exempt)*rate
                parts_gain = sum(max(p["realized_gain_eur"], 0.) for p in grouped_gain_parts)
                parts_loss = sum(max(-p["realized_gain_eur"], 0.) for p in grouped_gain_parts)
                previous = max(0., gains-parts_gain-(losses-parts_loss)-carried-exempt)*rate
                if projected-previous > TOL:
                    raise AssertionError(f"Gain harvest exceeded relief known on {day}")
                if c["gain_harvest_reinvest"] == "same_security" and any(p["realized_gain_eur"] < -1e-9 for p in grouped_gain_parts):
                    raise AssertionError("Immediate-repurchase gain sale contains a losing matched lot")
                gain_sales.append(dict(date=str(day.date()), security_id=security,
                                       gain_eur=row["realized_gain_eur"], incremental_cgt_eur=projected-previous))
                gain_parts_by_sale[(day, security)] = grouped_gain_parts
                grouped_gain_parts = []
                if c["gain_harvest_reinvest"] == "underweights":
                    loss_block[klass] = day+pd.Timedelta(days=c["reentry_days"])
        elif event == "gain_harvest":
            if row.get("reinvest") == "underweights":
                loss_block[klass] = day+pd.Timedelta(days=c["reentry_days"])
        elif event == "buy":
            if day < loss_block.get(klass, pd.Timestamp.min):
                blocked_buy_violations.append(dict(date=str(day.date()), security_id=security))
            if reason == "gain_repurchase":
                repurchases += 1
                preceding = [x for x in gain_sales if x["date"] == str(day.date()) and x["security_id"] == security]
                if not preceding:
                    raise AssertionError("Gain repurchase lacks a same-day gain disposal")
                parts = gain_parts_by_sale[(day, security)]
                if any(part["realized_gain_eur"] < -1e-8 for part in parts):
                    raise AssertionError("Immediate gain repurchase follows a losing matched lot")
            recent_buys[klass] = day
    if blocked_buy_violations:
        raise AssertionError(f"Voluntary purchases during same-class block: {blocked_buy_violations[:3]}")
    # Actual scheduled execution must use the first observed session, rather
    # than a retrospectively favourable day within the review interval.
    daily = pd.read_csv(OUT/f"{key}_daily.csv.gz", usecols=["date"], parse_dates=["date"])
    for row in t.loc[t.event.isin(["gain_review", "harvest_review"])].to_dict("records"):
        scheduled = pd.Timestamp(row["scheduled_date"])
        first = daily.loc[daily.date.ge(scheduled), "date"].iloc[0]
        if first != row["date"]:
            raise AssertionError(f"Review did not use first session: {row['event']} {scheduled}")
    receipt_details = []
    affected_disposal_indices = set()
    disposal_classes = disposals.security_id.map(lambda s: classes.get(s, s))
    for receipt in t.loc[t.event.eq("automatic_receipt_during_loss_block")].to_dict("records"):
        klass = classes.get(receipt["security_id"], receipt["security_id"])
        recent = disposals.loc[disposal_classes.eq(klass)
                               & disposals.date.lt(receipt["date"])
                               & disposals.date.ge(receipt["date"]-pd.Timedelta(days=28))
                               & disposals.realized_gain_eur.lt(0)]
        affected_disposal_indices.update(recent.index)
        receipt_details.append(dict(date=str(receipt["date"].date()), security_id=receipt["security_id"],
                                    maximum_loss_relief_affected_eur=float(-recent.realized_gain_eur.sum())))
    affected_loss = float(-disposals.loc[list(affected_disposal_indices), "realized_gain_eur"].sum())
    return dict(key=key, status="PASS", final_cash=summary["final_cash"],
                cash_error_eur=cash-summary["final_cash"], basis_error_eur=basis_error,
                cumulative_exemption_used_eur=float(y.exemption_used.sum()),
                nominal_cgt_avoided_by_exemption_eur=float(y.exemption_used.sum()*rate),
                gain_harvest_sales=len(gain_sales), gain_repurchase_count=repurchases,
                min_preceding_purchase_age_days=min_purchase_age,
                maximum_gain_harvest_incremental_cgt_eur=max([x["incremental_cgt_eur"] for x in gain_sales], default=0.),
                automatic_receipts_during_block=int(t.event.eq("automatic_receipt_during_loss_block").sum()),
                automatic_receipt_details=receipt_details,
                forced_receipt_permanent_loss_denial_tax_upper_bound_eur=affected_loss*rate,
                caveats=["Frozen-rate, unused-personal-exemption scenario; input corporate actions provisional",
                         "Foreign currency balances are not independently modelled",
                         "Voluntary same-class blocking verified; forced receipts remain separately disclosed",
                         "Terminal differences include exposure, costs and reinvestment, not just tax alpha"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args()
    checks = []
    for path in sorted(OUT.glob("*_summary.json")):
        key = path.name.removesuffix("_summary.json")
        if args.only and key not in args.only:
            continue
        try:
            check = audit_case(path)
        except Exception as exc:
            check = dict(key=key, status="FAIL", error=str(exc))
        checks.append(check)
        print(f"{check['key']}: {check['status']}" + (f" {check['error']}" if "error" in check else ""), flush=True)
    audit = dict(case_count=len(checks), all_passed=bool(checks) and all(x["status"] == "PASS" for x in checks),
                 independent_of_engine_tax_helper=True, checks=checks)
    if not args.only:
        expected = {s["key"] for s in json.loads((OUT.parent/"policy_definitions.json").read_text())}
        audit["complete_predeclared_case_set"] = expected == {x["key"] for x in checks}
        audit["all_passed"] &= audit["complete_predeclared_case_set"]
    engine = ROOT/"model/direct_stock_backtest.py"
    audit["engine_sha256"] = hashlib.sha256(engine.read_bytes()).hexdigest()
    audit["audit_code_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (OUT.parent/"independent_ledger_audit.json").write_text(json.dumps(audit, indent=2))
    if not audit["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
