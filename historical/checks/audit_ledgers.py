"""Independent arithmetic, causal and tax-limit audit of saved strategy outputs.

This script does not run backtests, import the engine, or use its tax helper.
It reconstructs annual CGT from recorded lot proceeds and cost bases. For queued
orders it checks signal eligibility, fixed orders, actual cash and tax deviations.
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
    if not math.isfinite(float(actual)) or not math.isfinite(float(expected)) or abs(float(actual)-float(expected)) > tolerance:
        raise AssertionError(f"{label}: {actual} != {expected}")


def tax(gains, losses, carry, exemption, rate):
    used = min(gains, losses+carry)
    net = gains-used
    exempt = min(net, exemption)
    return dict(tax_due=(net-exempt)*rate, losses_used=used,
                loss_carry_forward=losses+carry-used,
                exemption_used=exempt, taxable_gain=net-exempt)


def check_sale_signal(row, c, gains, losses, carried, pending, policy_spent):
    """Recompute projected lot gains and eligibility from the recorded signal."""
    parts = json.loads(row["signal_lots"])
    order = [(pd.Timestamp(p["acquired"]), p["lot_id"]) for p in parts]
    if not parts or order != sorted(order):
        raise AssertionError("Signal lots do not follow FIFO")
    position_ids = json.loads(row["signal_position_lot_ids"])
    if [p["lot_id"] for p in parts] != position_ids[:len(parts)]:
        raise AssertionError("Signal skipped an earlier FIFO lot")
    if any(p["units"] <= 0 or p["basis_eur"] < 0 for p in parts):
        raise AssertionError("Invalid signal lot units or basis")
    if any((row["date"]-d).days < c["reentry_days"] for d, _ in order):
        raise AssertionError("Signal includes a recent acquisition")
    units, basis = sum(p["units"] for p in parts), sum(p["basis_eur"] for p in parts)
    near(units, row["units"], "Signal units")
    near(basis, row["signal_basis_eur"], "Signal basis")
    net_unit = row["signal_price_eur"]*(1-row["signal_cost_rate"])
    pnl = [p["units"]*net_unit-p["basis_eur"] for p in parts]
    expected_gains, expected_losses = sum(max(p, 0.) for p in pnl), sum(max(-p, 0.) for p in pnl)
    planned_gains = gains+sum(p["expected_gains_eur"] for p in pending.values() if p["side"] == "sell")
    planned_losses = losses+sum(p["expected_losses_eur"] for p in pending.values() if p["side"] == "sell")
    headroom = max(0., c["cgt_exemption"]+planned_losses+carried-planned_gains)
    for name, value in dict(signal_gains_eur=gains, signal_losses_eur=losses,
                            planned_gains_eur=planned_gains, planned_losses_eur=planned_losses,
                            signal_carried_loss_eur=carried, signal_headroom_eur=headroom,
                            expected_gains_eur=expected_gains, expected_losses_eur=expected_losses).items():
        near(value, row[name], name)
    before = tax(planned_gains, planned_losses, carried, c["cgt_exemption"], c["cgt_rate"])
    after = tax(planned_gains+expected_gains, planned_losses+expected_losses,
                carried, c["cgt_exemption"], c["cgt_rate"])
    increment = after["tax_due"]-before["tax_due"]
    near(increment, row["expected_incremental_cgt_eur"], "Signal incremental CGT")
    gain = expected_gains-expected_losses
    if row["reason"] == "gain_harvest":
        if gain <= 0 or gain+TOL < c["gain_harvest_min_eur"] or gain > headroom+TOL or increment > TOL:
            raise AssertionError("Gain signal exceeds known relief or fails its gain threshold")
        if row["reinvest"] == "same_security" and any(p < -1e-8 for p in pnl):
            raise AssertionError("Same-security gain signal includes a losing lot")
    elif row["reason"] == "harvest":
        if -gain+TOL < max(c["harvest_min_loss_eur"], basis*c["harvest_loss_fraction"]) or gain >= 0:
            raise AssertionError("Loss signal fails its loss thresholds")
        if c.get("harvest_lot_mode") == "fifo_prefix" and any(p > 1e-8 for p in pnl):
            raise AssertionError("Loss-prefix signal includes a profitable lot")
        round_trip = units*row["signal_price_eur"]*2*row["signal_cost_rate"]
        if -gain*c["cgt_rate"]+TOL < round_trip*c.get("harvest_cost_multiple", 0.):
            raise AssertionError("Loss signal fails its cost threshold")
    elif row["reason"] == "policy_exit":
        if c["exit_policy"] == "loss_only" and gain >= 0:
            raise AssertionError("Loss-only exit signal is profitable")
        committed = sum(max(0., p["expected_incremental_cgt_eur"]) for p in pending.values()
                        if p["side"] == "sell" and p["reason"] == "policy_exit")
        if c["exit_policy"] == "tax_budget" and policy_spent+committed+max(0., increment) > c["exit_annual_tax_budget_eur"]+TOL:
            raise AssertionError("Exit signal exceeds its known tax budget")
    return parts


def audit_case(path):
    summary = json.loads(path.read_text())
    key = path.name.removesuffix("_summary.json")
    c = summary["configuration"]
    t = pd.read_csv(OUT/f"{key}_transactions.csv.gz", parse_dates=["date"], low_memory=False)
    y = pd.read_csv(OUT/f"{key}_yearly_tax.csv")
    lots = pd.read_csv(OUT/f"{key}_lots.csv.gz")
    rate, exempt = c["cgt_rate"], c["cgt_exemption"]
    queued = c.get("execution_mode", "same_close") == "next_session"

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
    if c.get("harvest_lot_mode") == "fifo_prefix" and not queued:
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
    currencies = {}
    pending, signals, filled, fill_records, order_parts = {}, {}, {}, set(), {}
    cash_balance = policy_spent = 0.
    execution_deviations = []
    day_end_cash = {}
    meta_path = OUT/"metadata_used.csv"
    if meta_path.exists():
        meta = pd.read_csv(meta_path)
        for row in meta.to_dict("records"):
            classes[row["security_id"]] = row.get("share_class") if pd.notna(row.get("share_class")) else row["security_id"]
            currencies[row["security_id"]] = row.get("currency", "USD")
    for row in t.to_dict("records"):
        event, day = row["event"], row["date"]
        security = row.get("security_id")
        klass = classes.get(security, security)
        reason = row.get("reason")
        order_id = row.get("order_id")
        cost = c["half_spread"]+(c["fx_fee"] if str(currencies.get(security, "USD")).upper() != "EUR" else 0.)
        if event == "contribution":
            cash_balance += row["cash_eur"]
        elif event == "dividend":
            cash_balance += row["net_cash_eur"]
        elif event == "sell":
            cash_balance += row["net_proceeds_eur"]
        elif event == "lot_disposal" and reason in ("mixed_merger", "capital_distribution"):
            cash_balance += row["net_proceeds_eur"]
        elif event == "contingent_payment":
            cash_balance += row["gross_proceeds_eur"]-row["fees_eur"]
        elif event == "buy":
            if cash_balance-row["cash_outlay_eur"] < tax(gains, losses, carried, exempt, rate)["tax_due"]-TOL:
                raise AssertionError("Purchase spent reserved tax or unavailable cash")
            cash_balance -= row["cash_outlay_eur"]
        elif event == "cgt_settlement":
            cash_balance -= row["tax_eur"]
        if cash_balance < -TOL:
            raise AssertionError("Negative reconstructed cash")

        if event == "order_signal":
            if not queued or order_id in signals or pd.Timestamp(row["signal_date"]) != day:
                raise AssertionError("Invalid or duplicate order signal")
            if any(classes.get(p["security_id"], p["security_id"]) == klass for p in pending.values()):
                raise AssertionError("Overlapping orders for the same share class")
            if row["side"] == "sell":
                near(row["signal_cost_rate"], cost, "Signal transaction cost")
                parts = check_sale_signal(row, c, gains, losses, carried, pending, policy_spent)
                row["parts"] = parts
                if klass in recent_buys and (day-recent_buys[klass]).days < c["reentry_days"]:
                    raise AssertionError("Sale signal follows a recent same-class purchase")
            elif row["side"] == "buy":
                if not pd.Timestamp(row["weight_available_date"]) < day or pd.Timestamp(row["weight_effective_date"]) > day:
                    raise AssertionError("Buy signal uses unavailable target weights")
                committed = sum(p["cash_budget_eur"] for p in pending.values() if p["side"] == "buy")
                free_cash = cash_balance-tax(gains, losses, carried, exempt, rate)["tax_due"]-committed
                if not math.isfinite(row["cash_budget_eur"]) or row["cash_budget_eur"] < 0 or row["cash_budget_eur"] > free_cash+TOL:
                    raise AssertionError("Buy signal commits unavailable cash")
                if reason == "gain_repurchase":
                    source = filled.get(row["sale_order_id"])
                    if source is None or source["reason"] != "gain_harvest" or source["security_id"] != security:
                        raise AssertionError("Repurchase signal lacks its actual gain sale")
                    if source["date"] != day or any(p["realized_gain_eur"] < -1e-8 for p in source["parts"]):
                        raise AssertionError("Repurchase signal lacks a same-day non-losing matched sale")
                    if row["cash_budget_eur"] > source["net_proceeds_eur"]-max(0., source["actual_incremental_cgt_eur"])+TOL:
                        raise AssertionError("Repurchase budget exceeds after-tax sale proceeds")
            else:
                raise AssertionError("Unknown order side")
            signals[order_id] = row
            pending[order_id] = row
        elif event == "order_split_adjusted":
            order = pending[order_id]
            if order["side"] != "sell" or row["ratio"] <= 0 or order["security_id"] != security:
                raise AssertionError("Invalid pending split adjustment")
            order["units"] *= row["ratio"]
            for part in order["parts"]:
                part["units"] *= row["ratio"]
            near(order["units"], row["units"], "Split-adjusted order units")
        elif event == "order_cancelled":
            if order_id not in pending:
                raise AssertionError("Cancellation lacks a pending order")
            order = pending.pop(order_id)
            if order["security_id"] != security or pd.Timestamp(row["signal_date"]) != order["date"] or day < order["date"]:
                raise AssertionError("Cancellation differs from its signal")
        elif event == "order_fill":
            if order_id not in filled or order_id in fill_records:
                raise AssertionError("Order fill lacks a unique actual trade")
            trade, signal = filled[order_id], signals[order_id]
            if row["side"] != signal["side"] or reason != signal["reason"] or security != signal["security_id"]:
                raise AssertionError("Fill identity differs from its signal")
            if pd.Timestamp(row["signal_date"]) != signal["date"] or pd.Timestamp(row["fill_date"]) != day or trade["date"] != day:
                raise AssertionError("Fill timestamps disagree with signal or actual trade")
            near(row["units"], trade["units"], "Fill units")
            if row["side"] == "sell":
                increment = trade["actual_incremental_cgt_eur"]
                near(row["incremental_cgt_eur"], increment, "Actual fill CGT")
                near(row["expected_incremental_cgt_eur"], signal["expected_incremental_cgt_eur"], "Original CGT estimate")
                near(row["tax_estimate_error_eur"], increment-signal["expected_incremental_cgt_eur"], "Fill tax deviation")
                near(row["realized_gain_eur"], trade["realized_gain_eur"], "Fill realized gain")
                projected_gain = signal["expected_gains_eur"]-signal["expected_losses_eur"]
                execution_deviations.append(dict(order_id=order_id, reason=reason,
                    signal_gain_eur=projected_gain, actual_gain_eur=trade["realized_gain_eur"],
                    signal_incremental_cgt_eur=signal["expected_incremental_cgt_eur"],
                    actual_incremental_cgt_eur=increment,
                    tax_estimate_error_eur=increment-signal["expected_incremental_cgt_eur"],
                    gain_sign_reversed=projected_gain*trade["realized_gain_eur"] < 0))
            else:
                near(row["cash_budget_eur"], signal["cash_budget_eur"], "Fixed fill budget")
                near(row["cash_outlay_eur"], trade["cash_outlay_eur"], "Actual fill outlay")
            fill_records.add(order_id)
        if event == "cgt_settlement":
            settlement = tax(gains, losses, carried, exempt, rate)
            near(settlement["tax_due"], row["tax_eur"], f"CGT settlement {day}")
            near(settlement["loss_carry_forward"], row["loss_carry_forward"], f"CGT carry {day}")
            carried = settlement["loss_carry_forward"]
            gains = losses = 0.
            policy_spent = 0.
        elif event == "lot_disposal":
            pnl = row["realized_gain_eur"]
            if reason == "gain_harvest":
                grouped_gain_parts.append(row)
            if queued and pd.notna(order_id):
                order_parts.setdefault(order_id, []).append(row)
            gains += max(pnl, 0.)
            losses += max(-pnl, 0.)
            if pnl < -1e-9:
                loss_block[klass] = max(loss_block.get(klass, pd.Timestamp.min), day+pd.Timedelta(days=c["reentry_days"]))
        elif event == "contingent_payment":
            gains += max(row["realized_gain_eur"], 0.)
            losses += max(-row["realized_gain_eur"], 0.)
        elif event == "sell" and reason in ("gain_harvest", "harvest", "policy_exit", "rebalance"):
            if queued:
                if order_id not in pending:
                    raise AssertionError("Voluntary sale lacks a pending signal")
                signal = pending.pop(order_id)
                if signal["side"] != "sell" or signal["security_id"] != security or signal["reason"] != reason:
                    raise AssertionError("Sale differs from its signal")
                if not signal["date"] < day or pd.Timestamp(row["signal_date"]) != signal["date"] or pd.Timestamp(row["fill_date"]) != day:
                    raise AssertionError("Sale does not follow its signal on a later date")
                near(row["units"], signal["units"], "Fixed sale units")
                parts = order_parts.pop(order_id, [])
                if [p["lot_id"] for p in parts] != [p["lot_id"] for p in signal["parts"]]:
                    raise AssertionError("Actual matched lots differ from signal")
                for actual, projected_part in zip(parts, signal["parts"]):
                    near(actual["units"], projected_part["units"], "Fixed matched units")
                    near(actual["basis_eur"], projected_part["basis_eur"], "Fixed matched basis")
                    if pd.Timestamp(actual["acquisition"]) != pd.Timestamp(projected_part["acquired"]):
                        raise AssertionError("Matched acquisition date changed")
                parts_gain = sum(max(p["realized_gain_eur"], 0.) for p in parts)
                parts_loss = sum(max(-p["realized_gain_eur"], 0.) for p in parts)
                before = tax(gains-parts_gain, losses-parts_loss, carried, exempt, rate)["tax_due"]
                increment = tax(gains, losses, carried, exempt, rate)["tax_due"]-before
                near(row["realized_gain_eur"], parts_gain-parts_loss, "Actual sale gain")
                near(row["fees_eur"], row["units"]*row["price_eur"]*cost, "Actual sale fees")
                near(row["net_proceeds_eur"], row["units"]*row["price_eur"]-row["fees_eur"], "Actual sale cash")
                filled[order_id] = dict(row, parts=parts, actual_incremental_cgt_eur=increment)
                if reason == "policy_exit":
                    policy_spent += max(0., increment)
            if klass in recent_buys:
                age = (day-recent_buys[klass]).days
                min_purchase_age = age if min_purchase_age is None else min(min_purchase_age, age)
                if age < c["reentry_days"]:
                    raise AssertionError(f"Recent same-class purchase before {reason}: {security} {day} age={age}")
            if reason == "gain_harvest":
                if not queued and row["realized_gain_eur"] <= 0:
                    raise AssertionError("Gain harvest has nonpositive aggregate gain")
                # Include only information booked up to and including this sale.
                projected = max(0., gains-losses-carried-exempt)*rate
                parts_gain = sum(max(p["realized_gain_eur"], 0.) for p in grouped_gain_parts)
                parts_loss = sum(max(-p["realized_gain_eur"], 0.) for p in grouped_gain_parts)
                previous = max(0., gains-parts_gain-(losses-parts_loss)-carried-exempt)*rate
                if not queued and projected-previous > TOL:
                    raise AssertionError(f"Gain harvest exceeded relief known on {day}")
                if not queued and c["gain_harvest_reinvest"] == "same_security" and any(p["realized_gain_eur"] < -1e-9 for p in grouped_gain_parts):
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
            if queued:
                if order_id not in pending:
                    raise AssertionError("Purchase lacks a pending signal")
                signal = pending.pop(order_id)
                if signal["side"] != "buy" or signal["security_id"] != security or signal["reason"] != reason:
                    raise AssertionError("Purchase differs from its signal")
                if not signal["date"] < day or pd.Timestamp(row["signal_date"]) != signal["date"] or pd.Timestamp(row["fill_date"]) != day:
                    raise AssertionError("Purchase does not follow its signal on a later date")
                if row["cash_outlay_eur"] > signal["cash_budget_eur"]+TOL:
                    raise AssertionError("Purchase exceeded fixed notional budget")
                near(row["fees_eur"], row["units"]*row["price_eur"]*cost, "Actual buy fees")
                near(row["cash_outlay_eur"], row["units"]*row["price_eur"]+row["fees_eur"], "Actual buy cash")
                basis = row["cash_outlay_eur"] if c["acquisition_costs_in_basis"] else row["units"]*row["price_eur"]
                near(row["basis_eur"], basis, "Actual buy basis")
                for field in ("weight_effective_date", "weight_available_date"):
                    if pd.Timestamp(row[field]) != pd.Timestamp(signal[field]):
                        raise AssertionError("Purchase changed its signal target weights")
                filled[order_id] = row
            if day < loss_block.get(klass, pd.Timestamp.min):
                blocked_buy_violations.append(dict(date=str(day.date()), security_id=security))
            if reason == "gain_repurchase":
                repurchases += 1
                if queued:
                    if row["sale_order_id"] != signal["sale_order_id"]:
                        raise AssertionError("Repurchase changed its originating sale")
                    source = filled[row["sale_order_id"]]
                    if not source["date"] < day:
                        raise AssertionError("Repurchase did not follow its sale on a later date")
                    parts = source["parts"]
                else:
                    preceding = [x for x in gain_sales if x["date"] == str(day.date()) and x["security_id"] == security]
                    if not preceding:
                        raise AssertionError("Gain repurchase lacks a same-day gain disposal")
                    parts = gain_parts_by_sale[(day, security)]
                if any(part["realized_gain_eur"] < -1e-8 for part in parts):
                    raise AssertionError("Immediate gain repurchase follows a losing matched lot")
            recent_buys[klass] = day
        day_end_cash[day] = dict(cash_eur=cash_balance,
                                cgt_reserve_eur=tax(gains, losses, carried, exempt, rate)["tax_due"])
    near(cash_balance, summary["final_cash"], "Chronological cash reconstruction")
    if queued and (pending or order_parts or set(filled) != fill_records):
        raise AssertionError("Unresolved orders or missing fill records at the terminal date")
    if blocked_buy_violations:
        raise AssertionError(f"Voluntary purchases during same-class block: {blocked_buy_violations[:3]}")
    # Actual scheduled execution must use the first observed session, rather
    # than a retrospectively favourable day within the review interval.
    daily = pd.read_csv(OUT/f"{key}_daily.csv.gz", usecols=["date", "cash_eur", "cgt_reserve_eur"], parse_dates=["date"])
    reconstructed = pd.DataFrame.from_dict(day_end_cash, orient="index").reindex(daily.date).ffill().fillna(0.)
    for field in ("cash_eur", "cgt_reserve_eur"):
        if daily[field].isna().any():
            raise AssertionError(f"Missing daily {field}")
        near(abs(daily[field].to_numpy()-reconstructed[field].to_numpy()).max(initial=0.), 0., f"Daily {field}")
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
                execution_mode=c.get("execution_mode", "same_close"),
                queued_signals_checked=len(signals), queued_fills_checked=len(fill_records),
                execution_deviations=execution_deviations,
                sign_reversals_at_fill=sum(d["gain_sign_reversed"] for d in execution_deviations),
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
