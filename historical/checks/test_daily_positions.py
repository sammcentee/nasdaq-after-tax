"""A separate holdings reconstruction must detect corrupted daily records."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

import pandas as pd
import check_daily_positions as audit


class DailyPositionChecks(unittest.TestCase):
    def fixture(self, directory):
        base = Path(directory)/'ledgers'
        base.mkdir()
        days = pd.to_datetime(['2020-01-02', '2020-01-03', '2020-01-06'])
        rows = [
            dict(date=days[0], event='contribution', cash_eur=100.),
            dict(date=days[0], event='buy', security_id='A', units=10., cash_outlay_eur=100.),
            dict(date=days[1], event='corporate_action', security_id='A', action='split', effective_date=days[1]),
            dict(date=days[1], event='dividend_entitlement', security_id='A', units=20.,
                 dividend_id='d1', net_receivable_eur=20.),
            dict(date=days[2], event='sell', security_id='A', units=20., net_proceeds_eur=100.),
            dict(date=days[2], event='dividend', security_id='A', dividend_id='d1', net_cash_eur=20.),
        ]
        pd.DataFrame(rows).to_csv(base/'case_transactions.csv.gz', index=False)
        daily = pd.DataFrame([
            dict(date=days[0], holdings=json.dumps({'A': 10.}), cash_eur=0., value_eur=100., dividend_receivable_eur=0.),
            dict(date=days[1], holdings=json.dumps({'A': 20.}), cash_eur=0., value_eur=120., dividend_receivable_eur=20.),
            dict(date=days[2], holdings='{}', cash_eur=120., value_eur=120., dividend_receivable_eur=0.),
        ])
        actions = {(days[1], 'A', 'split'): dict(ratio=2.)}
        marks = {days[0]: {'A': 10.}, days[1]: {'A': 5.}, days[2]: {'A': 5.}}
        return base, daily, actions, marks

    def test_split_and_entitlement_survive_sale_until_payment(self):
        with TemporaryDirectory() as directory, patch.object(audit, 'OUT', Path(directory)):
            base, daily, actions, marks = self.fixture(directory)
            daily.to_csv(base/'case_daily.csv.gz', index=False)
            result = audit.check_case('case', actions, marks)
            self.assertEqual(result['status'], 'PASS')
            self.assertEqual(max(result['maximum_residuals'].values()), 0.)

    def test_rejects_wrong_units_cash_value_or_claim(self):
        for field, index, value in [('holdings', 1, json.dumps({'A': 21.})),
                                    ('cash_eur', 2, 121.), ('value_eur', 1, 121.),
                                    ('dividend_receivable_eur', 1, 21.)]:
            with self.subTest(field=field), TemporaryDirectory() as directory, patch.object(audit, 'OUT', Path(directory)):
                base, daily, actions, marks = self.fixture(directory)
                daily.loc[index, field] = value
                daily.to_csv(base/'case_daily.csv.gz', index=False)
                with self.assertRaises(AssertionError):
                    audit.check_case('case', actions, marks)


if __name__ == '__main__':
    unittest.main()
