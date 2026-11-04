import html
import json
import re
from datetime import datetime, timedelta, timezone

SECTIONS = [
    ('problem', 'Needs your attention'),
    ('no_match', 'No card charge found yet'),
    ('received', 'Received - waiting for the card statement'),
    ('matched', 'Matched to a card charge'),
    ('coded', 'Coding received'),
    ('history', 'Coded from your history - reply only if wrong'),
    ('complete', 'Complete - nothing more needed'),
]
NEEDS_CODING = ('matched', 'received', 'no_match', 'history')
FIELDS = (('project_code', 'project'), ('cost_code', 'cost code'), ('reason', 'reason'))


def _s(v):
    return re.sub(r'\s+', ' ', '' if v is None else str(v)).strip()


def _h(v):
    return html.escape(_s(v), quote=True)


WHEN = re.compile(r'^(\d{4})-(\d\d)-(\d\d)[T ](\d\d):(\d\d)(?::(\d\d))?(?:\.\d+)?\s*(Z|[+-]\d\d:?\d\d)?$', re.I)


def _when(v):
    m = WHEN.match(_s(v))
    if not m:
        return None
    y, mo, d, h, mi, sec, tz = m.groups()
    off = timedelta(0)
    if tz and tz.upper() != 'Z':
        sign = -1 if tz[0] == '-' else 1
        digits = tz[1:].replace(':', '')
        off = sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
    return datetime(int(y), int(mo), int(d), int(h), int(mi), int(sec or 0), tzinfo=timezone(off))


def _amount(r):
    a = _s(r.get('amount'))
    try:
        a = '{:,.2f}'.format(float(a))
    except ValueError:
        pass
    return (a + ' ' + _s(r.get('currency'))).strip()


def _line(r):
    what = ' - '.join(x for x in (_h(r.get('merchant')), _h(r.get('date')), _h(_amount(r))) if x)
    parts = ['<b>%s</b>' % (what or _h(r.get('ref')))]
    kind = _s(r.get('kind'))
    if kind in NEEDS_CODING or kind in ('coded', 'complete'):
        have = ['%s %s' % (label.capitalize(), _h(r.get(f))) for f, label in FIELDS if _s(r.get(f))]
        missing = [label for f, label in FIELDS if not _s(r.get(f))]
        if have:
            parts.append(' &middot; '.join(have))
        if missing and kind != 'complete':
            parts.append('<span style="color:#b00">Still needed: %s</span>' % ', '.join(missing))
    if _s(r.get('note')):
        parts.append(_h(r.get('note')))
    if _s(r.get('ref')):
        parts.append('<span style="color:#666">Ref: %s</span>' % _h(r.get('ref')))
    return '<li>%s</li>' % '<br>'.join(parts)


def main(input):
    rows = input.get('notifications_json') or '[]'
    rows = json.loads(rows) if isinstance(rows, str) else rows
    quiet = int(float(_s(input.get('quiet_minutes')) or 5))
    now = _when(input.get('now')) or datetime.now(timezone.utc)

    by_person = {}
    for r in rows or []:
        to = _s(r.get('recipient')).lower()
        if to:
            by_person.setdefault(to, []).append(r)

    batches, waiting = [], 0
    for to, items in sorted(by_person.items()):
        newest = max((_when(r.get('Created time') or r.get('Created at') or r.get('created_at')) or now - timedelta(minutes=quiet)) for r in items)
        if now - newest < timedelta(minutes=quiet):
            waiting += len(items)
            continue
        body = ['<p>Hello,</p>']
        counts = []
        for kind, title in SECTIONS:
            sec = [r for r in items if _s(r.get('kind')) == kind]
            if not sec:
                continue
            counts.append('%d %s' % (len(sec), title.split(' - ')[0].lower()))
            body.append('<h3 style="margin:16px 0 6px 0">%s</h3><ul>%s</ul>' % (html.escape(title), ''.join(_line(r) for r in sec)))
        other = [r for r in items if _s(r.get('kind')) not in dict(SECTIONS)]
        if other:
            body.append('<h3 style="margin:16px 0 6px 0">Other updates</h3><ul>%s</ul>' % ''.join(_line(r) for r in other))
        if any(_s(r.get('kind')) in NEEDS_CODING and not all(_s(r.get(f)) for f, _ in FIELDS) for r in items) \
                or any(_s(r.get('kind')) == 'history' for r in items):
            body.append('<p>To add or correct coding, reply with one line per item, keeping <b>[CC]</b> in the '
                        'subject:<br><code>Ref: project, cost code, reason</code></p>')
        n = len(items)
        batches.append({
            'recipient': to,
            'subject': '[CC] %d card receipt update%s' % (n, '' if n == 1 else 's'),
            'html': ''.join(body),
            'summary': ', '.join(counts),
            'record_ids': [_s(r.get('Record ID')) for r in items if _s(r.get('Record ID'))],
            'count': n,
        })
    return {'batches': batches, 'batch_count': len(batches), 'waiting_count': waiting}
