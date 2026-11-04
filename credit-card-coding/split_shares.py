import json
import re
from decimal import Decimal, ROUND_HALF_UP

FIELDS = ('project_code', 'cost_code', 'reason')
LABELS = {'project_code': 'project', 'cost_code': 'cost code', 'reason': 'reason'}
CENT = Decimal('0.01')
SHARE = re.compile(r'^\s*(\(?)\s*(-?)\s*\$?\s*(-?)([\d,]*\.?\d+)\s*(%?)\s*\)?\s*$')


def _s(v):
    return re.sub(r'\s+', ' ', '' if v is None else str(v)).strip()


def _money(d):
    return '{:,.2f}'.format(d)


def parse_share(v):
    """'$400', '400.00', '1,200', '60%', '(25.00)' -> ('amount'|'percent', Decimal); else None.
    A bare number is dollars: the spreadsheet's Split share column holds numbers."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return 'amount', Decimal(str(v))
    m = SHARE.match(_s(v))
    if not m:
        return None
    neg = bool(m.group(1) or m.group(2) or m.group(3))
    n = Decimal(m.group(4).replace(',', ''))
    return ('percent' if m.group(5) else 'amount'), (-n if neg else n)


def _text_shares(text):
    """The AI step's split, one share per line: 'project | cost code | share | reason'."""
    out = []
    for line in (text or '').splitlines():
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 3 or not any(parts):
            continue
        out.append({'project_code': parts[0], 'cost_code': parts[1], 'share': parts[2],
                    'reason': ' | '.join(parts[3:]).strip()})
    return out


def main(input):
    shares = input.get('shares_json') or '[]'
    shares = json.loads(shares) if isinstance(shares, str) else shares
    shares = list(shares or []) or _text_shares(input.get('split_text'))
    problems = []
    try:
        charge = Decimal(str(input.get('charge_amount'))).quantize(CENT, rounding=ROUND_HALF_UP)
    except Exception:
        charge = None
        problems.append('The charge amount is not known, so the split cannot be checked.')

    parsed = []
    for n, sh in enumerate(shares, 1):
        p = parse_share(sh.get('share'))
        if p is None:
            problems.append('Share %d has no amount or percentage ("$400" or "60%%").' % n)
        parsed.append((dict((f, _s(sh.get(f))) for f in FIELDS), p))

    if charge is not None and not problems:
        sign = -1 if charge < 0 else 1
        amounts = []
        for coding, (kind, value) in parsed:
            if kind == 'percent':
                amounts.append((charge * value / 100).quantize(CENT, rounding=ROUND_HALF_UP))
            else:
                v = value.quantize(CENT, rounding=ROUND_HALF_UP)
                amounts.append(-v if sign < 0 and v > 0 else v)
        pct = [i for i, (_, (kind, _v)) in enumerate(parsed) if kind == 'percent']
        diff = charge - sum(amounts, Decimal('0'))
        if pct and diff != 0 and abs(diff) <= CENT * len(pct):
            amounts[pct[-1]] += diff
            diff = Decimal('0')
        if diff != 0:
            problems.append('The shares total %s but the charge is %s (%s %s). Nothing was applied.' % (
                _money(sum(amounts, Decimal('0'))), _money(charge), _money(abs(diff)),
                'short' if diff > 0 else 'over'))
    else:
        amounts = []

    existing = dict((f, _s(input.get(f))) for f in FIELDS)
    for f in FIELDS:
        given = sorted(set(c[f] for c, _ in parsed if c[f]))
        fill = existing[f] or (given[0] if len(given) == 1 else '')
        for c, _ in parsed:
            if not c[f] and fill:
                c[f] = fill
    for n, (c, _) in enumerate(parsed, 1):
        blank = [LABELS[f] for f in FIELDS if not c[f]]
        if blank:
            problems.append('Share %d has no %s.' % (n, ', '.join(blank)))

    if problems:
        return {'ok': False, 'is_split': False, 'shares': [], 'problems': ' '.join(problems),
                'project_code': '', 'cost_code': '', 'reason': '', 'split_note': ''}

    rows = [dict(c, amount=float(a), amount_text=_money(a)) for (c, _), a in zip(parsed, amounts)]
    if len(rows) == 1:
        return {'ok': True, 'is_split': False, 'shares': rows, 'problems': '',
                'project_code': rows[0]['project_code'], 'cost_code': rows[0]['cost_code'],
                'reason': rows[0]['reason'], 'split_note': ''}

    def distinct(f):
        seen = []
        for r in rows:
            if r[f] not in seen:
                seen.append(r[f])
        return seen

    note = 'Split: ' + '; '.join('%s %s %s' % (r['project_code'], r['cost_code'], r['amount_text']) for r in rows)
    return {
        'ok': True,
        'is_split': True,
        'shares': rows,
        'problems': '',
        'project_code': 'Split: ' + ' / '.join(distinct('project_code')),
        'cost_code': ' / '.join(distinct('cost_code')),
        'reason': ' / '.join(distinct('reason')),
        'split_note': note,
    }
