import json
import html


def _s(v):
    return str(v).strip() if v is not None else ''


def _amt(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _h(v):
    return html.escape(_s(v), quote=True)


def _load(v):
    try:
        return json.loads(v or '[]') or []
    except Exception:
        return []


def _table(headers, rows, right=()):
    out = '<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;width:100%">'
    out += '<tr>' + ''.join('<th>%s</th>' % _h(x) for x in headers) + '</tr>'
    for r in rows:
        out += '<tr>' + ''.join('<td%s>%s</td>' % (' style="text-align:right"' if i in right else '', _h(v)) for i, v in enumerate(r)) + '</tr>'
    return out + '</table>'


def main(input):
    txns = _load(input.get('transactions_json'))
    included_ids = [_s(x) for x in _load(input.get('included_receipt_ids_json')) if _s(x)]
    inc = set(included_ids)
    excluded = _load(input.get('excluded_json'))
    cost_codes = {}
    for r in _load(input.get('receipt_cost_codes_json')):
        if isinstance(r, list) and len(r) >= 2:
            cost_codes[_s(r[0])] = _s(r[1])
        elif isinstance(r, dict):
            cost_codes[_s(r.get('Record ID'))] = _s(r.get('cost_code'))

    def _cc(t):
        return _s(t.get('cost_code')) or cost_codes.get(_s(t.get('receipt_id'))) or '(none)'

    def _merchant(t):
        note = _s(t.get('split_note'))
        return _s(t.get('merchant')) + (' - ' + note if note else '')

    flagged = {}
    for e in excluded:
        rid = _s(e.get('receipt_id'))
        flagged[rid] = {k: _s(e.get(k)) for k in ('receipt_id', 'receipt_number', 'merchant', 'amount', 'file_name', 'reason')}
        flagged[rid]['_txns'] = []

    included, held = [], []
    for t in txns:
        rid = _s(t.get('receipt_id'))
        if (rid and rid in inc) or (not rid and t.get('no_receipt_needed') is True):
            included.append(t)
            continue
        held.append(t)
        if rid not in flagged:
            # receipt id on the transaction did not come back from the Receipts search
            flagged[rid] = {'receipt_id': rid or '-', 'receipt_number': _s(t.get('receipt_number')), 'merchant': '', 'amount': '', 'file_name': '(no file)', 'reason': 'Receipt record not found in Receipts table', '_txns': []}
        flagged[rid]['_txns'].append('%s%s' % (_s(t.get('transaction_id')), '' if t.get('is_new') else ' (previously sent)'))

    new_inc = [t for t in included if t.get('is_new')]
    prev_inc = [t for t in included if not t.get('is_new')]
    held_new = [t for t in held if t.get('is_new')]

    flagged_list = []
    for rid, f in flagged.items():
        f['held_back_transactions'] = ', '.join(f.pop('_txns')) or '-'
        flagged_list.append(f)

    if flagged_list:
        flagged_text = '\n'.join('- Receipt %s (%s, %s, file: %s): %s - transactions held back: %s' % (f['receipt_number'] or f['receipt_id'], f['merchant'] or '-', f['amount'] or '-', f['file_name'] or '-', f['reason'], f['held_back_transactions']) for f in flagged_list)
        flagged_html = '<ul>' + ''.join('<li><b>Receipt %s</b> (%s, %s, file: %s): %s &mdash; transactions held back: %s</li>' % (_esc(f['receipt_number'] or f['receipt_id']), _esc(f['merchant'] or '-'), _esc(f['amount'] or '-'), _esc(f['file_name'] or '-'), _esc(f['reason']), _esc(f['held_back_transactions'])) for f in flagged_list) + '</ul>'
    else:
        flagged_text = 'None - all backup files were included.'
        flagged_html = '<p>None - all backup files were included.</p>'

    changes_text = '\n'.join('- %s | %s | %s | %s' % (_s(t.get('transaction_id')), _s(t.get('transaction_date')), _merchant(t), _s(t.get('amount'))) for t in new_inc)
    changes_html = '<ul>' + ''.join('<li><b>%s</b> - %s - %s - %s</li>' % (_esc(_s(t.get('transaction_id'))), _esc(_s(t.get('transaction_date'))), _esc(_merchant(t)), _esc(_s(t.get('amount')))) for t in new_inc) + '</ul>'

    # ---- cover page HTML (values HTML-escaped, amounts to 2 decimals) ----
    cc_tot = {}
    for t in included:
        c = _cc(t)
        n, a = cc_tot.get(c, (0, 0.0))
        cc_tot[c] = (n + 1, a + _amt(t.get('amount')))
    cc_rows = [[c, str(cc_tot[c][0]), '%.2f' % cc_tot[c][1]] for c in sorted(cc_tot.keys())]
    cc_rows.append(['Total', str(len(included)), '%.2f' % sum(_amt(t.get('amount')) for t in included)])
    cover_cost_code_totals_html = _table(['Cost code', 'Transactions', 'Total'], cc_rows, right=(1, 2))

    cover_changes_html = _table(
        ['Date', 'Transaction ID', 'Merchant', 'Cardholder', 'Amount', 'Receipt number', 'Cost code'],
        [[t.get('transaction_date'), t.get('transaction_id'), _merchant(t), t.get('cardholder_name'), '%.2f' % _amt(t.get('amount')), t.get('receipt_number'), _cc(t)] for t in new_inc],
        right=(4,)) if new_inc else ''

    def _status(t):
        if t.get('is_new'):
            return 'New'
        pv = _s(t.get('previous_version'))
        return 'Previously sent (v%s)' % pv if pv else 'Previously sent'

    cover_transactions_html = _table(
        ['Date', 'Merchant', 'Cardholder', 'Amount', 'Receipt number', 'Cost code', 'Status'],
        [[t.get('transaction_date'), _merchant(t), t.get('cardholder_name'), '%.2f' % _amt(t.get('amount')), t.get('receipt_number'), _cc(t), _status(t)] for t in included],
        right=(3,))

    cover_flagged_html = _table(
        ['Receipt number', 'Merchant', 'Amount', 'File', 'Reason', 'Held-back transactions'],
        [[f['receipt_number'] or f['receipt_id'], f['merchant'] or '-', f['amount'] or '-', f['file_name'] or '-', f['reason'], f['held_back_transactions']] for f in flagged_list]) if flagged_list else ''

    file_count = len(included_ids)
    send = len(new_inc) > 0 and (file_count > 0 or all(t.get('no_receipt_needed') is True for t in new_inc))
    log = 'Included files: %d | included transactions: %d (%d new) | excluded receipts: %d | held-back transactions: %d (%d new, stay unsent) | send package: %s' % (file_count, len(included), len(new_inc), len(flagged_list), len(held), len(held_new), 'YES' if send else 'NO (no new transaction with a usable receipt file)')
    if flagged_list:
        log += '\nFLAGGED receipts:\n' + flagged_text

    keys = ('record_id', 'table', 'transaction_id', 'transaction_date', 'merchant', 'split_note', 'amount', 'cost_code', 'cardholder_name', 'receipt_number', 'status', 'is_new')
    return {
        'send_package': send,
        'has_files': file_count > 0,
        'included_file_count': file_count,
        'included_count': len(included),
        'included_total': '%.2f' % sum(_amt(t.get('amount')) for t in included),
        'included_new_count': len(new_inc),
        'included_new_total': '%.2f' % sum(_amt(t.get('amount')) for t in new_inc),
        'included_previous_count': len(prev_inc),
        'included_previous_total': '%.2f' % sum(_amt(t.get('amount')) for t in prev_inc),
        'included_changes_text': changes_text,
        'included_changes_html': changes_html,
        'excluded_receipt_count': len(flagged_list),
        'held_back_count': len(held),
        'held_back_new_count': len(held_new),
        'flagged_text': flagged_text,
        'flagged_html': flagged_html,
        'summary_log': log,
        'cover_cost_code_totals_html': cover_cost_code_totals_html,
        'cover_changes_html': cover_changes_html,
        'cover_transactions_html': cover_transactions_html,
        'cover_flagged_html': cover_flagged_html,
        'included_transactions': [{k: t.get(k) for k in keys} for t in included],
        'flagged_receipts': flagged_list,
        'mark_sent': [{'record_id': _s(t.get('record_id')), 'transaction_id': _s(t.get('transaction_id'))} for t in new_inc if _s(t.get('table')) != 'splits'],
        'mark_sent_splits': [{'record_id': _s(t.get('record_id')), 'transaction_id': _s(t.get('transaction_id'))} for t in new_inc if _s(t.get('table')) == 'splits'],
    }
