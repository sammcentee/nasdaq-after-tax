"""Rebuild daily units, cash and dividend claims from saved transaction records.

Prices and corporate-action terms share the study's prepared inputs. This checks
ledger consistency, not independent source accuracy or tax classifications.
"""
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/latest'
sys.path.insert(0, str(ROOT))
from study_inputs import prepare


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_case(key, actions, marks):
    base = OUT / 'ledgers'
    columns = {'date', 'event', 'security_id', 'units', 'action', 'effective_date',
               'dividend_id', 'net_receivable_eur', 'net_cash_eur', 'cash_eur',
               'cash_outlay_eur', 'net_proceeds_eur', 'gross_proceeds_eur',
               'fees_eur', 'tax_eur', 'reason'}
    t = pd.read_csv(base/f'{key}_transactions.csv.gz', usecols=lambda c: c in columns,
                    parse_dates=['date'], low_memory=False)
    groups = {day: group.to_dict('records') for day, group in t.groupby('date', sort=False)}
    daily = pd.read_csv(base/f'{key}_daily.csv.gz', parse_dates=['date'])
    units, claims = defaultdict(float), {}
    cash = 0.
    maximum = dict(units=0., cash_eur=0., value_eur=0., dividend_receivable_eur=0.)
    comparisons = 0
    for row in daily.itertuples():
        for entry in groups.get(row.date, []):
            event, security = entry['event'], entry.get('security_id')
            if event == 'buy':
                units[security] += entry['units']
                cash -= entry['cash_outlay_eur']
            elif event == 'sell':
                units[security] -= entry['units']
                cash += entry['net_proceeds_eur']
            elif event == 'corporate_action':
                action = entry['action']
                source = actions[(pd.Timestamp(entry['effective_date']), security, action)]
                if action == 'split':
                    units[security] *= source['ratio']
                elif action in ('stock_exchange', 'mixed_merger', 'spinoff'):
                    units[source['successor_id']] += units[security]*source['ratio']
                    if action != 'spinoff':
                        units[security] = 0.
            elif event == 'contribution':
                cash += entry['cash_eur']
            elif event == 'dividend_entitlement':
                assert abs(entry['units']-units[security]) < 1e-7, (key, row.date, security)
                assert entry['dividend_id'] not in claims
                claims[entry['dividend_id']] = entry['net_receivable_eur']
            elif event == 'dividend':
                cash += entry['net_cash_eur']
                if pd.notna(entry.get('dividend_id')):
                    claims.pop(entry['dividend_id'])
            elif event == 'lot_disposal' and entry['reason'] in ('mixed_merger', 'capital_distribution'):
                cash += entry['net_proceeds_eur']
            elif event == 'contingent_payment':
                cash += entry['gross_proceeds_eur']-entry['fees_eur']
            elif event == 'cgt_settlement':
                cash -= entry['tax_eur']
        stored = json.loads(row.holdings)
        securities = set(stored) | set(units)
        residual = max((abs(units[s]-stored.get(s, 0.)) for s in securities), default=0.)
        assert residual < 1e-7, (key, row.date, 'units', residual)
        assert min(units.values(), default=0.) >= -1e-7
        maximum['units'] = max(maximum['units'], residual)
        comparisons += len(securities)
        receivable = sum(claims.values())
        value = cash+receivable+sum(n*marks[row.date][s] for s, n in units.items() if abs(n) > 1e-9)
        for name, actual in [('cash_eur', cash), ('value_eur', value),
                             ('dividend_receivable_eur', receivable)]:
            error = abs(actual-getattr(row, name))
            assert error < 1e-5, (key, row.date, name, error)
            maximum[name] = max(maximum[name], error)
    assert not claims and max(map(abs, units.values()), default=0.) < 1e-7
    return dict(key=key, status='PASS', daily_rows=len(daily),
                security_day_comparisons=comparisons, maximum_residuals=maximum)


def main():
    manifest = json.loads((OUT/'study_manifest.json').read_text())
    sources = {**manifest['input_sha256'], **manifest['code_sha256']}
    for name, expected in sources.items():
        assert digest(ROOT/name) == expected, name
    with TemporaryDirectory(prefix='nasdaq-daily-check-') as temporary:
        prices, _, events, _, _, _ = prepare(temporary)
    actions = {(r['date'], r['security_id'], r['event_type']): r for r in events.to_dict('records')}
    assert len(actions) == len(events), 'Ambiguous corporate event key'
    splits = events.loc[events.event_type.eq('split')].sort_values('date').to_dict('records')
    marks, quote, index = {}, {}, 0
    for day, group in prices.groupby('date', sort=True):
        while index < len(splits) and splits[index]['date'] <= day:
            split = splits[index]
            if split['security_id'] in quote:
                quote[split['security_id']] /= split['ratio']
            index += 1
        fresh = group.dropna(subset=['price_eur'])
        quote.update(zip(fresh.security_id, fresh.price_eur))
        marks[day] = quote.copy()
    specs = json.loads((OUT/'policy_definitions.json').read_text())
    paths = [OUT/'study_manifest.json', OUT/'policy_definitions.json', Path(__file__)]
    paths += [OUT/'ledgers'/f"{spec['key']}_{kind}.csv.gz"
              for spec in specs for kind in ('transactions', 'daily')]
    sources.update({str(path.relative_to(ROOT)): digest(path) for path in paths})
    checks = [check_case(spec['key'], actions, marks) for spec in specs]
    for name, expected in sources.items():
        assert digest(ROOT/name) == expected, name
    result = dict(scope=__doc__.strip(), study_manifest_sha256=digest(OUT/'study_manifest.json'),
        source_sha256=sources, all_passed=True, cases=checks)
    (OUT/'daily_position_audit.json').write_text(json.dumps(result, indent=2)+'\n')
    print(f"PASS: {len(checks)} portfolios, {sum(c['daily_rows'] for c in checks)} daily observations")
    print(json.dumps({name: max(c['maximum_residuals'][name] for c in checks)
                      for name in checks[0]['maximum_residuals']}, indent=2))


if __name__ == '__main__':
    main()
