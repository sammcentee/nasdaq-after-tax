"""Annual September contribution reviews using previously published Irish CPI."""
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pandas as pd


INFLATION_FILE = Path(__file__).resolve().parent / "inflation" / "irish_cpi.csv"


def _load_cpi():
    return pd.read_csv(INFLATION_FILE, parse_dates=["cpi_published_date"])


def build_cpi_schedule(dates, initial_amount=1000):
    """Return one contribution per supplied monthly payment date.

    Dates must start in September and cover consecutive months. Each September
    payment reviews the amount against that year's August all-items CPI, on the
    unchanged December 2006=100 base. The first August observation anchors the
    initial amount. Deflation reduces contributions. Round only each final
    monthly amount to cents, half up; never compound rounded annual amounts.

    Every release must precede its review date, including the initial anchor.
    Missing or not-yet-published data raises an error rather than using hindsight
    or silently changing the agreed August reference month.
    """
    dates = pd.DatetimeIndex(pd.to_datetime(list(dates))).normalize()
    if len(dates) == 0 or dates.isna().any():
        raise ValueError("Payment dates must be nonempty and valid.")
    months = dates.to_period("M")
    if dates[0].month != 9 or any(
        right.ordinal - left.ordinal != 1 for left, right in zip(months, months[1:])
    ):
        raise ValueError("Payment dates must start in September and cover consecutive months.")
    initial = Decimal(str(initial_amount))
    if not initial.is_finite() or initial <= 0:
        raise ValueError("The initial monthly contribution must be positive and finite.")

    cpi = _load_cpi().set_index("reference_month")
    rows = []
    base_index = None
    for date in dates:
        if date.month == 9:
            reference = f"{date.year}-08"
            if reference not in cpi.index:
                raise ValueError(f"No archived August CPI observation for {date.year}.")
            observation = cpi.loc[reference]
            published = pd.Timestamp(observation.cpi_published_date).normalize()
            if published >= date:
                raise ValueError(f"CPI for {reference} was not published before review {date.date()}.")
            index = Decimal(str(observation.cpi_index))
            if base_index is None:
                base_index = index
                base_reference = reference
            amount = (initial * index / base_index).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            review_date = date
        rows.append({
            "date": date,
            "contribution_eur": float(amount),
            "review_date": review_date,
            "reference_month": reference,
            "cpi_index": float(index),
            "cpi_published_date": published,
            "base_cpi_index": float(base_index),
            "base_reference_month": base_reference,
            "initial_contribution_eur": float(initial),
            "index_base": "December 2006=100",
            "release_url": observation.release_url,
        })
    return pd.DataFrame(rows)
