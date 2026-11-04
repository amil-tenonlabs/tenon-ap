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
          'project_code': 'Perry', 'cost_code': '01-750', 'reason': 'e-signature plan'})
    check('reply: the reason keeps its own commas', u[T2]['reason'] == 'lunch, site meeting')
    check('reply: a charge only in the quoted email is not coded', len(u) == 2 and not r['needs_ai'])

    r = reply.main({'body': 'Project: Perry\nCost code: 01-750\nReason: annual plan\n\nOn Tue, APM wrote:\n> Ref: %s' % T1})
    check('reply: labelled coding applies to the one reference in the thread',
          r['updates'] == [{'ref': T1, 'ref_type': 'transaction', 'project_code': 'Perry',
                            'cost_code': '01-750', 'reason': 'annual plan'}])

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
                               'cost_code': '01-750', 'reason': ''}])
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


def main():
    reply_checks()
    sheet_checks()
    history_checks()
    batch_checks()
    failed = [label for label, ok in RESULTS if not ok]
    for label, ok in RESULTS:
        print(('  ok    ' if ok else '  FAIL  ') + label)
    print('%d checks, %d failed' % (len(RESULTS), len(failed)))
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
