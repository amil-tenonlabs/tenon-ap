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


def _grouped(items, show_grand):
    """Job, then cost code, then each transaction and its amount, with totals."""
    cell = 'padding:3px 6px;border-bottom:1px solid #e3e3e3'
    out = ['<table cellspacing="0" style="border-collapse:collapse;width:100%%;font-size:12px">'
           '<tr style="background:#222;color:#fff"><th style="%s;text-align:left">Date</th>'
           '<th style="%s;text-align:left">Transaction</th><th style="%s;text-align:left">Cardholder</th>'
           '<th style="%s;text-align:right">Amount</th></tr>' % (cell, cell, cell, cell)]
    grand = Decimal('0')
    for job in sorted(set(i['job'] for i in items)):
        job_items = [i for i in items if i['job'] == job]
        job_total = sum((i['amt'] for i in job_items), Decimal('0'))
        grand += job_total
        out.append('<tr style="background:#dfe7f1"><td colspan="4" style="%s;font-weight:bold;font-size:13px">Job %s</td></tr>'
                   % (cell, _h(job)))
        for cost in sorted(set(i['cost'] for i in job_items)):
            rows = sorted((i for i in job_items if i['cost'] == cost), key=lambda i: (i['date'], i['name']))
            out.append('<tr style="background:#f3f3f3"><td colspan="4" style="%s;font-weight:bold;padding-left:14px">Cost code %s</td></tr>'
                       % (cell, _h(cost)))
            for i in rows:
                name = _h(i['name']) + (' <span style="color:#777">(%s)</span>' % _h(i['note']) if i['note'] else '')
                out.append('<tr><td style="%s;padding-left:22px;white-space:nowrap">%s</td><td style="%s">%s</td>'
                           '<td style="%s">%s</td><td style="%s;text-align:right;white-space:nowrap">%s</td></tr>'
                           % (cell, _h(i['date']), cell, name, cell, _h(i['holder']), cell, _money(i['amt'])))
            out.append('<tr><td colspan="3" style="%s;text-align:right;font-weight:bold">Cost code %s total</td>'
                       '<td style="%s;text-align:right;font-weight:bold">%s</td></tr>'
                       % (cell, _h(cost), cell, _money(sum((i['amt'] for i in rows), Decimal('0')))))
        out.append('<tr style="background:#dfe7f1"><td colspan="3" style="%s;text-align:right;font-weight:bold">Job %s total</td>'
                   '<td style="%s;text-align:right;font-weight:bold">%s</td></tr>' % (cell, _h(job), cell, _money(job_total)))
    if show_grand:
        out.append('<tr style="background:#222;color:#fff"><td colspan="3" style="%s;text-align:right;font-weight:bold">Total, all jobs</td>'
                   '<td style="%s;text-align:right;font-weight:bold">%s</td></tr>' % (cell, cell, _money(grand)))
    return ''.join(out) + '</table>'


def _page(title, subtitle, table):
    return ('<div style="font-family:Arial,Helvetica,sans-serif;color:#222">'
            '<h2 style="margin:0 0 2px 0;font-size:18px">%s</h2><p style="margin:0 0 12px 0;color:#666;font-size:12px">%s</p>%s'
            '<p style="margin-top:10px;color:#777;font-size:11px">Credits are negative. A split charge appears at its share.</p></div>'
            % (_h(title), subtitle, table))


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

    months = {}
    for t in txns:
        m = _s(t.get('statement_month'))
        if m and (not only or m == only):
            months.setdefault(m, []).append(t)

    status, chosen, open_blockers = [], None, {}
    for m in sorted(months):
        rows = months[m]
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
        status.append({'statement_month': m, 'charges': len(rows), 'open_items': len(blockers), 'unsent': unsent})
        if blockers and unsent:
            open_blockers[m] = blockers
        if not blockers and unsent and chosen is None:
            chosen = m

    log = '; '.join('%s: %d charges, %s' % (s['statement_month'], s['charges'],
                                            ('%d open' % s['open_items']) if s['open_items'] else ('ready' if s['unsent'] else 'already sent'))
                    for s in status) or 'No charges loaded.'
    empty = {'ready': False, 'statement_month': '', 'month_label': '', 'version': 0, 'groups': [], 'group_count': 0,
             'summary_html': '', 'summary_file_name': '', 'month_total': '0.00', 'mark_sent': [], 'mark_sent_splits': [],
             'status_log': log, 'blockers': [], 'blocker_count': 0}
    if chosen is None:
        if not open_blockers:
            return empty
        m = sorted(open_blockers)[0]
        return dict(empty, statement_month=m, month_label=_month_name(m),
                    blockers=open_blockers[m], blocker_count=len(open_blockers[m]))

    rows = months[chosen]
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

    label = _month_name(chosen)
    out_groups = []
    for job in sorted(groups):
        g = groups[job]
        total = sum((i['_amt'] for i in g['items']), Decimal('0'))
        for i in g['items']:
            i.pop('_amt')
        lines = ['- %s | %s | %s | %s' % (i['transaction_id'], i['transaction_date'], i['merchant'], i['amount']) for i in g['items']]
        out_groups.append({
            'group_key': chosen + '|' + job, 'receipt_month': chosen, 'project_code': job, 'version': version,
            'file_name': 'Finance_Package_%s_%s.pdf' % (_safe(chosen), _safe(job)),
            'new_count': len(g['items']), 'previous_count': 0, 'total_count': len(g['items']),
            'new_total': '%.2f' % total, 'previous_total': '0.00', 'grand_total': '%.2f' % total,
            'changes_text': '\n'.join(lines),
            'changes_html': '<ul>' + ''.join('<li>%s</li>' % _h(x[2:]) for x in lines) + '</ul>',
            'receipt_ids': g['receipt_ids'], 'transactions': g['items'],
            'cover_html': _page('Job %s - %s' % (job, label), 'Credit card charges &nbsp;|&nbsp; Prepared %s' % _h(today), _grouped([x for x in cover_lines if x['job'] == job], False)),
            'new_transactions': [{k: i[k] for k in ('record_id', 'table', 'transaction_id', 'transaction_date', 'merchant',
                                                    'amount', 'cost_code', 'receipt_id')} for i in g['items']],
        })

    summary = _page('Credit card summary - %s' % label,
                    'Statement month %s &nbsp;|&nbsp; Prepared %s &nbsp;|&nbsp; %d job package%s attached'
                    % (_h(chosen), _h(today), len(out_groups), '' if len(out_groups) == 1 else 's'),
                    _grouped(cover_lines, True))
    return dict(empty, ready=True, statement_month=chosen, month_label=label, version=version, groups=out_groups,
                group_count=len(out_groups), summary_html=summary, month_total='%.2f' % month_total,
                summary_file_name='Card_Summary_%s' % _safe(chosen),
                mark_sent=mark, mark_sent_splits=mark_splits)
