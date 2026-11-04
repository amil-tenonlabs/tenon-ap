import json
import re
from datetime import date


def _norm(v):
    return (str(v).strip() if v is not None else '')


def _amt(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _ver(v):
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return 0


def _safe(s):
    return re.sub(r'[^A-Za-z0-9_-]+', '-', s).strip('-') or 'NA'


def _esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def _true(v):
    return v is True or str(v).lower() == 'true'


def main(input):
    txns = json.loads(input.get('transactions_json') or '[]') or []
    rows = json.loads(input.get('receipts_json') or '[]') or []
    # receipts pluck order: Record ID, receipt_month, project_code, receipt_number, merchant, amount, currency
    receipts = {}
    for r in rows:
        if isinstance(r, dict):
            rid = _norm(r.get('Record ID'))
            receipts[rid] = {'receipt_month': _norm(r.get('receipt_month')), 'project_code': _norm(r.get('project_code')), 'receipt_number': _norm(r.get('receipt_number'))}
        elif isinstance(r, list) and len(r) >= 4:
            receipts[_norm(r[0])] = {'receipt_month': _norm(r[1]), 'project_code': _norm(r[2]), 'receipt_number': _norm(r[3])}

    splits = {}
    for sh in json.loads(input.get('splits_json') or '[]') or []:
        splits.setdefault(_norm(sh.get('transaction_id')), []).append(sh)

    groups = {}
    log = []
    skipped = 0
    held_uncoded = 0
    today = _norm(input.get('today'))[:10] or date.today().isoformat()
    new_count = 0
    for t in txns:
        if t.get('matched') is not True and str(t.get('matched')).lower() != 'true':
            continue
        tid = _norm(t.get('transaction_id')) or _norm(t.get('Record ID'))
        is_sent = _true(t.get('sent_in_package'))
        rid = _norm(t.get('matched_receipt_id'))
        rec = receipts.get(rid)
        if not rec or not rec['receipt_month']:
            skipped += 1
            log.append('Transaction %s: %s - SKIPPED (matched receipt %s not found or has no receipt_month; stays pending)' % (tid, 'PREVIOUSLY SENT' if is_sent else 'NOT YET SENT', rid or '-'))
            continue
        source = _norm(t.get('coding_source')).lower()
        if source == 'split':
            shares = splits.get(tid, [])
            total = sum(_amt(sh.get('amount')) for sh in shares)
            if not shares:
                held_uncoded += 1
                log.append('Transaction %s: HELD (marked split but no split shares were found)' % tid)
                continue
            if abs(total - _amt(t.get('amount'))) > 0.005:
                held_uncoded += 1
                log.append('Transaction %s: HELD (split shares total %.2f, the charge is %.2f)' % (tid, total, _amt(t.get('amount'))))
                continue
            entries = []
            for sh in shares:
                others = '; '.join('%s %s %.2f' % (_norm(o.get('project_code')), _norm(o.get('cost_code')), _amt(o.get('amount')))
                                   for o in shares if o is not sh)
                entries.append({'record_id': _norm(sh.get('Record ID')), 'table': 'splits', 'sent': _true(sh.get('sent_in_package')),
                                'version': sh.get('package_version_sent'), 'project_code': _norm(sh.get('project_code')),
                                'cost_code': _norm(sh.get('cost_code')), 'reason': _norm(sh.get('reason')),
                                'amount': _amt(sh.get('amount')),
                                'split_note': 'Split: %.2f of %.2f (also %s)' % (_amt(sh.get('amount')), _amt(t.get('amount')), others)})
        else:
            entries = [{'record_id': _norm(t.get('Record ID')), 'table': 'transactions', 'sent': is_sent,
                        'version': t.get('package_version_sent'), 'project_code': _norm(t.get('project_code')),
                        'cost_code': _norm(t.get('cost_code')), 'reason': _norm(t.get('reason')),
                        'amount': _amt(t.get('amount')), 'split_note': ''}]
        unsent = [e for e in entries if not e['sent']]
        blank = sorted(set(f for e in unsent for f in ('project_code', 'cost_code', 'reason') if not e[f]))
        coded_on = _norm(t.get('history_coded_on'))[:10]
        if blank:
            held_uncoded += 1
            log.append('Transaction %s: NOT YET SENT - HELD (no %s; stays pending until coded)' % (tid, ', '.join(blank)))
            continue
        if unsent and source == 'history' and (not coded_on or coded_on >= today):
            held_uncoded += 1
            log.append('Transaction %s: NOT YET SENT - HELD (coded from history on %s; sent once a digest has shown it)' % (tid, coded_on or 'an unknown date'))
            continue
        month = rec['receipt_month']
        for e in entries:
            code = e['project_code'] or rec['project_code'] or 'Unassigned'
            key = month + '|' + code
            g = groups.setdefault(key, {'receipt_month': month, 'project_code': code, 'max_ver': 0, 'items': [], 'receipt_ids': []})
            item = {
                'record_id': e['record_id'],
                'table': e['table'],
                'transaction_id': tid,
                'transaction_date': _norm(t.get('transaction_date')),
                'merchant': _norm(t.get('merchant')),
                'amount': '%.2f' % e['amount'],
                'cost_code': e['cost_code'],
                'split_note': e['split_note'],
                'cardholder_name': _norm(t.get('cardholder_name')),
                'receipt_number': rec['receipt_number'],
                'receipt_id': rid,
                'is_new': not e['sent'],
                'status': 'Previously sent (v%s)' % _norm(e['version']) if e['sent'] else 'NEW - what changed',
                'previous_version': _norm(e['version']) if e['sent'] else '',
                '_amt': e['amount'],
            }
            if e['sent']:
                g['max_ver'] = max(g['max_ver'], _ver(e['version']))
            g['items'].append(item)
            if rid and rid not in g['receipt_ids']:
                g['receipt_ids'].append(rid)
            log.append('Transaction %s%s [%s x %s]: %s' % (tid, ' (split share)' if e['table'] == 'splits' else '', month, code,
                       ('PREVIOUSLY SENT in v%s' % item['previous_version']) if e['sent'] else 'NOT PREVIOUSLY SENT (new)'))

    out = []
    for key in sorted(groups.keys()):
        g = groups[key]
        new_items = [i for i in g['items'] if i['is_new']]
        if not new_items:
            continue
        prev_items = [i for i in g['items'] if not i['is_new']]
        new_count += len(new_items)
        version = g['max_ver'] + 1
        new_total = sum(i['_amt'] for i in new_items)
        prev_total = sum(i['_amt'] for i in prev_items)
        changes_text = '\n'.join('- %s | %s | %s | %s' % (i['transaction_id'], i['transaction_date'], i['merchant'] + (' - ' + i['split_note'] if i['split_note'] else ''), i['amount']) for i in new_items)
        changes_html = '<ul>' + ''.join('<li><b>%s</b> - %s - %s - %s</li>' % (_esc(i['transaction_id']), _esc(i['transaction_date']), _esc(i['merchant'] + (' - ' + i['split_note'] if i['split_note'] else '')), _esc(i['amount'])) for i in new_items) + '</ul>'
        for i in g['items']:
            i.pop('_amt', None)
        out.append({
            'group_key': key,
            'receipt_month': g['receipt_month'],
            'project_code': g['project_code'],
            'version': version,
            'file_name': 'Finance_Package_%s_%s_v%d.pdf' % (_safe(g['receipt_month']), _safe(g['project_code']), version),
            'new_count': len(new_items),
            'previous_count': len(prev_items),
            'total_count': len(g['items']),
            'new_total': '%.2f' % new_total,
            'previous_total': '%.2f' % prev_total,
            'grand_total': '%.2f' % (new_total + prev_total),
            'changes_text': changes_text,
            'changes_html': changes_html,
            'receipt_ids': g['receipt_ids'],
            'transactions': g['items'],
            'new_transactions': [{k: i[k] for k in ('record_id', 'table', 'transaction_id', 'transaction_date', 'merchant', 'amount', 'cost_code', 'receipt_id')} for i in new_items],
        })

    return {'new_count': new_count, 'skipped_count': skipped, 'transaction_log': '\n'.join(log), 'groups': out, 'held_uncoded_count': held_uncoded}
