# ============================================================================
# test_coding.py
#
# Coding that arrives after the receipt: replies, the open-items spreadsheet,
# and prior coding from history (design/credit-card-coding.md, Coding after
# the receipt). No real data.
#
#   python3 tests/test_coding.py
#
# The load-bearing cases are the ones that would code a charge wrongly with
# nobody told: a quoted line from the original email read as the reply's own
# answer, a sheet row with a typo'd reference applied to nothing silently, and
# a guess from history confirming itself. Each is a check below.
# ============================================================================

import base64
import importlib.util
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = os.path.join(HERE, '..', 'credit-card-coding')


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(STEPS, name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


reply = _load('read_coding_reply')
build = _load('build_coding_sheet')
read = _load('read_coding_sheet')
suggest = _load('suggest_coding')
open_items = _load('open_items')
batch = _load('batch_notifications')
split = _load('split_shares')
package = _load('group_finance_package')
cover = _load('split_finance_package')

T1 = '1234-20261029-606.00-14'
T2 = '1234-20261019-50.03-9'
R1 = 'R-31e28ed9-1f46-45c5-8d4a-848a0ba583cc'

RESULTS = []


def check(label, ok):
    RESULTS.append((label, bool(ok)))


def reply_checks():
    r = reply.main({'body': '%s: Perry, 01-750, e-signature plan\n%s - Kleeman; 02-100; lunch, site meeting\n\n'
                            'Pat\n\nFrom: APM\nSent: Monday\n%s  Uber  193.87  receipt' % (T1, T2, '1234-20261007-193.87-4')})
    u = {x['ref']: x for x in r['updates']}
    check('reply: one line per charge, positional', u[T1] == {'ref': T1, 'ref_type': 'transaction',
          'project_code': 'Perry', 'cost_code': '01-750', 'reason': 'e-signature plan', 'shares': []})
    check('reply: the reason keeps its own commas', u[T2]['reason'] == 'lunch, site meeting')
    check('reply: a charge only in the quoted email is not coded', len(u) == 2 and not r['needs_ai'])

    r = reply.main({'body': 'Project: Perry\nCost code: 01-750\nReason: annual plan\n\nOn Tue, APM wrote:\n> Ref: %s' % T1})
    check('reply: labelled coding applies to the one reference in the thread',
          r['updates'] == [{'ref': T1, 'ref_type': 'transaction', 'project_code': 'Perry',
                            'cost_code': '01-750', 'reason': 'annual plan', 'shares': []}])

    r = reply.main({'body': 'code this to Perry 01-750\n\n-----Original Message-----\nReceipt ref: %s' % R1})
    check('reply: free text with one reference goes to the AI step',
          r['needs_ai'] and r['single_ref'] == R1[2:] and r['single_ref_type'] == 'receipt'
          and r['new_text'] == 'code this to Perry 01-750')

    r = reply.main({'body': 'Perry 01-750\n\n> %s\n> %s' % (T1, T2)})
    check('reply: two references and no coded line is a question, not a guess',
          not r['updates'] and not r['needs_ai'] and '2 charges' in r['problems'])

    r = reply.main({'body': 'Perry, 01-750, plan'})
    check('reply: no reference anywhere is a question', not r['updates'] and 'No charge' in r['problems'])
    check('reply: an email with no reference says so, so the intake can treat it as a receipt', r['ref_count'] == 0)

    r = reply.main({'body': '%s: Perry, 01-750\n%s: Other, 99, x' % (T1, T1)})
    check('reply: fewer than three parts fill what is given',
          r['updates'][0]['reason'] == '' and r['updates'][0]['cost_code'] == '01-750')
    check('reply: a charge given twice keeps the first and says so',
          len(r['updates']) == 1 and 'more than once' in r['problems'])

    r = reply.main({'body': '%s.1: Perry, 01-750, plan' % T1})
    check('reply: a reference with more digits run on is not that reference', not r['updates'])


def sheet_checks():
    items = [{'transaction_id': T1, 'cardholder_name': 'PAT SAMPLE', 'transaction_date': '2026-10-29',
              'merchant': 'DOCUSIGN INC.', 'amount': '606.0', 'missing_summary': 'project_code, reason',
              'suggested_project_code': 'Perry', 'suggested_cost_code': '01-750', 'suggested_reason': ''},
             {'transaction_id': T2, 'cardholder_name': 'PAT SAMPLE', 'transaction_date': '2026-10-19',
              'merchant': 'GATES & CO <NYC>', 'amount': '50.03', 'missing_summary': 'receipt'}]
    b = build.main({'items_json': json.dumps(items), 'label': 'Pat Sample', 'today': '2026-11-04'})
    check('sheet: named for the cardholder and day', b['file_name'] == 'CC_Coding_Pat_Sample_20261104.xlsx')
    back = read.main({'file_content_base64': b['file_base64']})
    check('sheet: a sheet sent straight back reads as a coding sheet', back['is_coding_sheet'])
    check('sheet: suggestions are pre-filled, so returning it confirms them',
          back['updates'] == [{'ref': T1, 'ref_type': 'transaction', 'project_code': 'Perry',
                               'cost_code': '01-750', 'reason': '', 'shares': []}])
    check('sheet: a row with nothing filled in is left alone', back['rows_left_blank'] == 1)

    try:
        import openpyxl
    except ImportError:
        print('  note  openpyxl not installed: Excel re-save case skipped')
        return
    wb = openpyxl.load_workbook(io.BytesIO(base64.b64decode(b['file_base64'])))
    ws = wb.active
    check('sheet: opens in a spreadsheet with its header and rows',
          [c.value for c in ws[1]][:3] == ['Ref', 'Cardholder', 'Date'] and ws['D3'].value == 'GATES & CO <NYC>')
    ws['I2'] = 'annual plan'
    ws['G3'], ws['H3'], ws['I3'] = 'Kleeman', 2100, 'lunch'
    ws['A5'], ws['G5'] = '1234-2026-typo', 'X'
    buf = io.BytesIO()
    wb.save(buf)
    back = read.main({'file_content_base64': base64.b64encode(buf.getvalue()).decode()})
    u = {x['ref']: x for x in back['updates']}
    check('sheet: re-saved by a spreadsheet program, shared strings and all, still reads',
          u[T1]['reason'] == 'annual plan' and u[T2]['project_code'] == 'Kleeman')
    check('sheet: a cost code typed as a number reads without ".0"', u[T2]['cost_code'] == '2100')
    check('sheet: a reference that is not one is reported, not dropped', 'Row 5' in back['problems'])

    other = build.main({'items_json': '[]'})
    plain = openpyxl.Workbook()
    plain.active.append(['Date', 'Merchant', 'Amount'])
    buf = io.BytesIO()
    plain.save(buf)
    check('sheet: any other workbook is not a coding sheet',
          not read.main({'file_content_base64': base64.b64encode(buf.getvalue()).decode()})['is_coding_sheet']
          and other['row_count'] == 0)


def history_checks():
    def tx(rid, date, merchant, project='', cost='', reason='', source='', who='PAT SAMPLE'):
        return {'Record ID': rid, 'transaction_id': rid, 'transaction_date': date, 'merchant': merchant,
                'cardholder_name': who, 'amount': 1, 'project_code': project, 'cost_code': cost,
                'reason': reason, 'coding_source': source, 'matched': True, 'exempt': False}
    recs = [
        tx('a1', '2026-08-29', 'DOCUSIGN INC. 800-3799973 DE', 'Perry', '01-750', 'e-sign plan'),
        tx('a2', '2026-09-29', 'DocuSign Inc', 'Perry', '01-750', 'e-sign plan'),
        tx('a3', '2026-10-29', 'DOCUSIGN INC. 800-3799973 DE'),
        tx('b1', '2026-09-10', 'UBER *BUSINESS', 'Perry', '01-500', 'site visit'),
        tx('b2', '2026-09-20', 'UBER *BUSINESS', 'Oak St', '01-500', 'site visit'),
        tx('b3', '2026-10-07', 'UBER *BUSINESS HELP.UBER.COMCA'),
        tx('c1', '2026-09-01', 'APPLE.COM/BILL', 'Office', '99-100', 'phone', source='history'),
        tx('c2', '2026-09-15', 'APPLE.COM/BILL', 'Office', '99-100', 'phone', source='history'),
        tx('c3', '2026-10-03', 'APPLE.COM/BILL'),
        tx('d1', '2026-09-01', 'DOCUSIGN INC.', 'Elm', '03-000', 'x', who='SAM OTHER'),
        tx('d2', '2026-09-02', 'DOCUSIGN INC.', 'Elm', '03-000', 'x', who='SAM OTHER'),
        tx('e1', '2026-10-30', 'DOCUSIGN INC.', project='Maple'),
    ]
    out = suggest.main({'records_json': json.dumps(recs)})
    applied = {a['ref']: a for a in out['apply']}
    merged = {r['Record ID']: r for r in json.loads(out['records_json'])}
    check('history: two matching explicit codings apply, across merchant spellings',
          applied.get('a3', {}).get('project_code') == 'Perry' and applied['a3']['reason'] == 'e-sign plan')
    check('history: applied coding is marked as from history', merged['a3']['coding_source'] == 'history')
    check('history: disagreeing codings only suggest the latest',
          'b3' not in applied and merged['b3']['suggested_project_code'] == 'Oak St')
    check('history: coding from history never counts as evidence for more',
          'c3' not in applied and merged['c3']['suggestion'] == 'Office / 99-100 / phone')
    check('history: another cardholder\'s coding is not this one\'s', applied['a3']['project_code'] != 'Elm')
    check('history: a field the cardholder already gave is kept',
          applied.get('e1', {}).get('project_code') == 'Maple' and applied['e1']['cost_code'] == '01-750')
    check('history: counts', out['apply_count'] == 2 and out['suggested_count'] == 2)

    oi = open_items.main({'records_json': out['records_json']})
    items = {i['transaction_id']: i for g in oi['groups'] for i in g['items']}
    check('history: a charge coded from history is no longer an open item', 'a3' not in items)
    check('history: the digest carries a suggestion through', items['b3']['suggested_project_code'] == 'Oak St')
    check('history: merchant key ignores store numbers and filler',
          suggest.merchant_key('THE HOME DEPOT #1234 ATLANTA GA') == suggest.merchant_key('Home Depot'))


def batch_checks():
    def n(rid, to, kind, at, **kw):
        return dict({'Record ID': rid, 'recipient': to, 'kind': kind, 'Created time': at, 'ref': T1,
                     'merchant': 'DOCUSIGN <INC>', 'date': '2026-10-29', 'amount': 606, 'currency': 'USD'}, **kw)
    rows = [
        n('n1', 'Pat@Example.com', 'matched', '2026-11-04T10:00:00.000+00:00', project_code='Perry'),
        n('n2', 'pat@example.com', 'received', '2026-11-04T10:02:00Z', project_code='Perry', cost_code='01-750', reason='plan'),
        n('n3', 'pat@example.com', 'history', '2026-11-04T10:03:00Z', project_code='Perry', cost_code='01-750', reason='plan'),
        n('n4', 'sam@example.com', 'complete', '2026-11-04T10:08:30Z', project_code='Elm', cost_code='1', reason='x'),
        n('n5', 'lee@example.com', 'no_match', ''),
    ]
    out = batch.main({'notifications_json': json.dumps(rows), 'now': '2026-11-04T10:09:00Z', 'quiet_minutes': '5'})
    b = {x['recipient']: x for x in out['batches']}
    check('batch: one email per person, addresses compared without case',
          b['pat@example.com']['count'] == 3 and b['pat@example.com']['record_ids'] == ['n1', 'n2', 'n3'])
    check('batch: a person still sending waits for 5 quiet minutes', 'sam@example.com' not in b and out['waiting_count'] == 1)
    check('batch: a row with no readable time is sent, never held forever', 'lee@example.com' in b)
    h = b['pat@example.com']['html']
    check('batch: sections in a fixed order',
          h.index('Received') < h.index('Matched to') < h.index('Coded from your history'))
    check('batch: what is still needed is named', 'Still needed: cost code, reason' in h)
    check('batch: every line carries its reference', h.count('Ref: ' + T1) == 3)
    check('batch: merchant text is escaped', '&lt;INC&gt;' in h and '<INC>' not in h)
    check('batch: the reply format is explained when something is missing', 'Ref: project, cost code, reason' in h)
    check('batch: subject counts the updates and carries the tag', b['pat@example.com']['subject'] == '[CC] 3 card receipt updates')


def split_checks():
    def sh(project, cost, share, reason=''):
        return {'project_code': project, 'cost_code': cost, 'reason': reason, 'share': share}

    r = split.main({'charge_amount': 606, 'shares_json': json.dumps([sh('Perry', '01-750', '60%', 'plan'),
                                                                      sh('Oak St', '02-100', '40%', 'plan')])})
    check('split: percentages become dollars', r['ok'] and [x['amount'] for x in r['shares']] == [363.6, 242.4])
    check('split: a split may mix projects and cost codes',
          r['is_split'] and r['project_code'] == 'Split: Perry / Oak St' and r['cost_code'] == '01-750 / 02-100')
    check('split: the note names every share', r['split_note'] == 'Split: Perry 01-750 363.60; Oak St 02-100 242.40')

    r = split.main({'charge_amount': '100', 'shares_json': json.dumps([sh('A', '1', '33.33%', 'x')] * 2 + [sh('C', '1', '33.33%', 'x')])})
    check('split: the last percentage share takes the rounding cent',
          r['ok'] and [x['amount'] for x in r['shares']] == [33.33, 33.33, 33.34])

    r = split.main({'charge_amount': 606, 'shares_json': json.dumps([sh('Perry', '01-750', '$400', 'p'), sh('Oak', '01-750', '$200', 'p')])})
    check('split: dollar shares that do not add up apply nothing and say by how much',
          not r['ok'] and r['shares'] == [] and '600.00' in r['problems'] and '6.00 short' in r['problems'])

    r = split.main({'charge_amount': 606, 'shares_json': json.dumps([sh('Perry', '01-750', '$400'), sh('Oak', '', '$206')]),
                    'reason': 'e-sign plan'})
    check('split: a field blank on a share is filled from the charge, then from the one value given',
          r['ok'] and all(x['reason'] == 'e-sign plan' and x['cost_code'] == '01-750' for x in r['shares']))

    r = split.main({'charge_amount': 606, 'shares_json': json.dumps([sh('Perry', '01-750', '$400', 'a'), sh('Oak', '02-1', '$206', '')])})
    check('split: a reason given once and differently elsewhere is not guessed',
          r['ok'] and r['shares'][1]['reason'] == 'a')
    r = split.main({'charge_amount': 606, 'shares_json': json.dumps([sh('Perry', '01-750', '$400', 'a'), sh('Oak', '02-1', '$206', 'b'),
                                                                      sh('', '03-1', '$0', '')])})
    check('split: a share with no project is refused', not r['ok'] and 'Share 3 has no project' in r['problems'])

    r = split.main({'charge_amount': -50, 'shares_json': json.dumps([sh('A', '1', '$30', 'x'), sh('B', '1', '$20', 'x')])})
    check('split: a credit splits as a credit', r['ok'] and [x['amount'] for x in r['shares']] == [-30.0, -20.0])
    r = split.main({'charge_amount': 606, 'shares_json': json.dumps([sh('Perry', '01-750', 'most', 'x'), sh('B', '1', '$6', 'x')])})
    check('split: a share that is not $ or % is refused', not r['ok'] and 'Share 1 has no amount' in r['problems'])
    r = split.main({'charge_amount': 606, 'split_text': 'Perry | 01-750 | 60% | e-sign\nOak St | 01-750 | 40% | e-sign\n'})
    check('split: the AI step\'s lines are read', r['ok'] and r['shares'][1]['project_code'] == 'Oak St')
    r = split.main({'charge_amount': 606, 'shares_json': json.dumps([sh('Perry', '01-750', '$606', 'x')])})
    check('split: one share of the whole charge is ordinary coding', r['ok'] and not r['is_split'] and r['project_code'] == 'Perry')

    r = reply.main({'body': '%s: Perry, 01-750, $400, e-signature plan\n%s: Oak St, 02-100, 206.00 USD\n%s: Oak St, 02-100, $206.00' % (T1, T2, T1)})
    u = {x['ref']: x for x in r['updates']}
    check('split: two reply lines with shares for one charge are a split',
          [x['share'] for x in u[T1]['shares']] == ['$400', '$206.00'] and u[T1]['shares'][0]['reason'] == 'e-signature plan')
    check('split: a plain number is never read as a share in a reply', u[T2]['shares'] == [] and u[T2]['reason'] == '206.00 USD')
    r = reply.main({'body': '%s: Perry, 01-750, 60%%\n%s: Oak St, 01-750' % (T1, T1)})
    check('split: lines without a share on each are not a split', r['updates'][0]['shares'] == [] and 'without a share' in r['problems'])

    items = [{'transaction_id': T1, 'merchant': 'DOCUSIGN', 'amount': 606}]
    try:
        import openpyxl
    except ImportError:
        openpyxl = None
    if openpyxl:
        b = build.main({'items_json': json.dumps(items)})
        wb = openpyxl.load_workbook(io.BytesIO(base64.b64decode(b['file_base64'])))
        ws = wb.active
        check('split: the sheet has a Split share column', ws['J1'].value == 'Split share')
        ws['G2'], ws['H2'], ws['I2'], ws['J2'] = 'Perry', '01-750', 'plan', 400
        ws.append([T1, '', '', '', '', '', 'Oak St', '02-100', 'plan', '$206'])
        buf = io.BytesIO()
        wb.save(buf)
        back = read.main({'file_content_base64': base64.b64encode(buf.getvalue()).decode()})
        check('split: a charge on two sheet rows with shares is a split',
              [(x['project_code'], x['share']) for x in back['updates'][0]['shares']] == [('Perry', '400'), ('Oak St', '$206')])
        r = split.main({'charge_amount': 606, 'shares_json': json.dumps(back['updates'][0]['shares'])})
        check('split: a number typed in the sheet is dollars', r['ok'] and [x['amount'] for x in r['shares']] == [400.0, 206.0])

    txns = [{'Record ID': 't1', 'transaction_id': T1, 'matched': True, 'matched_receipt_id': 'r1', 'amount': 606,
             'merchant': 'DOCUSIGN', 'coding_source': 'split', 'project_code': 'Split: Perry / Oak St',
             'cost_code': '01-750 / 02-100', 'reason': 'plan'},
            {'Record ID': 't2', 'transaction_id': T2, 'matched': True, 'matched_receipt_id': 'r2', 'amount': 50.03,
             'merchant': 'GATES', 'coding_source': 'split', 'project_code': 'Split', 'cost_code': '1', 'reason': 'x'}]
    splits = [{'Record ID': 's1', 'transaction_id': T1, 'project_code': 'Perry', 'cost_code': '01-750', 'reason': 'plan', 'amount': 400},
              {'Record ID': 's2', 'transaction_id': T1, 'project_code': 'Oak St', 'cost_code': '02-100', 'reason': 'plan', 'amount': 206,
               'sent_in_package': True, 'package_version_sent': '1'},
              {'Record ID': 's3', 'transaction_id': T2, 'project_code': 'Perry', 'cost_code': '1', 'reason': 'x', 'amount': 40}]
    receipts = [{'Record ID': 'r1', 'receipt_month': '2026-10', 'project_code': '', 'receipt_number': 'INV1'},
                {'Record ID': 'r2', 'receipt_month': '2026-10', 'project_code': '', 'receipt_number': 'INV2'}]
    out = package.main({'transactions_json': json.dumps(txns), 'receipts_json': json.dumps(receipts),
                        'splits_json': json.dumps(splits), 'today': '2026-11-05'})
    g = {x['project_code']: x for x in out['groups']}
    perry = g['Perry']['transactions'][0]
    check('split: each share goes in its own project\'s package at its share',
          perry['amount'] == '400.00' and perry['table'] == 'splits' and perry['cost_code'] == '01-750')
    check('split: the receipt goes in every package its shares are in', g['Perry']['receipt_ids'] == ['r1'])
    check('split: the line says what it is a share of', perry['split_note'] == 'Split: 400.00 of 606.00 (also Oak St 02-100 206.00)')
    check('split: a share already sent is not new again', 'Oak St' not in g)
    check('split: shares that do not add up to the charge hold it', out['held_uncoded_count'] == 1
          and not any(i['transaction_id'] == T2 for x in out['groups'] for i in x['transactions']))
    c = cover.main({'transactions_json': json.dumps(g['Perry']['transactions']), 'included_receipt_ids_json': '["r1"]',
                    'excluded_json': '[]', 'receipt_cost_codes_json': '[]'})
    check('split: a sent share is marked on Splits, not on the charge',
          c['mark_sent'] == [] and c['mark_sent_splits'] == [{'record_id': 's1', 'transaction_id': T1}])
    check('split: the cover shows the share\'s cost code and note',
          '01-750' in c['cover_cost_code_totals_html'] and 'Split: 400.00 of 606.00' in c['cover_transactions_html'])

    hist = [dict(t, cardholder_name='PAT', transaction_date=d) for t, d in ((txns[0], '2026-08-01'), (txns[0], '2026-09-01'))]
    hist.append({'Record ID': 'new', 'transaction_id': 'new', 'merchant': 'DOCUSIGN', 'cardholder_name': 'PAT',
                 'transaction_date': '2026-10-01'})
    out = suggest.main({'records_json': json.dumps(hist)})
    check('split: a split charge never feeds the history rule', out['apply_count'] == 0 and out['suggested_count'] == 0)


def main():
    reply_checks()
    sheet_checks()
    history_checks()
    batch_checks()
    split_checks()
    failed = [label for label, ok in RESULTS if not ok]
    for label, ok in RESULTS:
        print(('  ok    ' if ok else '  FAIL  ') + label)
    print('%d checks, %d failed' % (len(RESULTS), len(failed)))
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
