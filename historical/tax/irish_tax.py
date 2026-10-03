"""Small auditable tax primitives for the historical investment comparison.

These functions do not claim to be a complete filing engine. All values supplied
must already be in EUR. Stock matching is deliberately separate from the annual
capital-gains settlement. Refund timing is not modelled by fund_tax_delta().

Primary sources, checked 3 October 2026:
https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/how-to-calculate-cgt.aspx
https://www.revenue.ie/en/gains-gifts-and-inheritance/transfering-an-asset/if-you-make-a-loss.aspx
https://www.revenue.ie/en/tax-professionals/documents/notes-for-guidance/tca/part19.pdf
https://www.revenue.ie/en/tax-professionals/tdm/income-tax-capital-gains-tax-corporation-tax/part-19/19-04-03.pdf
https://www.revenue.ie/en/tax-professionals/tdm/income-tax-capital-gains-tax-corporation-tax/part-27/27-04-01.pdf
https://www.revenue.ie/en/tax-professionals/tdm/income-tax-capital-gains-tax-corporation-tax/part-27/27-01a-02.pdf
https://www.revenue.ie/en/additional-incomes/dividend-income/index.aspx
https://www.revenue.ie/en/tax-professionals/documents/double-taxation-treaties/u/usa-1997.pdf
"""

from dataclasses import dataclass
from datetime import date
from math import isfinite


def _nonnegative(**values):
    for name, value in values.items():
        if not isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and nonnegative")


@dataclass(frozen=True)
class CGTSettlement:
    tax_due: float
    losses_used: float
    loss_carry_forward: float
    exemption_used: float
    taxable_gain: float


def settle_cgt_year(gains, current_losses, carried_losses=0.0,
                    rate=0.33, exemption=1270.0):
    """Settle one individual's ordinary CGT at one rate.

    Gains and losses are separately accumulated positive EUR amounts after share
    identification, costs and any four-week restriction. Crucially, brought-
    forward losses are used BEFORE the exemption, unlike the UK ordering.
    The exemption is annual and unused amounts do not accumulate. No dividends,
    offshore-fund gains, connected-party losses, or spouse transfers enter here.
    """
    _nonnegative(gains=gains, current_losses=current_losses,
                 carried_losses=carried_losses, rate=rate, exemption=exemption)
    available = current_losses + carried_losses
    used = min(gains, available)
    net_gain = gains - used
    exempt = min(net_gain, exemption)
    taxable = net_gain - exempt
    return CGTSettlement(rate * taxable, used, available - used, exempt, taxable)


def fund_tax_delta(value, original_basis, attributable_dd_credit, rate=0.38):
    """Tax payable (+) or refundable (-) on one disposed fund lot/lot fraction.

    Use the original acquisition cost and the prior DD tax attributable to just
    the units concerned. Do not carry sold units' credits into remaining units.
    The positive gain is floored BEFORE subtracting the credit: max(0, gain*rate
    -credit) would incorrectly deny refunds. This does not allow an ordinary
    fund capital loss to offset another gain. Aggregation/identification of the
    specific fund interest is a caller responsibility.
    """
    _nonnegative(value=value, original_basis=original_basis,
                 attributable_dd_credit=attributable_dd_credit, rate=rate)
    return max(0.0, value - original_basis) * rate - attributable_dd_credit


@dataclass(frozen=True)
class DividendSettlement:
    foreign_withholding: float
    irish_tax_top_up: float
    net_to_reinvest: float
    total_tax: float


def settle_us_dividend(gross_eur, income_tax=0.40, usc=0.08,
                      prsi=0.0435, withholding=0.15):
    """Ordinary treaty-eligible US dividend, rates supplied as marginal rates.

    Assumes valid treaty relief and a credit against Irish Income Tax for US
    withholding. The default 52.35% is a frozen current-rate scenario with top
    USC, not a claim that every higher-rate taxpayer pays that combined rate.
    2026 self-assessed annual Class S PRSI has a blended 4.2375% rate. No minimum
    PRSI, age exemption, bands crossed, or non-US issuer treatment is included.
    """
    _nonnegative(gross_eur=gross_eur, income_tax=income_tax, usc=usc,
                 prsi=prsi, withholding=withholding)
    foreign = gross_eur * withholding
    credit = gross_eur * min(withholding, income_tax)
    irish = gross_eur * (income_tax + usc + prsi) - credit
    total = foreign + irish
    return DividendSettlement(foreign, irish, gross_eur - total, total)


def stock_matching_order(acquisition_dates, disposal_date):
    """Indices of lots to consume: purchases in preceding four weeks, then FIFO.

    Caller must filter to the same legal share class and same owner/capacity;
    ticker changes are not new share classes. Following Revenue's public LIFO
    description, recent acquisitions are ordered latest first. Same-date lots
    use reverse input order. The inclusive 28-day boundary is conservative;
    harvesting code should wait >=29 days and prevent buys for >=29 days after
    sale to avoid depending on day-boundary interpretation.
    """
    if any(d > disposal_date for d in acquisition_dates):
        raise ValueError("Future purchases cannot be matched to an earlier sale")
    recent = [i for i, d in enumerate(acquisition_dates)
              if 0 <= (disposal_date - d).days <= 28]
    earlier = [i for i, d in enumerate(acquisition_dates)
               if (disposal_date - d).days > 28]
    recent.sort(key=lambda i: (acquisition_dates[i], i), reverse=True)
    earlier.sort(key=lambda i: (acquisition_dates[i], i))
    return recent + earlier


def unrestricted_loss_after_repurchase(loss, units_sold, units_reacquired):
    """Proportion free for other gains after same-class buys within four weeks.

    Restricted balance may ONLY reduce gains on those replacement shares.
    This helper is proportional and does not identify multiple replacement
    trades or release restricted losses on their subsequent disposal.
    """
    _nonnegative(loss=loss, units_sold=units_sold,
                 units_reacquired=units_reacquired)
    if units_sold == 0:
        raise ValueError("units_sold must be positive")
    return loss * (1.0 - min(units_sold, units_reacquired) / units_sold)
