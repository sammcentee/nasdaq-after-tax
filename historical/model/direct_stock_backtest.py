"""Auditable, long-only direct-share replay under a frozen Irish-tax scenario.

Inputs are RAW (not dividend/split-adjusted) EUR close prices and gross cash
dividends per share. Conversion must use each observation's historical FX rate.
Full target snapshots require effective_date AND available_date; an observation
is usable only when available_date < trade date and effective_date <= trade date.
By default constituent deletions never cause sales. Optional announced review
policies sell departed holdings in full, within a realised-CGT budget, or in
fixed fractions. Fresh cash and sale proceeds buy current underweights. The
ordinary harvesting rule sells whole positions at an aggregate loss, with a
same-class 29-day exclusion before and after sale. Final liquidation sells all.
Optional proactive gain harvesting consumes only currently known annual CGT
headroom, including mandatory use of carried losses before the exemption. A
partial FIFO sale either redirects cash to underweights with a 29-day embargo,
or immediately replaces a wholly non-losing FIFO prefix of a current target.
The replacement is self-financing after both sides' transaction costs.

This engine cannot certify an input corpus. The caller must audit security
identities, gross dividends, raw prices, actions, historical weights and FX.
Explicit unresolved events/flags and excessive held-price gaps fail closed.
No terminal disappearance is converted into an invented sale or zero value.

Supported actions: split; taxable cash_merger; stock_exchange with explicitly
confirmed rollover treatment; spinoff with explicitly confirmed rollover and
documented child basis_fraction. mixed_merger applies cash part-disposal with
rollover of the share consideration, using explicit successor market value.
capital_distribution applies cash part-disposal while retaining the parent.
Dividend quantities refer to shares AFTER same-day actions. Dates on actions
are effective dates, not announcement dates. Event tax classifications remain
the caller's responsibility, including disclosed provisional classifications.

Dividend tax is reserved immediately from gross income. CGT is reserved from
cash as gains occur, then settled at the first session of the next year (or at
final liquidation). This reserve convention is not Revenue's payment calendar.
Harvested losses never generate a cash rebate. Unused losses have no terminal
cash value. Default 52.35% dividend tax is a configurable marginal-rate scenario,
not a claim about every higher-rate taxpayer or historical Irish law.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import floor, isfinite
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tax"))
from irish_tax import settle_cgt_year, settle_us_dividend


class DataIntegrityError(ValueError):
    """The data cannot support an auditable valuation or transaction."""


@dataclass(frozen=True)
class BacktestConfig:
    start: str = "2010-09-30"
    end: str = "2026-09-30"
    monthly_contribution: float = 1000.0
    contribution_dates: tuple[str, ...] | None = None
    contribution_amounts: tuple[float, ...] | None = None  # chronological scheduled_contributions order
    harvest: bool = True
    harvest_frequency: str = "contribution_dates"  # or daily
    investment_frequency: str = "contribution_dates"  # or daily
    reinvest_after_disposal: bool = True
    minimum_order_eur: float = 1.0
    harvest_loss_fraction: float = 0.05
    harvest_min_loss_eur: float = 25.0
    harvest_review_dates: tuple[str, ...] | None = None  # replaces the default TLH cadence
    harvest_cost_multiple: float = 0.0  # potential loss relief / estimated round-trip costs
    harvest_lot_mode: str = "position"  # fifo_prefix or position_or_fifo_prefix
    gain_harvest: bool = False
    gain_review_dates: tuple[str, ...] | None = None  # None uses announced deposit dates
    gain_harvest_scope: str = "all"  # all known holdings, or departed
    gain_harvest_reinvest: str = "underweights"  # same_security, or hybrid (replace current targets only)
    gain_harvest_ranking: str = "overweight"  # or efficient (gain per euro of proceeds)
    gain_harvest_min_eur: float = 0.0
    reentry_days: int = 29
    cgt_rate: float = 0.33
    cgt_exemption: float = 1270.0
    dividend_income_tax: float = 0.40
    dividend_usc: float = 0.08
    dividend_prsi: float = 0.0435
    foreign_dividend_withholding: float = 0.15
    fx_fee: float = 0.0015  # charged each USD/non-EUR buy AND sale
    half_spread: float = 0.0  # 0.0005 means a 0.10% round trip
    acquisition_costs_in_basis: bool = True  # acquisition-only; sale costs still deducted
    fractional_shares: bool = True
    max_stale_sessions: int = 5
    liquidate_at_end: bool = True
    cash_target_security_id: str = "__CASH__"
    missing_target_policy: str = "error"  # or reserve_cash; never fabricates prices
    exit_policy: str = "retain"  # retain, sell_all, tax_budget, gradual, loss_only
    exit_review_dates: tuple[str, ...] | None = None  # None uses announced deposit dates
    exit_grace_days: int = 0
    exit_fraction: float = 0.25  # fraction of remaining units at each gradual review
    exit_annual_tax_budget_eur: float = 0.0


@dataclass
class Lot:
    lot_id: int
    security_id: str
    acquired: pd.Timestamp
    units: float
    basis_eur: float
    lineage: str


@dataclass
class BacktestResult:
    summary: dict
    transactions: pd.DataFrame
    daily: pd.DataFrame
    yearly_tax: pd.DataFrame
    lots: pd.DataFrame


def _dates(frame, columns):
    for column in columns:
        frame[column] = pd.to_datetime(frame[column]).dt.normalize()
        if frame[column].isna().any():
            raise DataIntegrityError(f"Missing {column}")


def _require(frame, columns, name):
    missing = set(columns) - set(frame.columns)
    if missing:
        raise DataIntegrityError(f"{name} missing columns: {sorted(missing)}")


def _number(value, name, *, positive=False):
    value = float(value)
    if not isfinite(value) or value < 0 or (positive and value == 0):
        raise DataIntegrityError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")
    return value


def scheduled_contributions(config: BacktestConfig) -> list[pd.Timestamp]:
    """Deterministic announced dates; do not infer month ends from future prices.

    Pass explicit exchange month ends to match a benchmark's exchange calendar.
    Otherwise use each month's last weekday, executing on the first session on
    or after it. The final valuation month is excluded (192 deposits by default).
    """
    start, end = pd.Timestamp(config.start), pd.Timestamp(config.end)
    if config.contribution_dates is not None:
        result = [pd.Timestamp(d).normalize() for d in config.contribution_dates]
        if len(result) != len(set(result)):
            raise ValueError("Duplicate contribution dates")
        if any(d < start or d > end for d in result):
            raise ValueError("Contribution date outside configured interval")
        return sorted(result)
    result = []
    for month in pd.period_range(start.to_period("M"), end.to_period("M"), freq="M")[:-1]:
        d = month.end_time.normalize()
        while d.weekday() >= 5:
            d -= pd.Timedelta(days=1)
        result.append(max(d, start))
    return result


def run_backtest(prices: pd.DataFrame, target_weights: pd.DataFrame,
                 config: BacktestConfig | None = None,
                 events: pd.DataFrame | None = None,
                 metadata: pd.DataFrame | None = None,
                 membership: pd.DataFrame | None = None) -> BacktestResult:
    """Run a portfolio; every execution and tax settlement is returned in ledgers.

    prices: date, security_id, price_eur; optional dividend_eur (gross/share),
      unresolved_action (boolean). A NaN price may carry a dividend but cannot
      support a trade. Fresh quotes are required for all discretionary trades.
    target_weights: effective_date, available_date, security_id, weight. Each
      complete snapshot's nonnegative weights must sum to 1. A zero weight is
      permitted. Snapshots on a date are known only after that date's close.
    metadata: security_id, optional share_class and currency (default USD),
      dividend_withholding (default config). Legal share_class must persist
      across ticker changes to enforce the matching/repurchase restrictions.
    events: date, security_id, event_type. split needs ratio; cash_merger needs
      cash_eur_per_share; stock_exchange needs successor_id, ratio, tax_treatment
      'rollover'; spinoff additionally needs basis_fraction (allocated to child).
      mixed_merger needs successor_id, ratio, cash_eur_per_share and
      stock_value_eur_per_old_share; tax_treatment='rollover'. capital_distribution
      needs cash_eur_per_share and remaining_value_eur_per_share. The cash basis
      uses cash/(cash+retained value), before costs. Zero cash merger proceeds
      are allowed ONLY with explicit documented event.
    membership: optional effective_date, security_id, is_member updates. Explicit
      deletions bar new buys even if a fund weight snapshot still contains them.
      Updates are assumed public by the effective date; optional available_date
      delays their use until strictly after publication. A new constituent with
      no known weight receives no invented weight. Existing holdings are kept
      under the default retain policy. Unknown status never authorizes an exit.
    exit_policy: sell_all closes departed holdings; gradual closes exit_fraction
      of remaining units using FIFO; loss_only closes positions at any strictly
      negative aggregate euro PnL after fees; tax_budget closes whole positions
      ordered by unrealized gain/basis, ascending. The latter charges each sale's
      positive marginal current-year CGT against an annual cap, using only losses
      and exemption known so far. Later losses never refund the used policy cap.
      Announced review dates execute on the first observation on/after the date,
      after ordinary TLH and before reinvestment. All require fresh tradable quotes
      and at least 29 days since the last same-class purchase. Grace begins when
      departure is first observed, resets on reentry, and follows an already-
      departed position through stock/mixed exchanges. Unknown spinoffs stay held.
    harvest_review_dates: explicitly announced dates replace the ordinary TLH
      cadence; execution uses the first observed session on/after each date.
      harvest_cost_multiple requires potential loss relief (loss times CGT rate)
      to exceed that multiple of estimated round-trip costs. It does not book
      relief as cash or assume the loss will ultimately be usable.
      harvest_lot_mode='fifo_prefix' can instead sell a leading run of FIFO lots
      whose individual net gains are nonpositive, stopping before the first
      profitable lot. Thresholds and estimated costs use that prefix only.
      It never skips profitable old lots to choose newer losing acquisitions.
      'position_or_fifo_prefix' retains every qualifying whole-position loss
      sale, using the eligible FIFO prefix only if the whole position fails
      the configured loss thresholds or cost hurdle.
    gain_harvest: after TLH and exit reviews, sell positive FIFO prefixes until
      gains minus current and brought-forward losses reaches the exemption.
      There is no assumption about subsequent losses, which can erase earlier
      exemption use. Known departed holdings rank before current overweights;
      efficient ranking instead uses gain per euro of gross proceeds. Unknown
      membership never authorizes a gain sale. Same-security replacement is
      restricted to current known targets and prefixes without a losing lot;
      it spends only sale proceeds and records a new acquisition basis. All
      candidates require fresh tradable quotes and no same-class acquisition
      within the preceding 29 days. The alternative underweight route blocks
      same-class purchases for 29 days even where every sold lot was profitable.
      Hybrid reinvestment uses the underweight route for departed holdings and
      immediate replacement for known current targets, with the same lot guards.
      gain_harvest_exemption_increments_eur sums increases at sale time; it is
      NOT final annual exemption use or an estimate of tax alpha. The yearly
      settlements and cgt_exemption_used_total_eur report actual modelled use.
    Cash dividends accumulate until a scheduled contribution date by default.
      Cash-merger and harvest proceeds can be reinvested on the disposal date.
    """
    c = config or BacktestConfig()
    start, end = pd.Timestamp(c.start).normalize(), pd.Timestamp(c.end).normalize()
    if start > end or c.reentry_days < 29 or c.max_stale_sessions < 0:
        raise ValueError("Invalid dates, reentry window, or quote-staleness limit")
    if c.harvest_frequency not in ("contribution_dates", "daily"):
        raise ValueError("Unknown harvest frequency")
    if c.investment_frequency not in ("contribution_dates", "daily"):
        raise ValueError("Unknown investment frequency")
    if c.missing_target_policy not in ("error", "reserve_cash"):
        raise ValueError("Unknown missing target policy")
    if c.exit_policy not in ("retain", "sell_all", "tax_budget", "gradual", "loss_only"):
        raise ValueError("Unknown exit policy")
    if c.gain_harvest_scope not in ("all", "departed"):
        raise ValueError("Unknown gain harvest scope")
    if c.harvest_lot_mode not in ("position", "fifo_prefix", "position_or_fifo_prefix"):
        raise ValueError("Unknown harvest lot mode")
    if c.gain_harvest_reinvest not in ("underweights", "same_security", "hybrid"):
        raise ValueError("Unknown gain harvest reinvestment")
    if c.gain_harvest_ranking not in ("overweight", "efficient"):
        raise ValueError("Unknown gain harvest ranking")
    if c.exit_grace_days < 0 or not isinstance(c.exit_grace_days, int):
        raise ValueError("Exit grace days must be a nonnegative integer")
    if not 0 < c.exit_fraction <= 1:
        raise ValueError("Exit fraction must be in (0, 1]")
    for name in ("monthly_contribution", "minimum_order_eur", "harvest_loss_fraction", "harvest_min_loss_eur",
                 "cgt_rate", "cgt_exemption", "dividend_income_tax", "dividend_usc",
                 "dividend_prsi", "foreign_dividend_withholding", "fx_fee", "half_spread",
                 "exit_annual_tax_budget_eur", "harvest_cost_multiple", "gain_harvest_min_eur"):
        _number(getattr(c, name), name)
    if c.fx_fee + c.half_spread >= 1 or c.cgt_rate > 1:
        raise ValueError("Invalid transaction costs or CGT rate")

    p = prices.copy()
    w = target_weights.copy()
    _require(p, ("date", "security_id", "price_eur"), "prices")
    _require(w, ("effective_date", "available_date", "security_id", "weight"), "weights")
    _dates(p, ("date",))
    _dates(w, ("effective_date", "available_date"))
    p["security_id"] = p.security_id.astype(str)
    w["security_id"] = w.security_id.astype(str)
    p = p.loc[p.date.between(start, end)].sort_values(["date", "security_id"])
    if p.empty:
        raise DataIntegrityError("No observations in requested interval")
    if p.duplicated(["date", "security_id"]).any():
        raise DataIntegrityError("Duplicate security/date price")
    if w.duplicated(["effective_date", "available_date", "security_id"]).any():
        raise DataIntegrityError("Duplicate security within weight snapshot")
    p["dividend_eur"] = p.get("dividend_eur", 0.0)
    p["dividend_eur"] = p.dividend_eur.fillna(0.0).map(lambda x: _number(x, "dividend_eur"))
    for price in p.price_eur.dropna():
        _number(price, "price_eur", positive=True)
    w["weight"] = w.weight.map(lambda x: _number(x, "weight"))
    snapshots = []
    for (effective, available), snapshot in w.groupby(["effective_date", "available_date"]):
        if abs(snapshot.weight.sum() - 1.0) > 1e-8:
            raise DataIntegrityError(f"Weights must sum to one: {effective}, {available}")
        snapshots.append((effective, available, dict(zip(snapshot.security_id, snapshot.weight))))
    snapshots.sort(key=lambda x: (x[0], x[1]))

    meta = {}
    if metadata is not None:
        m = metadata.copy()
        _require(m, ("security_id",), "metadata")
        if m.security_id.astype(str).duplicated().any():
            raise DataIntegrityError("Duplicate security metadata")
        meta = {str(row["security_id"]): row for row in m.to_dict("records")}

    def field(security, name, default):
        value = meta.get(security, {}).get(name, default)
        return default if pd.isna(value) else value

    def share_class(security):
        return str(field(security, "share_class", security))

    def cost_rate(security):
        return c.half_spread + (c.fx_fee if str(field(security, "currency", "USD")).upper() != "EUR" else 0.0)

    event_rows = []
    if events is not None and not events.empty:
        e = events.copy()
        _require(e, ("date", "security_id", "event_type"), "events")
        _dates(e, ("date",))
        e["security_id"] = e.security_id.astype(str)
        event_rows = e.loc[e.date.between(start, end)].sort_values("date", kind="stable").to_dict("records")

    membership_rows = []
    if membership is not None:
        member = membership.copy()
        _require(member, ("effective_date", "security_id", "is_member"), "membership")
        _dates(member, ("effective_date",))
        if "available_date" in member:
            _dates(member, ("available_date",))
        member["security_id"] = member.security_id.astype(str)
        if member.duplicated(["effective_date", "security_id"]).any():
            raise DataIntegrityError("Duplicate membership update")
        for row in member.sort_values("effective_date", kind="stable").to_dict("records"):
            raw = row["is_member"]
            if isinstance(raw, str):
                raw = {"true": True, "false": False, "1": True, "0": False}.get(raw.lower())
            if raw is None or pd.isna(raw) or raw not in (True, False, 0, 1):
                raise DataIntegrityError("is_member must be boolean")
            row["is_member"] = bool(raw)
            membership_rows.append(row)

    dates = pd.DatetimeIndex(p.date.unique()).sort_values()
    if dates[0] != start:
        raise DataIntegrityError("Exact first valuation date is required; refusing a shortened history")
    if c.liquidate_at_end and dates[-1] != end:
        raise DataIntegrityError("Exact final valuation date is required for liquidation")
    deposits = scheduled_contributions(c)
    amounts = c.contribution_amounts
    if amounts is None:
        amounts = (c.monthly_contribution,) * len(deposits)
    if len(amounts) != len(deposits):
        raise ValueError("Contribution amounts must match the scheduled contribution dates")
    amounts = tuple(_number(amount, f"contribution_amounts[{i}]")
                    for i, amount in enumerate(amounts))
    reviews = deposits if c.exit_review_dates is None else [pd.Timestamp(d).normalize() for d in c.exit_review_dates]
    if any(pd.isna(d) or d < start or d > end for d in reviews) or len(reviews) != len(set(reviews)):
        raise ValueError("Exit review dates must be unique dates in the configured interval")
    reviews = sorted(reviews)
    def review_schedule(values, label):
        result = deposits if values is None else [pd.Timestamp(d).normalize() for d in values]
        if any(pd.isna(d) or d < start or d > end for d in result) or len(result) != len(set(result)):
            raise ValueError(f"{label} review dates must be unique dates in the configured interval")
        return sorted(result)

    loss_reviews = review_schedule(c.harvest_review_dates, "Loss") if c.harvest_review_dates is not None else []
    gain_reviews = review_schedule(c.gain_review_dates, "Gain")
    loss_review_index = gain_review_index = 0
    deposit_index = event_index = review_index = 0
    lots: list[Lot] = []
    open_positions: dict[str, list[Lot]] = {}
    contingent_rights: dict[str, float] = {}
    transactions, daily, taxes = [], [], []
    quote, quote_session, quote_tradable = {}, {}, {}
    last_buy, blocked_until = {}, {}
    inherited_outside, outside_since = set(), {}
    policy_tax_spent = total_policy_tax_spent = 0.0
    policy_review_count = policy_sale_count = 0
    policy_gross_proceeds = policy_net_proceeds = policy_realized_pnl = 0.0
    policy_skips = {}
    gain_review_count = gain_sale_count = 0
    gain_gross_proceeds = gain_net_proceeds = gain_realized_pnl = gain_exemption_increment = 0.0
    gain_skips = {}
    cash = reserve = carried_loss = 0.0
    gains = losses = total_cgt = total_dividend_tax = total_cost = 0.0
    total_contributions = contribution_count = lot_serial = 0
    current_year = dates[0].year
    annual_dividends = annual_dividend_tax = 0.0
    total_gross_dividends = 0.0
    pre_liquidation_value = final_tax = 0.0
    member_state, known_targets = {}, {}

    def membership_status(security):
        if security in member_state:
            return "inside" if member_state[security] else "outside"
        if known_targets.get(security, 0.) > 0:
            return "inside"
        return "outside" if security in inherited_outside else "unknown"

    def log(day, event, **kw):
        transactions.append(dict(date=day, event=event, **kw))

    def held(security):
        return open_positions.get(security, [])

    def securities():
        return sorted(s for s, position in open_positions.items() if position)

    def check_class_identity():
        seen = {}
        for security in securities():
            klass = share_class(security)
            if klass in seen:
                raise DataIntegrityError(f"Overlapping security IDs for one legal share class: {seen[klass]}, {security}; consolidate identity before replay")
            seen[klass] = security

    def balance(security):
        return sum(lot.units for lot in held(security))

    def value():
        return cash + sum(balance(s) * quote[s] for s in securities())

    def liability():
        return settle_cgt_year(gains, losses, carried_loss, c.cgt_rate, c.cgt_exemption)

    def update_reserve():
        nonlocal reserve
        reserve = liability().tax_due
        if reserve > cash + 1e-7:
            raise DataIntegrityError("Insufficient cash for CGT reserve; refusing a winner sale")

    def settle_year(day, *, final=False):
        nonlocal cash, reserve, carried_loss, gains, losses, total_cgt
        nonlocal annual_dividends, annual_dividend_tax
        settlement = liability()
        if cash + 1e-7 < settlement.tax_due:
            raise DataIntegrityError("Insufficient cash to pay CGT; refusing a winner sale")
        taxes.append(dict(year=current_year, settled_on=day, final_settlement=final,
                          gains_eur=gains, losses_eur=losses,
                          brought_forward_loss_eur=carried_loss,
                          gross_dividends_eur=annual_dividends,
                          dividend_tax_eur=annual_dividend_tax, **asdict(settlement)))
        cash -= settlement.tax_due
        total_cgt += settlement.tax_due
        log(day, "cgt_settlement", tax_year=current_year, tax_eur=settlement.tax_due,
            loss_carry_forward=settlement.loss_carry_forward)
        carried_loss = settlement.loss_carry_forward
        gains = losses = reserve = annual_dividends = annual_dividend_tax = 0.0
        return settlement.tax_due

    def disposal_parts(security, units=None):
        """Select ordinary FIFO lots; a partial sale keeps the remaining basis."""
        position = held(security)
        available_units = sum(l.units for l in position)
        requested = available_units if units is None else _number(units, "disposal units", positive=True)
        if requested > available_units + 1e-9:
            raise ValueError("Cannot dispose of more units than held")
        remaining = min(requested, available_units)
        # Preserve legacy all-lot traversal and arithmetic for the retain baseline.
        ordered = position if units is None else sorted(position, key=lambda lot: (lot.acquired, lot.lot_id))
        result = []
        for lot in ordered:
            if remaining <= 1e-12:
                break
            sold_units = min(lot.units, remaining)
            sold_basis = lot.basis_eur if sold_units == lot.units else lot.basis_eur * sold_units / lot.units
            result.append((lot, sold_units, sold_basis))
            remaining -= sold_units
        return result

    def gain_headroom():
        # Irish carried losses must be used before the annual exemption. There
        # is no value assigned to losses which have not yet been realised.
        return max(0., c.cgt_exemption + losses + carried_loss - gains)

    def immediate_repurchase(security):
        return (c.gain_harvest_reinvest == "same_security" or
                (c.gain_harvest_reinvest == "hybrid" and membership_status(security) == "inside"))

    def gain_sale_units(security, headroom):
        """First FIFO prefix reaching headroom, or its largest positive prefix.

        Net gains are piecewise linear in units; treating the whole position's
        average cost as FIFO would over/undershoot the exemption. Immediate
        replacement may consume only a leading run of non-losing lots.
        """
        net_unit = quote[security] * (1-cost_rate(security))
        cumulative_units = cumulative_gain = best_units = best_gain = 0.0
        for lot in sorted(held(security), key=lambda lot: (lot.acquired, lot.lot_id)):
            unit_gain = net_unit - lot.basis_eur / lot.units
            if immediate_repurchase(security) and unit_gain < 0:
                break
            end_gain = cumulative_gain + lot.units * unit_gain
            if unit_gain > 0 and end_gain >= headroom:
                best_units = cumulative_units + (headroom-cumulative_gain) / unit_gain
                break
            cumulative_units += lot.units
            cumulative_gain = end_gain
            if cumulative_gain > best_gain:
                best_gain, best_units = cumulative_gain, cumulative_units
        if not c.fractional_shares:
            best_units = float(floor(best_units+1e-12))
        return best_units

    def sale_pnl(security, units):
        return sum(n*quote[security]*(1-cost_rate(security))-b
                   for _, n, b in disposal_parts(security, units))

    def dispose(day, security, price, reason, *, apply_cost=True, units=None):
        nonlocal cash, gains, losses, total_cost
        position = held(security)
        if not position:
            return
        parts = disposal_parts(security, units)
        sold_units = sum(n for _, n, _ in parts)
        basis = sum(b for _, _, b in parts)
        gross = sold_units * price
        fees = gross * cost_rate(security) if apply_cost else 0.0
        net = gross - fees
        pnl = net - basis
        if reason == "harvest" and pnl >= -1e-9:
            raise AssertionError("Voluntary profitable disposal prohibited")
        has_lot_loss = False
        for lot, part_units, part_basis in parts:
            allocated_net = net * part_units / sold_units
            lot_pnl = allocated_net - part_basis
            gains += max(lot_pnl, 0.0)
            losses += max(-lot_pnl, 0.0)
            has_lot_loss = has_lot_loss or lot_pnl < 0
            log(day, "lot_disposal", security_id=security, reason=reason,
                lot_id=lot.lot_id, acquisition=lot.acquired, units=part_units,
                basis_eur=part_basis, net_proceeds_eur=allocated_net,
                realized_gain_eur=lot_pnl, lineage=lot.lineage)
            lot.units -= part_units
            lot.basis_eur -= part_basis
        cash += net
        total_cost += fees
        log(day, "sell", security_id=security, reason=reason, units=sold_units,
            price_eur=price, gross_proceeds_eur=gross, fees_eur=fees,
            net_proceeds_eur=net, basis_eur=basis, realized_gain_eur=pnl)
        # Prevent restricted replacement losses for forced disposals too.
        if has_lot_loss:
            blocked_until[share_class(security)] = day + pd.Timedelta(days=c.reentry_days)
        open_positions[security] = [lot for lot in position if lot.units > 1e-12]
        return dict(gross=gross, net=net, pnl=pnl, units=sold_units, basis=basis)

    def inherit_restrictions(day, security, successor, *, inherit_departure=True):
        """Rollover receipts retain purchase history and existing loss embargoes."""
        parent_class, successor_class = share_class(security), share_class(successor)
        previous = last_buy.get(parent_class)
        if previous is not None:
            last_buy[successor_class] = max(previous, last_buy.get(successor_class, previous))
        parent_block = blocked_until.get(parent_class)
        if parent_block is not None:
            blocked_until[successor_class] = max(parent_block, blocked_until.get(successor_class, parent_block))
        # Only earlier observed outside status transfers. Same-day mechanical
        # termination rows do not prove a received child is outside the index.
        if inherit_departure and security in outside_since and outside_since[security] < day and membership_status(security) != "inside":
            inherited_outside.add(successor)
            if membership_status(successor) != "inside":
                outside_since[successor] = min(outside_since[security], outside_since.get(successor, day))
            log(day, "inherited_outside_status", security_id=successor,
                predecessor_id=security, predecessor_outside_since=outside_since[security],
                assumption="Continuation of an already-departed holding; explicit membership overrides")
        if day < blocked_until.get(successor_class, pd.Timestamp.min):
            log(day, "automatic_receipt_during_loss_block", security_id=successor,
                predecessor_id=security, blocked_until=blocked_until[successor_class],
                assumption="Corporate-action receipt; audit tax matching separately from voluntary repurchases")

    def apply_event(day, event):
        nonlocal lot_serial, cash, gains, losses, total_cost, total_dividend_tax
        nonlocal annual_dividends, annual_dividend_tax, total_gross_dividends
        security, kind = event["security_id"], event["event_type"]
        if kind not in ("split", "cash_merger", "stock_exchange", "spinoff",
                        "mixed_merger", "capital_distribution", "cash_dividend",
                        "contingent_right", "contingent_cash"):
            raise DataIntegrityError(f"Unresolved/unsupported action: {security} {kind}")
        position = held(security)
        if kind == "contingent_right":
            right_id = event.get("successor_id")
            if not isinstance(right_id, str) or not right_id:
                raise DataIntegrityError("Contingent right needs successor_id")
            units = balance(security)*_number(event.get("ratio", 1.), "rights ratio", positive=True)
            contingent_rights[right_id] = contingent_rights.get(right_id, 0.) + units
            log(day, "contingent_entitlement", security_id=security, right_id=right_id,
                units=units, assigned_value_eur=0., assigned_basis_eur=0.,
                assumption="Unquoted right zero mark/basis until actual payment; provisional allocation")
            return
        if kind == "contingent_cash":
            units = contingent_rights.get(security, 0.)
            amount = _number(event.get("cash_eur_per_share", float("nan")), "rights payment")
            gross = units*amount
            fees = gross*cost_rate(security)
            cash += gross-fees
            gains += gross-fees
            total_cost += fees
            contingent_rights[security] = 0.
            log(day, "contingent_payment", security_id=security, units=units,
                gross_proceeds_eur=gross, fees_eur=fees, realized_gain_eur=gross-fees,
                source=event.get("source", ""))
            return
        if not position and kind != "split":
            log(day, "corporate_action", security_id=security, action=kind,
                effective_date=event["date"], affected_lots=0, source=event.get("source", ""))
            return
        if kind == "cash_merger":
            amount = _number(event.get("cash_eur_per_share", float("nan")), "merger consideration")
            dispose(day, security, amount, "cash_merger", apply_cost=True)
        elif kind == "cash_dividend":
            amount = _number(event.get("cash_eur_per_share", float("nan")), "cash dividend")
            gross = balance(security)*amount
            withholding = _number(field(security, "dividend_withholding", c.foreign_dividend_withholding), "withholding")
            tax = settle_us_dividend(gross, c.dividend_income_tax, c.dividend_usc,
                                    c.dividend_prsi, withholding)
            cash += tax.net_to_reinvest
            total_dividend_tax += tax.total_tax
            total_gross_dividends += gross
            annual_dividends += gross
            annual_dividend_tax += tax.total_tax
            log(day, "dividend", security_id=security, gross_eur=gross,
                withholding_eur=tax.foreign_withholding, irish_top_up_eur=tax.irish_tax_top_up,
                tax_eur=tax.total_tax, net_cash_eur=tax.net_to_reinvest, source=event.get("source", ""))
        elif kind in ("mixed_merger", "capital_distribution"):
            amount = _number(event.get("cash_eur_per_share", float("nan")), "cash consideration")
            if kind == "mixed_merger":
                if event.get("tax_treatment") != "rollover":
                    raise DataIntegrityError(f"Explicit rollover classification required: {security}")
                successor = event.get("successor_id")
                if not isinstance(successor, str) or not successor or successor == security:
                    raise DataIntegrityError("Mixed merger requires distinct successor_id")
                ratio = _number(event.get("ratio", float("nan")), "exchange ratio", positive=True)
                retained = _number(event.get("stock_value_eur_per_old_share", float("nan")),
                                   "share consideration value", positive=True)
            else:
                retained = _number(event.get("remaining_value_eur_per_share", float("nan")),
                                   "remaining holding value", positive=True)
            fraction = amount / (amount + retained)
            for lot in position:
                gross = lot.units * amount
                fee = gross * cost_rate(security)
                cash_basis = lot.basis_eur * fraction
                pnl = gross - fee - cash_basis
                gains += max(pnl, 0.)
                losses += max(-pnl, 0.)
                cash += gross - fee
                total_cost += fee
                log(day, "lot_disposal", security_id=security, reason=kind,
                    lot_id=lot.lot_id, acquisition=lot.acquired,
                    units=lot.units * fraction, basis_eur=cash_basis,
                    net_proceeds_eur=gross-fee, realized_gain_eur=pnl,
                    lineage=lot.lineage)
                retained_basis = lot.basis_eur - cash_basis
                if kind == "mixed_merger":
                    lot_serial += 1
                    child = Lot(lot_serial, successor, lot.acquired, lot.units*ratio,
                                retained_basis, lot.lineage+f"|mixed_merger:{day.date()}:{successor}")
                    lots.append(child)
                    open_positions.setdefault(successor, []).append(child)
                    lot.units = lot.basis_eur = 0.
                else:
                    lot.basis_eur = retained_basis
            if kind == "mixed_merger":
                open_positions[security] = []
                inherit_restrictions(day, security, successor)
        else:
            ratio = _number(event.get("ratio", float("nan")), "action ratio", positive=True)
            if kind == "split":
                for lot in position:
                    lot.units *= ratio
                    lot.lineage += f"|split:{event['date'].date()}:{ratio}"
                if security in quote:
                    quote[security] /= ratio
            else:
                if event.get("tax_treatment") != "rollover":
                    raise DataIntegrityError(f"Explicit audited rollover treatment required: {security}")
                successor = event.get("successor_id")
                if not isinstance(successor, str) or not successor or successor == security:
                    raise DataIntegrityError("Action requires a distinct successor_id")
                allocation = (1.0 if kind == "stock_exchange" else
                              _number(event.get("basis_fraction", float("nan")), "child basis fraction"))
                if allocation > 1.0:
                    raise DataIntegrityError("Child basis fraction exceeds one")
                for lot in position:
                    lot_serial += 1
                    child = Lot(lot_serial, successor, lot.acquired, lot.units * ratio,
                                lot.basis_eur * allocation,
                                lot.lineage + f"|{kind}:{event['date'].date()}:{successor}")
                    lots.append(child)
                    open_positions.setdefault(successor, []).append(child)
                    lot.basis_eur *= 1.0 - allocation
                    if kind == "stock_exchange":
                        lot.units = 0.0
                if kind == "stock_exchange":
                    open_positions[security] = []
                inherit_restrictions(day, security, successor, inherit_departure=kind == "stock_exchange")
        log(day, "corporate_action", security_id=security, action=kind,
            effective_date=event["date"], affected_lots=len(position),
            source=event.get("source", "caller-supplied audited event"))

    for session, (day, rows) in enumerate(p.groupby("date", sort=True)):
        disposal_today = False
        available_snapshots = [s for s in snapshots if s[0] <= day and s[1] < day]
        known_targets = available_snapshots[-1][2] if available_snapshots else {}
        member_state = {}
        for update in membership_rows:
            if update["effective_date"] <= day and ("available_date" not in update or update["available_date"] < day):
                member_state[update["security_id"]] = update["is_member"]
        if day.year != current_year:
            settle_year(day)
            current_year = day.year
            policy_tax_spent = 0.0
        while event_index < len(event_rows) and event_rows[event_index]["date"] <= day:
            event = event_rows[event_index]
            disposal_today = disposal_today or (event["event_type"] in ("cash_merger", "mixed_merger", "capital_distribution") and bool(held(event["security_id"]))) or (event["event_type"] == "contingent_cash" and contingent_rights.get(event["security_id"], 0.) > 0)
            try:
                apply_event(day, event_rows[event_index])
            except DataIntegrityError as exc:
                raise DataIntegrityError(f"{event['security_id']} {day.date()} {event['event_type']}: {exc}") from exc
            event_index += 1
        check_class_identity()
        for row in rows.to_dict("records"):
            security = row["security_id"]
            flag = row.get("unresolved_action", False)
            if pd.notna(flag) and bool(flag):
                raise DataIntegrityError(f"Unresolved corporate action: {security} {day.date()}")
            if pd.notna(row["price_eur"]):
                quote[security] = float(row["price_eur"])
                quote_session[security] = session
                quote_tradable[security] = bool(row.get("tradable", True))
            gross_dividend = balance(security) * row["dividend_eur"]
            if gross_dividend:
                withholding = _number(field(security, "dividend_withholding", c.foreign_dividend_withholding), "withholding")
                tax = settle_us_dividend(gross_dividend, c.dividend_income_tax,
                                        c.dividend_usc, c.dividend_prsi, withholding)
                if tax.net_to_reinvest < 0:
                    raise ValueError("Dividend tax exceeds gross dividend")
                cash += tax.net_to_reinvest
                total_dividend_tax += tax.total_tax
                annual_dividends += gross_dividend
                total_gross_dividends += gross_dividend
                annual_dividend_tax += tax.total_tax
                log(day, "dividend", security_id=security, gross_eur=gross_dividend,
                    withholding_eur=tax.foreign_withholding,
                    irish_top_up_eur=tax.irish_tax_top_up,
                    tax_eur=tax.total_tax, net_cash_eur=tax.net_to_reinvest)
        for security in securities():
            stale_limit = int(field(security, "max_stale_sessions", c.max_stale_sessions))
            if security not in quote or session - quote_session[security] > stale_limit:
                raise DataIntegrityError(f"Missing/stale held price: {security} {day.date()}; explicit action required")
        for security in list(outside_since):
            if not held(security) or membership_status(security) == "inside":
                del outside_since[security]
        for security in securities():
            if membership_status(security) == "outside":
                outside_since.setdefault(security, day)
            elif membership_status(security) == "inside":
                inherited_outside.discard(security)

        contributed_today = False
        while deposit_index < len(deposits) and deposits[deposit_index] <= day:
            amount = amounts[deposit_index]
            cash += amount
            total_contributions += amount
            contribution_count += 1
            contributed_today = True
            log(day, "contribution", scheduled_date=deposits[deposit_index], cash_eur=amount)
            deposit_index += 1

        terminal = c.liquidate_at_end and day == end
        loss_review_today = False
        while loss_review_index < len(loss_reviews) and loss_reviews[loss_review_index] <= day:
            loss_review_today = True
            loss_review_index += 1
        harvest_today = (loss_review_today if c.harvest_review_dates is not None else
                         contributed_today or c.harvest_frequency == "daily")
        if c.harvest and not terminal and harvest_today:
            for security in securities():
                klass = share_class(security)
                previous_buy = last_buy.get(klass)
                if previous_buy is not None and (day - previous_buy).days < c.reentry_days:
                    continue
                if quote_session.get(security) != session or not quote_tradable.get(security, True):
                    continue
                position = held(security)
                harvest_units = None
                use_prefix = c.harvest_lot_mode == "fifo_prefix"
                if c.harvest_lot_mode == "position_or_fifo_prefix":
                    whole_basis = sum(l.basis_eur for l in position)
                    whole_gross = balance(security)*quote[security]
                    whole_loss = whole_basis-whole_gross*(1-cost_rate(security))
                    whole_eligible = (whole_loss > 1e-9 and
                                      whole_loss+1e-9 >= max(c.harvest_min_loss_eur, whole_basis*c.harvest_loss_fraction) and
                                      whole_loss*c.cgt_rate+1e-9 >= c.harvest_cost_multiple*whole_gross*2*cost_rate(security))
                    use_prefix = not whole_eligible
                if use_prefix:
                    harvest_units = 0.
                    for lot in sorted(position, key=lambda lot: (lot.acquired, lot.lot_id)):
                        if lot.units*quote[security]*(1-cost_rate(security)) > lot.basis_eur:
                            break
                        harvest_units += lot.units
                    if not c.fractional_shares and harvest_units < balance(security)-1e-12:
                        harvest_units = float(floor(harvest_units+1e-12))
                    if harvest_units <= 1e-12:
                        continue
                units = balance(security) if harvest_units is None else harvest_units
                basis = (sum(l.basis_eur for l in position) if harvest_units is None else
                         sum(b for _, _, b in disposal_parts(security, harvest_units)))
                net = units * quote[security] * (1.0 - cost_rate(security))
                loss = basis - net
                if loss > 1e-9 and loss + 1e-9 >= max(c.harvest_min_loss_eur, basis * c.harvest_loss_fraction):
                    if harvest_units is not None and units*quote[security]+1e-9 < c.minimum_order_eur:
                        continue
                    round_trip_cost = units*quote[security]*2*cost_rate(security)
                    if loss*c.cgt_rate + 1e-9 < c.harvest_cost_multiple*round_trip_cost:
                        log(day, "harvest_skipped", security_id=security, skip_reason="cost_hurdle",
                            loss_eur=loss, potential_loss_relief_eur=loss*c.cgt_rate,
                            estimated_round_trip_cost_eur=round_trip_cost)
                        continue
                    dispose(day, security, quote[security], "harvest", units=harvest_units)
                    disposal_today = True

        while review_index < len(reviews) and reviews[review_index] <= day:
            scheduled_review = reviews[review_index]
            review_index += 1
            if c.exit_policy == "retain":
                continue
            if terminal:
                log(day, "policy_review_skipped", scheduled_date=scheduled_review,
                    policy=c.exit_policy, skip_reason="terminal_liquidation")
                continue
            policy_review_count += 1
            log(day, "policy_review", scheduled_date=scheduled_review, policy=c.exit_policy,
                annual_tax_budget_eur=c.exit_annual_tax_budget_eur,
                annual_positive_incremental_cgt_eur=policy_tax_spent)
            candidates = [s for s in securities() if membership_status(s) == "outside"]

            def gain_fraction(security):
                basis = sum(l.basis_eur for l in held(security))
                net = balance(security)*quote[security]*(1-cost_rate(security))
                return (net-basis)/basis if basis > 0 else float("inf")

            if c.exit_policy == "tax_budget":
                candidates.sort(key=lambda s: (gain_fraction(s), s))
            for security in candidates:
                since = outside_since[security]
                age = (day-since).days
                previous_buy = last_buy.get(share_class(security))
                skip = None
                if age < c.exit_grace_days:
                    skip = "grace_period"
                elif previous_buy is not None and (day-previous_buy).days < c.reentry_days:
                    skip = "recent_class_purchase"
                elif quote_session.get(security) != session or not quote_tradable.get(security, True):
                    skip = "no_fresh_tradable_quote"
                sold_units = balance(security)
                if c.exit_policy == "gradual":
                    sold_units *= c.exit_fraction
                    if not c.fractional_shares:
                        sold_units = float(floor(sold_units + 1e-12))
                    if sold_units <= 1e-12:
                        skip = skip or "fraction_below_one_share"
                    elif sold_units*quote[security]+1e-9 < c.minimum_order_eur:
                        skip = skip or "below_minimum_order"
                if skip:
                    policy_skips[skip] = policy_skips.get(skip, 0)+1
                    log(day, "policy_exit_skipped", security_id=security, policy=c.exit_policy,
                        scheduled_date=scheduled_review, outside_since=since,
                        outside_age_days=age, skip_reason=skip)
                    continue
                parts = disposal_parts(security, sold_units if c.exit_policy == "gradual" else None)
                sale_gains = sale_losses = 0.0
                for _, units, basis in parts:
                    pnl = units*quote[security]*(1-cost_rate(security))-basis
                    sale_gains += max(pnl, 0.)
                    sale_losses += max(-pnl, 0.)
                before_tax = liability().tax_due
                after_tax = settle_cgt_year(gains+sale_gains, losses+sale_losses,
                                            carried_loss, c.cgt_rate, c.cgt_exemption).tax_due
                increment = max(0., after_tax-before_tax)
                if c.exit_policy == "loss_only" and sale_losses-sale_gains <= 1e-9:
                    skip = "not_an_aggregate_loss"
                elif c.exit_policy == "tax_budget" and policy_tax_spent+increment > c.exit_annual_tax_budget_eur+1e-8:
                    skip = "annual_tax_budget"
                if skip:
                    policy_skips[skip] = policy_skips.get(skip, 0)+1
                    log(day, "policy_exit_skipped", security_id=security, policy=c.exit_policy,
                        scheduled_date=scheduled_review, outside_since=since,
                        outside_age_days=age, skip_reason=skip,
                        projected_incremental_cgt_eur=increment,
                        annual_positive_incremental_cgt_eur=policy_tax_spent)
                    continue
                sale = dispose(day, security, quote[security], "policy_exit",
                               units=sold_units if c.exit_policy == "gradual" else None)
                disposal_today = True
                policy_tax_spent += increment
                total_policy_tax_spent += increment
                policy_sale_count += 1
                policy_gross_proceeds += sale["gross"]
                policy_net_proceeds += sale["net"]
                policy_realized_pnl += sale["pnl"]
                log(day, "policy_exit", security_id=security, policy=c.exit_policy,
                    scheduled_date=scheduled_review, outside_since=since,
                    outside_age_days=age, units=sale["units"],
                    incremental_cgt_eur=increment,
                    annual_positive_incremental_cgt_eur=policy_tax_spent,
                    annual_tax_budget_eur=c.exit_annual_tax_budget_eur)

        while gain_review_index < len(gain_reviews) and gain_reviews[gain_review_index] <= day:
            scheduled_gain_review = gain_reviews[gain_review_index]
            gain_review_index += 1
            if not c.gain_harvest:
                continue
            if terminal:
                log(day, "gain_review_skipped", scheduled_date=scheduled_gain_review,
                    skip_reason="terminal_liquidation")
                continue
            gain_review_count += 1
            review_headroom = gain_headroom()
            review_exemption = liability().exemption_used
            log(day, "gain_review", scheduled_date=scheduled_gain_review,
                gain_headroom_eur=review_headroom, exemption_used_eur=review_exemption,
                carried_loss_eur=carried_loss, current_losses_eur=losses,
                scope=c.gain_harvest_scope, reinvest=c.gain_harvest_reinvest)
            candidates = []
            for security in securities():
                skip = None
                status = membership_status(security)
                previous_buy = last_buy.get(share_class(security))
                if status == "unknown":
                    skip = "unknown_membership"
                elif c.gain_harvest_scope == "departed" and status != "outside":
                    skip = "scope"
                elif immediate_repurchase(security) and (status != "inside" or known_targets.get(security, 0.) <= 0):
                    skip = "no_current_repurchase_target"
                elif previous_buy is not None and (day-previous_buy).days < c.reentry_days:
                    skip = "recent_class_purchase"
                elif day < blocked_until.get(share_class(security), pd.Timestamp.min):
                    skip = "class_repurchase_block"
                elif quote_session.get(security) != session or not quote_tradable.get(security, True):
                    skip = "no_fresh_tradable_quote"
                if skip:
                    gain_skips[skip] = gain_skips.get(skip, 0)+1
                    log(day, "gain_harvest_skipped", security_id=security,
                        scheduled_date=scheduled_gain_review, skip_reason=skip)
                    continue
                candidates.append(security)

            nav = value() - liability().tax_due

            def gain_rank(security):
                if c.gain_harvest_ranking == "efficient":
                    units = gain_sale_units(security, review_headroom) if review_headroom > 1e-9 else 0.
                    efficiency = sale_pnl(security, units)/(units*quote[security]) if units > 1e-12 else -float("inf")
                    return (-efficiency, security)
                overweight = balance(security)*quote[security] - known_targets.get(security, 0.)*nav
                return (membership_status(security) != "outside", -overweight, security)

            candidates.sort(key=gain_rank)
            for security in candidates:
                headroom = gain_headroom()
                if headroom <= 1e-8:
                    break
                units = gain_sale_units(security, headroom)
                pnl = sale_pnl(security, units) if units > 1e-12 else 0.
                skip = None
                if pnl <= 1e-9:
                    skip = "no_positive_fifo_prefix"
                elif pnl+1e-9 < c.gain_harvest_min_eur:
                    skip = "below_minimum_gain"
                elif units*quote[security]+1e-9 < c.minimum_order_eur:
                    skip = "below_minimum_order"
                elif immediate_repurchase(security) and units*quote[security]*(1-cost_rate(security))+1e-9 < c.minimum_order_eur:
                    skip = "replacement_below_minimum_order"
                elif immediate_repurchase(security) and not c.fractional_shares and units*(1-cost_rate(security))/(1+cost_rate(security)) < 1-1e-12:
                    skip = "replacement_below_one_share"
                if skip:
                    gain_skips[skip] = gain_skips.get(skip, 0)+1
                    log(day, "gain_harvest_skipped", security_id=security,
                        scheduled_date=scheduled_gain_review, skip_reason=skip)
                    continue
                before = liability()
                if immediate_repurchase(security):
                    if any(n*quote[security]*(1-cost_rate(security))-b < -1e-8
                           for _, n, b in disposal_parts(security, units)):
                        raise AssertionError("Immediate replacement cannot include a losing FIFO lot")
                sale = dispose(day, security, quote[security], "gain_harvest", units=units)
                after = liability()
                if sale["pnl"] <= 0 or after.tax_due > before.tax_due+1e-7:
                    raise AssertionError("Gain harvesting exceeded known tax-free headroom")
                gain_sale_count += 1
                gain_gross_proceeds += sale["gross"]
                gain_net_proceeds += sale["net"]
                gain_realized_pnl += sale["pnl"]
                gain_exemption_increment += after.exemption_used-before.exemption_used
                disposal_today = True
                log(day, "gain_harvest", security_id=security,
                    scheduled_date=scheduled_gain_review, units=sale["units"],
                    gain_headroom_before_eur=headroom, gain_headroom_after_eur=gain_headroom(),
                    exemption_used_before_eur=before.exemption_used,
                    exemption_used_after_eur=after.exemption_used,
                    incremental_cgt_eur=after.tax_due-before.tax_due,
                    realized_gain_eur=sale["pnl"],
                    reinvest="same_security" if immediate_repurchase(security) else "underweights")
                if immediate_repurchase(security):
                    unit_cost = quote[security]*(1+cost_rate(security))
                    replacement_units = sale["net"]/unit_cost
                    if not c.fractional_shares:
                        replacement_units = float(floor(replacement_units+1e-12))
                    if replacement_units > 1e-12:
                        outlay = replacement_units*unit_cost
                        fee = replacement_units*quote[security]*cost_rate(security)
                        cash -= outlay
                        total_cost += fee
                        lot_serial += 1
                        basis = outlay if c.acquisition_costs_in_basis else replacement_units*quote[security]
                        lot = Lot(lot_serial, security, day, replacement_units, basis,
                                  f"gain_repurchase:{day.date()}:{security}")
                        lots.append(lot)
                        open_positions.setdefault(security, []).append(lot)
                        last_buy[share_class(security)] = day
                        effective, available, _ = available_snapshots[-1]
                        log(day, "buy", security_id=security, reason="gain_repurchase",
                            units=replacement_units, price_eur=quote[security], basis_eur=basis,
                            cash_outlay_eur=outlay, fees_eur=fee, lot_id=lot_serial,
                            weight_effective_date=effective, weight_available_date=available)
                else:
                    blocked_until[share_class(security)] = day+pd.Timedelta(days=c.reentry_days)
            log(day, "gain_review_complete", scheduled_date=scheduled_gain_review,
                gain_headroom_eur=gain_headroom(), exemption_used_eur=liability().exemption_used,
                exemption_remaining_eur=c.cgt_exemption-liability().exemption_used)

        update_reserve()
        if terminal:
            pre_liquidation_value = value()
            for security in securities():
                if quote_session.get(security) != session or not quote_tradable.get(security, True):
                    raise DataIntegrityError(f"Fresh final liquidation price required: {security}")
                dispose(day, security, quote[security], "final_liquidation")
            final_tax = settle_year(day, final=True)
        elif (cash - reserve > 1e-8 and
              (contributed_today or c.investment_frequency == "daily" or
               (disposal_today and c.reinvest_after_disposal))):
            if not available_snapshots:
                raise DataIntegrityError(f"No previously available target snapshot on {day.date()}")
            effective, available, targets = available_snapshots[-1]
            investable_nav = value() - reserve
            deficits = {}
            cash_weight = targets.get(c.cash_target_security_id, 0.)
            for security, weight in sorted(targets.items()):
                if security == c.cash_target_security_id:
                    continue
                if weight <= 0 or not member_state.get(security, True):
                    continue
                if security not in quote:
                    if c.missing_target_policy == "error":
                        raise DataIntegrityError(f"No price for current target: {security} {day.date()}")
                    cash_weight += weight
                    log(day, "missing_target_cash", security_id=security, target_weight=weight)
                    continue
                if quote_session.get(security) != session or not quote_tradable.get(security, True):
                    if c.missing_target_policy == "reserve_cash":
                        cash_weight += max(0., weight - balance(security)*quote[security]/investable_nav)
                        log(day, "stale_target_cash", security_id=security, target_weight=weight)
                    continue
                if day < blocked_until.get(share_class(security), pd.Timestamp.min):
                    continue
                deficit = weight * investable_nav - balance(security) * quote[security]
                if deficit > 1e-9:
                    deficits[security] = deficit
            total_deficit = sum(deficits.values())
            data_cash_reserve = cash_weight * investable_nav
            budget = max(0., min(cash - reserve - data_cash_reserve, total_deficit))
            if cash_weight:
                log(day, "target_cash_reserve", target_weight=cash_weight,
                    required_cash_eur=data_cash_reserve, available_cash_eur=cash-reserve)
            for security, deficit in deficits.items():
                allocation = budget * deficit / total_deficit
                if allocation + 1e-9 < c.minimum_order_eur:
                    continue
                unit_cost = quote[security] * (1.0 + cost_rate(security))
                units = allocation / unit_cost
                if not c.fractional_shares:
                    units = float(floor(units + 1e-12))
                if units <= 1e-12:
                    continue
                outlay = units * unit_cost
                fee = units * quote[security] * cost_rate(security)
                cash -= outlay
                total_cost += fee
                lot_serial += 1
                basis = outlay if c.acquisition_costs_in_basis else units * quote[security]
                lot = Lot(lot_serial, security, day, units, basis,
                          f"purchase:{day.date()}:{security}")
                lots.append(lot)
                open_positions.setdefault(security, []).append(lot)
                check_class_identity()
                last_buy[share_class(security)] = day
                log(day, "buy", security_id=security, units=units, price_eur=quote[security],
                    basis_eur=basis, cash_outlay_eur=outlay, fees_eur=fee, lot_id=lot_serial,
                    weight_effective_date=effective, weight_available_date=available)

        if cash < -1e-7:
            raise AssertionError("Negative cash balance")
        exit_cost = sum(balance(s)*quote[s]*cost_rate(s) for s in securities())
        potential_gains, potential_losses = gains, losses
        for security in securities():
            for lot in held(security):
                pnl = lot.units*quote[security]*(1-cost_rate(security))-lot.basis_eur
                potential_gains += max(pnl, 0.)
                potential_losses += max(-pnl, 0.)
        potential_tax = settle_cgt_year(potential_gains, potential_losses, carried_loss,
                                        c.cgt_rate, c.cgt_exemption).tax_due
        outside_value = sum(balance(s)*quote[s] for s in securities() if membership_status(s) == "outside")
        unknown_value = sum(balance(s)*quote[s] for s in securities() if membership_status(s) == "unknown")
        portfolio_value = value()
        exemption_used = taxes[-1]["exemption_used"] if terminal else liability().exemption_used
        daily.append(dict(date=day, value_eur=value(), cash_eur=cash,
                          cgt_reserve_eur=reserve, net_of_cgt_reserve_eur=value()-reserve,
                          contributions_eur=total_contributions,
                          cgt_paid_eur=total_cgt, dividend_tax_eur=total_dividend_tax,
                          transaction_cost_eur=total_cost,
                          realized_gains_this_year_eur=gains,
                          realized_losses_this_year_eur=losses,
                          carried_loss_eur=carried_loss,
                          cgt_exemption_used_this_year_eur=exemption_used,
                          cgt_exemption_remaining_this_year_eur=c.cgt_exemption-exemption_used,
                          gain_harvest_headroom_eur=0. if terminal else gain_headroom(),
                          hypothetical_liquidation_tax_eur=potential_tax,
                          after_tax_liquidation_value_eur=value()-exit_cost-potential_tax,
                          out_of_index_value_eur=outside_value,
                          out_of_index_weight=outside_value/portfolio_value if portfolio_value else 0.,
                          unknown_membership_value_eur=unknown_value,
                          unknown_membership_weight=unknown_value/portfolio_value if portfolio_value else 0.,
                          exit_policy_cgt_budget_used_eur=policy_tax_spent,
                          holdings={s: balance(s) for s in securities()}))

    summary = dict(strategy="loss_harvesting" if c.harvest else "same_basket_no_harvest",
                   contributions=total_contributions, contribution_count=contribution_count,
                   final_cash=cash if c.liquidate_at_end else None,
                   final_value=value(), final_value_before_final_sale=pre_liquidation_value if c.liquidate_at_end else None,
                   final_tax=final_tax, total_cgt=total_cgt,
                   total_dividend_tax=total_dividend_tax,
                   total_gross_dividends=total_gross_dividends,
                   total_tax=total_cgt + total_dividend_tax,
                   transaction_costs=total_cost, unutilized_loss=liability().loss_carry_forward,
                   cgt_reserve=reserve, liquidated=c.liquidate_at_end,
                   unpaid_contingent_right_units={k:v for k,v in contingent_rights.items() if v},
                   exit_policy=c.exit_policy, exit_policy_reviews=policy_review_count,
                   exit_policy_sales=policy_sale_count,
                   exit_policy_gross_proceeds_eur=policy_gross_proceeds,
                   exit_policy_net_proceeds_eur=policy_net_proceeds,
                   exit_policy_realized_pnl_eur=policy_realized_pnl,
                   exit_policy_positive_incremental_cgt_eur=total_policy_tax_spent,
                   exit_policy_current_year_budget_used_eur=policy_tax_spent,
                   exit_policy_annual_tax_budget_eur=c.exit_annual_tax_budget_eur,
                   exit_policy_skips=policy_skips,
                   gain_harvest_enabled=c.gain_harvest,
                   gain_harvest_reviews=gain_review_count,
                   gain_harvest_sales=gain_sale_count,
                   gain_harvest_gross_proceeds_eur=gain_gross_proceeds,
                   gain_harvest_net_proceeds_eur=gain_net_proceeds,
                   gain_harvest_realized_pnl_eur=gain_realized_pnl,
                   gain_harvest_exemption_increments_eur=gain_exemption_increment,
                   cgt_exemption_used_total_eur=sum(t["exemption_used"] for t in taxes) + liability().exemption_used,
                   gain_harvest_skips=gain_skips,
                   input_data_status="caller-supplied; requires independent corpus audit")
    return BacktestResult(summary, pd.DataFrame(transactions), pd.DataFrame(daily),
                          pd.DataFrame(taxes), pd.DataFrame([asdict(lot) for lot in lots]))


def compare_harvesting(prices, target_weights, config=None, events=None, metadata=None, membership=None):
    """Economic incremental effect after BOTH complete portfolios are liquidated.

    Allocation paths may diverge while same-class repurchases are blocked. This
    difference therefore includes exposure changes and trading costs, not just
    an isolated tax effect. Gross harvested losses times 33% is never a return.
    """
    from dataclasses import replace
    c = config or BacktestConfig()
    if not c.liquidate_at_end:
        raise ValueError("Final liquidation is mandatory for an economic TLH comparison")
    baseline = run_backtest(prices, target_weights, replace(c, harvest=False), events, metadata, membership)
    harvested = run_backtest(prices, target_weights, replace(c, harvest=True), events, metadata, membership)
    return dict(baseline=baseline, harvested=harvested,
                incremental_after_tax_eur=harvested.summary["final_cash"]-baseline.summary["final_cash"],
                warning="Includes allocation-path differences caused by sale/reentry restrictions.")
