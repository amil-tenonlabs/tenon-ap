# ============================================================================
# test_month_close.py
#
# month_close.py: a statement month goes to finance only when every charge on
# it is complete - a receipt or exempt, and coded - as one summary cover by
# cardholder and job plus one package per job. No real data.
#
#   python3 tests/test_month_close.py
#
# The load-bearing cases: one open charge holds the whole month; a month that
# is complete goes even while an earlier one is open; the summary's grand total
# is every charge, credits and split shares included; and a month changed after
# it was sent goes again whole, as the next version.
# ============================================================================

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, '..', 'credit-card-coding', name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


close = _load('month_close')
cover = _load('split_finance_package')

RESULTS = []


def check(label, ok):
    RESULTS.append((label, bool(ok)))


def tx(tid, holder, amount, month='2026-10', matched=True, receipt='', exempt=False, project='Perry',
       cost='01-750', reason='supplies', **kw):
    return dict({'Record ID': 'rec-' + tid, 'transaction_id': tid, 'cardholder_name': holder, 'amount': amount,
                 'transaction_date': month + '-15', 'merchant': 'M ' + tid, 'statement_month': month,
                 'matched': matched, 'matched_receipt_id': receipt, 'exempt': exempt,
                 'project_code': project, 'cost_code': cost, 'reason': reason}, **kw)


RECEIPTS = [{'Record ID': 'r1', 'receipt_number': 'INV-1'}, {'Record ID': 'r2', 'receipt_number': 'INV-2'},
            {'Record ID': 'r3', 'receipt_number': 'INV-3'}, {'Record ID': 'r9', 'receipt_number': 'INV-9'}]
SPLITS = [{'Record ID': 's1', 'transaction_id': 'A3', 'project_code': 'Perry', 'cost_code': '01-750', 'reason': 'plan', 'amount': 400},
          {'Record ID': 's2', 'transaction_id': 'A3', 'project_code': 'Oak St', 'cost_code': '02-100', 'reason': 'plan', 'amount': 206}]
OCT = [tx('A1', 'PAT SAMPLE', 50.03, receipt='r1'),
       tx('A2', 'PAT SAMPLE', 3.00, matched=False, exempt=True, project='Office', cost='99-100', reason='transit'),
       tx('A3', 'PAT SAMPLE', 606, receipt='r2', coding_source='split', project='Split: Perry / Oak St', cost='01-750 / 02-100', reason='plan'),
       tx('B1', 'SAM OTHER', -20, receipt='r3', project='Oak St', cost='02-100', reason='return')]


def run(txns, splits=SPLITS, **kw):
    return close.main(dict({'transactions_json': json.dumps(txns), 'receipts_json': json.dumps(RECEIPTS),
                            'splits_json': json.dumps(splits), 'today': '2026-11-05'}, **kw))


def main():
    r = run(OCT)
    g = {x['project_code']: x for x in r['groups']}
    check('a complete month is ready', r['ready'] and r['statement_month'] == '2026-10')
    check('one package per job, split shares in each of their jobs', sorted(g) == ['Oak St', 'Office', 'Perry'])
    check('a job\'s total is its charges and shares', g['Perry']['grand_total'] == '450.03' and g['Oak St']['grand_total'] == '186.00')
    check('the month total is every charge, credits and shares included', r['month_total'] == '639.03')
    check('a job\'s receipts are attached to its package', g['Perry']['receipt_ids'] == ['r1', 'r2'] and g['Oak St']['receipt_ids'] == ['r2', 'r3'])
    office = g['Office']['transactions'][0]
    check('an exempt charge is in its job with no receipt needed',
          office['no_receipt_needed'] is True and office['receipt_id'] == '' and office['receipt_number'] == 'Not required (exempt)')
    h = r['summary_html']
    check('the summary groups by job, then cost code',
          h.index('Job Oak St<') < h.index('Cost code 02-100<') < h.index('Job Office<') < h.index('Job Perry<')
          < h.index('Cost code 01-750<'))
    check('each transaction is listed by name with its amount', 'M A1' in h and '$50.03' in h and 'M B1' in h and '-$20.00' in h)
    check('cost code, job and month totals', 'Cost code 01-750 total' in h and 'Job Perry total</td>' in h
          and '$450.03' in h and 'Total, all jobs' in h and '$639.03' in h)
    check('a split share and an exempt charge say what they are',
          'Split: $400.00 of $606.00' in h and 'exempt, no receipt' in h)
    perry = g['Perry']['cover_html']
    check('a job cover holds only its own job, with its total and no month total',
          'Job Perry total' in perry and 'Oak St' not in perry.replace('also Oak St', '') and 'Total, all jobs' not in perry)
    check('the summary is titled with the month', 'Credit card summary - October 2026' in h)
    check('charges and split shares are each marked sent where they live',
          sorted(x['record_id'] for x in r['mark_sent']) == ['rec-A1', 'rec-A2', 'rec-B1']
          and sorted(x['record_id'] for x in r['mark_sent_splits']) == ['s1', 's2'])
    check('file names carry month and job, no version', g['Oak St']['file_name'] == 'Finance_Package_2026-10_Oak-St.pdf'
          and r['summary_file_name'] == 'Card_Summary_2026-10')
    check('no version on either cover', 'Version' not in r['summary_html'] and 'Version' not in g['Perry']['cover_html'])

    r = run(OCT + [tx('B2', 'SAM OTHER', 75, matched=False)])
    check('one charge with no receipt holds the whole month', not r['ready'] and r['groups'] == [] and r['mark_sent'] == [])
    check('what holds it is named', r['blocker_count'] == 1 and r['blockers'][0]['transaction_id'] == 'B2'
          and r['blockers'][0]['missing'] == 'receipt')

    sep = [tx('C1', 'PAT SAMPLE', 10, month='2026-09', receipt='r9')]
    r = run(OCT + [tx('B2', 'SAM OTHER', 75, matched=False)] + sep)
    check('a complete month goes while a later one is open', r['ready'] and r['statement_month'] == '2026-09')
    r = run(sep + [tx('B2', 'SAM OTHER', 75, matched=False)] + OCT)
    check('the oldest complete month goes first whatever the row order', r['statement_month'] == '2026-09')

    for label, extra, want in (
            ('a charge with no cost code', tx('B3', 'SAM OTHER', 5, receipt='r3', cost=''), 'cost code'),
            ('history coding applied today', tx('B4', 'SAM OTHER', 5, receipt='r3', coding_source='history', history_coded_on='2026-11-05'), 'a day for'),
            ('a receipt record that cannot be found', tx('B5', 'SAM OTHER', 5, receipt='gone'), 'receipt record'),
    ):
        r = run(OCT + [extra])
        check('%s holds the month' % label, not r['ready'] and want in r['blockers'][0]['missing'])
    r = run(OCT, splits=SPLITS[:1])
    check('split shares that do not add up hold the month', not r['ready'] and 'add up' in r['blockers'][0]['missing'])

    sent = [dict(t, sent_in_package=True, package_version_sent='1') for t in OCT]
    sent_splits = [dict(s, sent_in_package=True, package_version_sent='1') for s in SPLITS]
    r = run(sent, splits=sent_splits)
    check('a month already sent is not sent again', not r['ready'] and r['blocker_count'] == 0 and 'already sent' in r['status_log'])
    r = run(sent + [tx('B6', 'SAM OTHER', 12, receipt='r3', project='Oak St', cost='02-100', reason='late row')], splits=sent_splits)
    check('a month changed after it was sent goes again whole, under the same names',
          r['ready'] and sum(x['total_count'] for x in r['groups']) == 6
          and r['summary_file_name'] == 'Card_Summary_2026-10')

    g = {x['project_code']: x for x in run(OCT)['groups']}
    c = cover.main({'transactions_json': json.dumps(g['Office']['transactions']), 'included_receipt_ids_json': '[]',
                    'excluded_json': '[]', 'receipt_cost_codes_json': '[]'})
    check('a job of exempt charges only is sent as a cover with no files',
          c['send_package'] and not c['has_files'] and c['included_count'] == 1 and c['held_back_count'] == 0)
    c = cover.main({'transactions_json': json.dumps(g['Perry']['transactions']), 'included_receipt_ids_json': '["r1"]',
                    'excluded_json': '[{"receipt_id": "r2", "reason": "Image conversion to PDF failed"}]', 'receipt_cost_codes_json': '[]'})
    check('a receipt whose file cannot be used is held back and reported', c['held_back_count'] == 1 and 'r2' in c['flagged_text'] + json.dumps(c['flagged_receipts']))

    failed = [label for label, ok in RESULTS if not ok]
    for label, ok in RESULTS:
        print(('  ok    ' if ok else '  FAIL  ') + label)
    print('%d checks, %d failed' % (len(RESULTS), len(failed)))
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
