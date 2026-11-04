import json
import re
from datetime import date

KEYS = ('merchant', 'receipt_date', 'amount', 'currency', 'card_last_4', 'receipt_number',
        'project_code', 'cost_code', 'reason', 'split_text', 'notes')
MONTHS = {m: i for i, m in enumerate(
    ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'), 1)}


def _s(v):
    return re.sub(r'\s+', ' ', '' if v is None else str(v)).strip()


def _object(text):
    """The JSON object in Claude's reply, tolerating code fences or a sentence around it."""
    t = (text or '').strip()
    t = re.sub(r'^```(?:json)?\s*|\s*```$', '', t, flags=re.I)
    try:
        v = json.loads(t)
        if isinstance(v, dict):
            return v
    except ValueError:
        pass
    a, b = t.find('{'), t.rfind('}')
    if a >= 0 and b > a:
        try:
            v = json.loads(t[a:b + 1])
            if isinstance(v, dict):
                return v
        except ValueError:
            pass
    return None


def _date(v):
    s = _s(v)
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})', s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.match(r'^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})$', s)
        if m:
            mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            y += 2000 if y < 100 else 0
        else:
            m = re.match(r'^([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})$', s)
            if not m or m.group(1).lower() not in MONTHS:
                return ''
            mo, d, y = MONTHS[m.group(1).lower()], int(m.group(2)), int(m.group(3))
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return ''


def _amount(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    s = _s(v)
    neg = s.startswith('-') or (s.startswith('(') and s.endswith(')'))
    s = re.sub(r'[^0-9.]', '', s.replace(',', ''))
    if not re.match(r'^\d*\.?\d+$', s):
        return None
    n = round(float(s), 2)
    return -n if neg else n


def _split_text(v):
    if isinstance(v, list):
        v = '\n'.join(_s(x) for x in v)
    return '\n'.join(line.strip() for line in str(v or '').splitlines() if line.count('|') >= 2)


def main(input):
    obj = _object(input.get('response_text'))
    empty = dict((k, '') for k in KEYS)
    empty.update(amount=None, receipt_month='')
    if obj is None:
        return dict(empty, ok=False, is_receipt=False,
                    problems='The reply was not the JSON object the prompt asks for.')
    is_receipt = obj.get('is_receipt') is not False and str(obj.get('is_receipt')).lower() != 'false'
    if not is_receipt:
        return dict(empty, ok=True, is_receipt=False, notes=_s(obj.get('notes')), problems='')

    out = dict((k, _s(obj.get(k))) for k in KEYS)
    out['receipt_date'] = _date(obj.get('receipt_date'))
    out['receipt_month'] = out['receipt_date'][:7]
    out['amount'] = _amount(obj.get('amount'))
    out['currency'] = (re.sub(r'[^A-Za-z]', '', out['currency']).upper()[:3]) or ''
    out['card_last_4'] = re.sub(r'\D', '', out['card_last_4'])[-4:]
    out['split_text'] = _split_text(obj.get('split_text'))
    if out['split_text']:
        out['project_code'] = out['cost_code'] = out['reason'] = ''

    problems = []
    if out['amount'] is None:
        problems.append('No total could be read.')
    if not out['receipt_date']:
        problems.append('No purchase date could be read.')
    if not out['merchant']:
        problems.append('No merchant could be read.')
    return dict(out, ok=True, is_receipt=True, problems=' '.join(problems))
