import html
import json
import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

FIELDS = ('project_code', 'cost_code', 'reason')
LABEL = {'project_code': 'project', 'cost_code': 'cost code', 'reason': 'reason'}
CENT = Decimal('0.01')


def _s(v):
    return re.sub(r'\s+', ' ', '' if v is None else str(v)).strip()


def _true(v):
    return v is True or _s(v).lower() in ('true', '1', 'yes')


def _d(v):
    try:
        return Decimal(_s(v) or '0').quantize(CENT, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal('0.00')


def _money(d):
    return ('-$' if d < 0 else '$') + '{:,.2f}'.format(abs(d))


def _h(v):
    return html.escape(_s(v), quote=True)


def _ver(v):
    try:
        return int(float(_s(v)))
    except ValueError:
        return 0


def _safe(s):
    return re.sub(r'[^A-Za-z0-9_-]+', '-', s).strip('-') or 'NA'


def _month_name(m):
    try:
        y, mo = m.split('-')
        return date(int(y), int(mo), 1).strftime('%B %Y')
    except Exception:
        return m


STYLES = {
    # Plain black on white: rules only, no fill.
    'minimal': {
        'font': 'Arial,Helvetica,sans-serif', 'size': '12px', 'title': 'font-size:18px;font-weight:bold',
        'head': 'border-bottom:2px solid #000;font-weight:bold',
        'job': 'font-weight:bold;font-size:13px;padding-top:14px;border-bottom:1px solid #000',
        'cost': 'font-weight:bold;color:#444;padding-left:12px;padding-top:6px',
        'row': '', 'sub': 'font-weight:bold;border-top:1px solid #999',
        'jobtotal': 'font-weight:bold;border-top:1px solid #000', 'grand': 'font-weight:bold;border-top:3px double #000;font-size:13px'},
    # An accountant's ledger: hairlines between rows, figures in a fixed-width face, double rule under the total.
    'ledger': {
        'font': 'Arial,Helvetica,sans-serif', 'size': '12px', 'title': 'font-size:17px;font-weight:bold;letter-spacing:0.5px;text-transform:uppercase',
        'head': 'border-top:1px solid #000;border-bottom:1px solid #000;font-weight:bold;text-transform:uppercase;font-size:10px;letter-spacing:0.5px',
        'job': 'font-weight:bold;text-transform:uppercase;padding-top:14px;letter-spacing:0.5px',
        'cost': 'padding-left:12px;color:#333;font-style:italic',
        'row': 'border-bottom:1px solid #e6e6e6', 'sub': 'font-weight:bold;border-top:1px solid #000',
        'jobtotal': 'font-weight:bold;border-bottom:1px solid #000', 'grand': 'font-weight:bold;border-bottom:3px double #000;font-size:13px',
        'amount': 'font-family:Menlo,Consolas,monospace'},
    # Soft grey bands for each job and its total, white rows between.
    'banded': {
        'font': 'Arial,Helvetica,sans-serif', 'size': '12px', 'title': 'font-size:18px;font-weight:bold;color:#333',
        'head': 'background:#555;color:#fff;font-weight:bold',
        'job': 'background:#e9e9e9;font-weight:bold;font-size:13px',
        'cost': 'background:#f6f6f6;font-weight:bold;padding-left:12px;color:#444',
        'row': 'border-bottom:1px solid #eee', 'sub': 'font-weight:bold',
        'jobtotal': 'background:#e9e9e9;font-weight:bold', 'grand': 'background:#555;color:#fff;font-weight:bold;font-size:13px'},
    # A printed statement: serif type, centred heading, thin rules.
    'classic': {
        'font': 'Georgia,"Times New Roman",serif', 'size': '12.5px', 'title': 'font-size:20px;font-weight:normal;text-align:center',
        'subtitle': 'text-align:center', 'head': 'border-bottom:1px solid #000;font-weight:normal;font-style:italic',
        'job': 'font-size:14px;padding-top:14px;font-variant:small-caps;letter-spacing:0.5px;border-bottom:1px solid #999',
        'cost': 'font-style:italic;padding-left:12px',
        'row': '', 'sub': 'font-style:italic;border-top:1px solid #ccc',
        'jobtotal': 'font-weight:bold;border-top:1px solid #000', 'grand': 'font-weight:bold;border-top:3px double #000;font-size:14px'},
}
DEFAULT_STYLE = 'minimal'


def _grouped(items, show_grand, style):
    """Job, then cost code, then each transaction and its amount, with totals. A package is one
    cardholder's month, so neither has a column: both are in the page header."""
    st = STYLES.get(style) or STYLES[DEFAULT_STYLE]
    width = 3
    pad = 'padding:3px 6px'
    amt = st.get('amount', '')

    def td(text, extra='', right=False, colspan=1):
        return '<td%s style="%s;%s%s">%s</td>' % (' colspan="%d"' % colspan if colspan > 1 else '', pad,
                                                  'text-align:right;white-space:nowrap;' if right else '', extra, text)

    head = ['Date', 'Transaction', 'Amount']
    out = ['<table cellspacing="0" style="border-collapse:collapse;width:100%%;font-size:%s">' % st['size'],
           '<tr>' + ''.join('<th style="%s;text-align:%s;%s">%s</th>' % (pad, 'right' if h == 'Amount' else 'left', st['head'], h)
                            for h in head) + '</tr>']

    def total_row(label, value, key):
        return '<tr>%s%s</tr>' % (td(label, st[key], right=True, colspan=width - 1), td(_money(value), st[key] + ';' + amt, right=True))

    grand = Decimal('0')
    jobs = sorted(set(i['job'] for i in items))
    for job in jobs:
        job_items = [i for i in items if i['job'] == job]
        job_total = sum((i['amt'] for i in job_items), Decimal('0'))
        grand += job_total
        if len(jobs) > 1 or show_grand:
            out.append('<tr>%s</tr>' % td('Job ' + _h(job), st['job'], colspan=width))
        for cost in sorted(set(i['cost'] for i in job_items)):
            rows = sorted((i for i in job_items if i['cost'] == cost), key=lambda i: (i['date'], i['name']))
            out.append('<tr>%s</tr>' % td('Cost code ' + _h(cost), st['cost'], colspan=width))
            for i in rows:
                name = _h(i['name']) + (' <span style="color:#777">(%s)</span>' % _h(i['note']) if i['note'] else '')
                cells = [td(_h(i['date']), st['row'] + ';padding-left:20px;white-space:nowrap'), td(name, st['row'])]
                cells.append(td(_money(i['amt']), st['row'] + ';' + amt, right=True))
                out.append('<tr>%s</tr>' % ''.join(cells))
            out.append(total_row('Cost code %s total' % _h(cost), sum((i['amt'] for i in rows), Decimal('0')), 'sub'))
        out.append(total_row('Job %s total' % _h(job), job_total, 'jobtotal'))
    if show_grand:
        out.append(total_row('Total, all jobs', grand, 'grand'))
    return ''.join(out) + '</table>'


def _page(title, subtitle, items, show_grand, style):
    st = STYLES.get(style) or STYLES[DEFAULT_STYLE]
    return ('<div style="font-family:%s;color:#222">'
            '<div style="margin:0 0 2px 0;%s">%s</div><div style="margin:0 0 14px 0;color:#666;font-size:11px;%s">%s</div>%s'
            '<div style="margin-top:10px;color:#777;font-size:10px">Credits are negative. A split charge appears at its share.</div></div>'
            % (st['font'], st['title'], _h(title), st.get('subtitle', ''), subtitle, _grouped(items, show_grand, style)))


def _entries(t, splits):
    """A charge as the entries it is packaged as: one, or one per split share."""
    if _s(t.get('coding_source')).lower() == 'split':
        shares = splits.get(_s(t.get('transaction_id')), [])
        out = []
        for sh in shares:
            others = '; '.join('%s %s %s' % (_s(o.get('project_code')), _s(o.get('cost_code')), _money(_d(o.get('amount'))))
                               for o in shares if o is not sh)
            out.append({'record_id': _s(sh.get('Record ID')), 'table': 'splits',
                        'project_code': _s(sh.get('project_code')), 'cost_code': _s(sh.get('cost_code')),
                        'reason': _s(sh.get('reason')), 'amount': _d(sh.get('amount')),
                        'sent': _true(sh.get('sent_in_package')), 'version': sh.get('package_version_sent'),
                        'split_note': 'Split: %s of %s (also %s)' % (_money(_d(sh.get('amount'))), _money(_d(t.get('amount'))), others)})
        return out
    return [{'record_id': _s(t.get('Record ID')), 'table': 'transactions',
             'project_code': _s(t.get('project_code')), 'cost_code': _s(t.get('cost_code')),
             'reason': _s(t.get('reason')), 'amount': _d(t.get('amount')),
             'sent': _true(t.get('sent_in_package')), 'version': t.get('package_version_sent'), 'split_note': ''}]


def _blocker(t, entries, splits, receipts, today):
    """Why this charge keeps its month from closing, or ''."""
    exempt = _true(t.get('exempt'))
    matched = _true(t.get('matched'))
    missing = []
    if not matched and not exempt:
        missing.append('receipt')
    elif matched and _s(t.get('matched_receipt_id')) not in receipts:
        missing.append('receipt record (matched to %s, not found)' % (_s(t.get('matched_receipt_id')) or 'nothing'))
    if _s(t.get('coding_source')).lower() == 'split':
        shares = splits.get(_s(t.get('transaction_id')), [])
        if not shares:
            missing.append('split shares')
        elif sum((e['amount'] for e in entries), Decimal('0')) != _d(t.get('amount')):
            missing.append('split shares that add up to the charge')
        else:
            blank = sorted(set(LABEL[f] for e in entries for f in FIELDS if not e[f]))
            missing += blank
    else:
        missing += [LABEL[f] for f in FIELDS if not _s(t.get(f))]
    if not missing and _s(t.get('coding_source')).lower() == 'history':
        coded_on = _s(t.get('history_coded_on'))[:10]
        if not coded_on or coded_on >= today:
            missing.append('a day for the cardholder to see coding taken from history')
    return ', '.join(missing)


def main(input):
    txns = json.loads(input.get('transactions_json') or '[]') or []
    receipts = {}
    for r in json.loads(input.get('receipts_json') or '[]') or []:
        if isinstance(r, dict):
            receipts[_s(r.get('Record ID'))] = _s(r.get('receipt_number'))
        elif isinstance(r, list) and r:
            receipts[_s(r[0])] = _s(r[1]) if len(r) > 1 else ''
    splits = {}
    for sh in json.loads(input.get('splits_json') or '[]') or []:
        splits.setdefault(_s(sh.get('transaction_id')), []).append(sh)
    today = _s(input.get('today'))[:10] or date.today().isoformat()
    only = _s(input.get('statement_month'))
    style = _s(input.get('style')).lower() or DEFAULT_STYLE

    units = {}
    for t in txns:
        m = _s(t.get('statement_month'))
        if m and (not only or m == only):
            holder = _s(t.get('cardholder_name')) or '(no cardholder)'
            units.setdefault((m, holder.upper()), []).append(t)

    status, chosen, open_blockers = [], None, {}
    for key in sorted(units):
        rows = units[key]
        blockers, unsent = [], False
        for t in rows:
            entries = _entries(t, splits)
            why = _blocker(t, entries, splits, receipts, today)
            if why:
                blockers.append({'cardholder_name': _s(t.get('cardholder_name')), 'transaction_id': _s(t.get('transaction_id')),
                                 'transaction_date': _s(t.get('transaction_date')), 'merchant': _s(t.get('merchant')),
                                 'amount': '%.2f' % _d(t.get('amount')), 'missing': why})
            if any(not e['sent'] for e in entries):
                unsent = True
        status.append({'unit': '%s %s' % (key[0], _s(rows[0].get('cardholder_name')) or key[1]), 'charges': len(rows),
                       'open_items': len(blockers), 'unsent': unsent})
        if blockers and unsent:
            open_blockers[key] = blockers
        if not blockers and unsent and chosen is None:
            chosen = key

    log = '; '.join('%s: %d charges, %s' % (s['unit'], s['charges'],
                                            ('%d open' % s['open_items']) if s['open_items'] else ('ready' if s['unsent'] else 'already sent'))
                    for s in status) or 'No charges loaded.'
    empty = {'ready': False, 'statement_month': '', 'month_label': '', 'cardholder_name': '', 'card_last4': '', 'version': 0,
             'groups': [], 'group_count': 0, 'summary_html': '', 'summary_file_name': '', 'month_total': '0.00',
             'mark_sent': [], 'mark_sent_splits': [], 'status_log': log, 'blockers': [], 'blocker_count': 0}
    if chosen is None:
        if not open_blockers:
            return empty
        key = sorted(open_blockers)[0]
        return dict(empty, statement_month=key[0], month_label=_month_name(key[0]),
                    cardholder_name=_s(units[key][0].get('cardholder_name')),
                    blockers=open_blockers[key], blocker_count=len(open_blockers[key]))

    rows = units[chosen]
    holder_name = _s(rows[0].get('cardholder_name')) or '(no cardholder)'
    cards = sorted(set(_s(t.get('card_last4')) for t in rows if _s(t.get('card_last4'))))
    card_text = (' &nbsp;|&nbsp; Card ending %s' % _h(', '.join(cards))) if cards else ''
    month = chosen[0]
    version = 1 + max([_ver(e['version']) for t in rows for e in _entries(t, splits) if e['sent']] or [0])
    groups, cover_lines = {}, []
    mark, mark_splits = [], []
    month_total = Decimal('0')
    for t in sorted(rows, key=lambda r: (_s(r.get('transaction_date')), _s(r.get('transaction_id')))):
        rid = _s(t.get('matched_receipt_id')) if _true(t.get('matched')) else ''
        holder = _s(t.get('cardholder_name')) or '(no cardholder)'
        for e in _entries(t, splits):
            job = e['project_code']
            month_total += e['amount']
            g = groups.setdefault(job, {'items': [], 'receipt_ids': []})
            g['items'].append({
                'record_id': e['record_id'], 'table': e['table'], 'transaction_id': _s(t.get('transaction_id')),
                'transaction_date': _s(t.get('transaction_date')), 'merchant': _s(t.get('merchant')),
                'amount': '%.2f' % e['amount'], 'cost_code': e['cost_code'], 'split_note': e['split_note'],
                'cardholder_name': holder, 'receipt_number': receipts.get(rid, '') if rid else 'Not required (exempt)',
                'receipt_id': rid, 'no_receipt_needed': not rid, 'is_new': True, 'status': 'Included',
                'previous_version': '', '_amt': e['amount']})
            if rid and rid not in g['receipt_ids']:
                g['receipt_ids'].append(rid)
            note = e['split_note'] or ('exempt, no receipt' if not rid else '')
            cover_lines.append({'job': job, 'cost': e['cost_code'], 'date': _s(t.get('transaction_date')),
                          'name': _s(t.get('merchant')), 'holder': holder, 'amt': e['amount'], 'note': note})
            (mark_splits if e['table'] == 'splits' else mark).append({'record_id': e['record_id'], 'transaction_id': _s(t.get('transaction_id'))})

    label = _month_name(month)
    out_groups = []
    for job in sorted(groups):
        g = groups[job]
        total = sum((i['_amt'] for i in g['items']), Decimal('0'))
        for i in g['items']:
            i.pop('_amt')
        lines = ['- %s | %s | %s | %s' % (i['transaction_id'], i['transaction_date'], i['merchant'], i['amount']) for i in g['items']]
        out_groups.append({
            'group_key': month + '|' + holder_name + '|' + job, 'receipt_month': month, 'project_code': job, 'version': version,
            'file_name': 'Finance_Package_%s_%s_%s.pdf' % (_safe(month), _safe(holder_name), _safe(job)),
            'new_count': len(g['items']), 'previous_count': 0, 'total_count': len(g['items']),
            'new_total': '%.2f' % total, 'previous_total': '0.00', 'grand_total': '%.2f' % total,
            'changes_text': '\n'.join(lines),
            'changes_html': '<ul>' + ''.join('<li>%s</li>' % _h(x[2:]) for x in lines) + '</ul>',
            'receipt_ids': g['receipt_ids'], 'receipt_ids_text': ','.join(g['receipt_ids']), 'transactions': g['items'],
            'cover_html': _page('Job %s - %s' % (job, label), '%s%s &nbsp;|&nbsp; Prepared %s' % (_h(holder_name), card_text, _h(today)),
                                [x for x in cover_lines if x['job'] == job], False, style),
            'new_transactions': [{k: i[k] for k in ('record_id', 'table', 'transaction_id', 'transaction_date', 'merchant',
                                                    'amount', 'cost_code', 'receipt_id')} for i in g['items']],
        })

    summary = _page('Credit card summary - %s' % label,
                    '%s%s &nbsp;|&nbsp; Prepared %s &nbsp;|&nbsp; %d job package%s attached'
                    % (_h(holder_name), card_text, _h(today), len(out_groups), '' if len(out_groups) == 1 else 's'),
                    cover_lines, True, style)
    return dict(empty, ready=True, statement_month=month, month_label=label, cardholder_name=holder_name,
                card_last4=', '.join(cards), version=version, groups=out_groups,
                group_count=len(out_groups), summary_html=summary, month_total='%.2f' % month_total,
                summary_file_name='Card_Summary_%s_%s' % (_safe(month), _safe(holder_name)),
                mark_sent=mark, mark_sent_splits=mark_splits)
