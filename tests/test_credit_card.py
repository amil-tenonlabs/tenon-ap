# ============================================================================
# test_credit_card.py
#
# The Credit Card Coding project's Python steps, run against a statement built
# in memory. No real data.
#
#   python3 tests/test_credit_card.py
#
# parse_statement.py is the step everything downstream trusts: a row it drops
# never reaches matching, and a date it gets wrong matches the wrong receipt.
# So the statement here carries what a real bank export does - title rows
# above the header, a repeated page header, a totals row, a credit, and a
# December charge on a January statement, which must land in the year before.
# Each step runs twice: through openpyxl when it is installed, and through the
# zipfile reader that Workato falls back to when it is not.
#
# KNOWN GAP checks pin behaviour that is wrong today (design/credit-card-coding.md,
# Findings). When the step is fixed, that check fails and should be turned around.
# ============================================================================

import importlib.util
import io
import os
import sys
import zipfile
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = os.path.join(HERE, '..', 'credit-card-coding')


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(STEPS, name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


parse_statement = _load('parse_statement')
open_items = _load('open_items')
group_finance_package = _load('group_finance_package')

FILE_NAME = 'PAT SAMPLE_4111xxxxxxxx1234_1_20270105.xlsx'

HEADER = ['Posting Date', 'Transaction Date', 'Description', 'Reference Number', 'MCC', 'Charge', 'Credit']
ROWS = [
    ['Card Services', None, None, None, None, None, None],
    ['Statement closing 01/05/2027', None, None, None, None, None, None],
    [],
    HEADER,
    ['12/29', '12/28', 'THE HOME DEPOT #1234', '7001', '5200', '182.40', None],
    ['01/03', '01/02', 'UBER *TRIP HELP.UBER.COM', '7002', '4121', '23.10', None],
    ['01/04', '01/03', 'COFFEE CART', '7003', '5814', '9.50', None],
    HEADER,
    ['01/04', '01/04', 'THE HOME DEPOT RETURN', '7004', '5200', None, '(45.00)'],
    ['Total', None, None, None, None, '215.00', '45.00'],
]

# A bank export converted from PDF: page 1 in columns, page 2's header and rows
# each packed into a single cell, the rows one per line, out of column alignment.
PACKED = [
    ['Commercial Card', None, None, 'PAT SAMPLE\nOctober 01, 2026 - October 31, 2026', None, None, None, None, None],
    [' Total Activity                                   $1,826.90 ', None, None, None, None, None, None, None, None],
    ['Posting Transaction', None, None, None, None, None, None, None, None],
    ['Date', 'Date', 'Description', None, 'Reference Number', None, 'MCC', 'Charge', 'Credit'],
    ['10/05', '10/01', 'THE HOME DEPOT #1234     ATLANTA      GA', None, 2.4692166275407714e+22, None, 5200, 182.40, None],
    [' Transactions', None, None, None, None, None, None, None, None],
    ['Date     Date           Description                       Reference Number      MCC      Charge      Credit',
     None, None, None, None, None, None, None, None],
    ['10/26    10/22          CURB TAXI                ASTORIA      NY      24055236296941234311381    4121       13.50\n'
     '10/30    10/29          SIGNING SERVICE          800-555-0100 DE      24793386302003604307226    5817    1,606.00\n'
     '10/31    10/31          HARDWARE RETURN          800-555-0101 NY      24793386302003604307227    5200       25.00',
     None, None, None, None, None, None, None, None],
]

RULES = [
    {'rule_type': 'vendor', 'value': '  Uber ', 'active': 'true'},
    {'rule_type': 'max_amount', 'value': '10', 'active': None},
    {'rule_type': 'vendor', 'value': 'home depot', 'active': 'false'},
    {'rule_type': 'max_amount', 'value': 'ten dollars', 'active': 'true'},
]


def _xlsx(rows):
    def cell(ref, v):
        if v is None:
            return ''
        return '<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (ref, escape(str(v)))

    def col(i):
        return chr(65 + i)

    sheet = ''.join(
        '<row r="%d">%s</row>' % (r + 1, ''.join(cell('%s%d' % (col(i), r + 1), v) for i, v in enumerate(row)))
        for r, row in enumerate(rows))
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    files = {
        '[Content_Types].xml':
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '</Types>',
        '_rels/.rels':
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="%s/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>' % rel,
        'xl/workbook.xml':
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="%s" xmlns:r="%s"><sheets>'
            '<sheet name="Transactions" sheetId="1" r:id="rId1"/>'
            '</sheets></workbook>' % (ns, rel),
        'xl/_rels/workbook.xml.rels':
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="%s/worksheet" Target="worksheets/sheet1.xml"/>'
            '</Relationships>' % rel,
        'xl/worksheets/sheet1.xml':
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="%s"><sheetData>%s</sheetData></worksheet>' % (ns, sheet),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, body in files.items():
            z.writestr(name, body)
    return buf.getvalue()


def _parse(rows, reader, rules=None, name=FILE_NAME):
    import base64
    saved = sys.modules.get('openpyxl', 'absent')
    if reader == 'zipfile':
        sys.modules['openpyxl'] = None
    try:
        return parse_statement.main({
            'file_name': name,
            'file_content_base64': base64.b64encode(_xlsx(rows)).decode(),
            'exemption_rules': RULES if rules is None else rules,
        })
    finally:
        if saved == 'absent':
            sys.modules.pop('openpyxl', None)
        else:
            sys.modules['openpyxl'] = saved


RESULTS = []


def check(label, ok):
    RESULTS.append((label, bool(ok)))


def readers():
    out = ['zipfile']
    try:
        import openpyxl  # noqa: F401
        out.append('openpyxl')
    except ImportError:
        print('  note  openpyxl not installed: zipfile reader only')
    return out


def statement_checks():
    for reader in readers():
        r = _parse(ROWS, reader)
        t = r['transactions']
        tag = '[%s] ' % reader
        check(tag + 'statement month from the file name', r['statement_month'] == '2027-01')
        check(tag + 'cardholder is the text before the first underscore', r['cardholder_name'] == 'PAT SAMPLE')
        check(tag + 'card_last4 from the masked card number', r['card_last4'] == '1234')
        check(tag + 'header found below the title rows', r['header_row'] == 4)
        check(tag + 'four transactions; repeated header and totals skipped',
              len(t) == 4 and r['skipped_count'] == 2)
        check(tag + 'a December charge on a January statement is the year before',
              t[0]['transaction_date'] == '2026-12-28')
        check(tag + 'transaction date is the second date, not posting', t[1]['transaction_date'] == '2027-01-02')
        check(tag + 'a credit in brackets is negative', t[3]['amount'] == -45.0)
        check(tag + 'vendor rule: trimmed, case-insensitive contains', t[1]['exempt'] is True)
        check(tag + 'max_amount rule: a charge strictly below the threshold', t[2]['exempt'] is True)
        check(tag + 'inactive rule is not applied', t[0]['exempt'] is False)
        check(tag + 'a credit is never amount-exempt', t[3]['exempt'] is False)
        check(tag + 'non-numeric max_amount is ignored with a warning',
              r['ignored_rule_count'] == 1 and 'ten dollars' in r['rule_warnings'])
        check(tag + 'transaction_id is card-date-amount-sequence',
              t[0]['transaction_id'] == '1234-20261228-182.40-1')

        check(tag + 'no Total Activity on the sheet: a warning, nothing refused',
              'No "Total Activity"' in r['total_warning'] and r['parsed_total'] == '170.00')

        p = _parse(PACKED, reader)
        pt = p['transactions']
        check(tag + 'a page packed into one cell: every line is a transaction',
              [x['merchant'] for x in pt] == ['THE HOME DEPOT #1234 ATLANTA GA', 'CURB TAXI ASTORIA NY',
                                              'SIGNING SERVICE 800-555-0100 DE', 'HARDWARE RETURN 800-555-0101 NY'])
        check(tag + 'packed lines keep their own transaction date and amount',
              [(x['transaction_date'], x['amount']) for x in pt[1:3]] == [('2026-10-22', 13.5), ('2026-10-29', 1606.0)])
        check(tag + 'a packed line with one amount is a charge: position cannot show a credit',
              len(pt) == 4 and pt[3]['amount'] == 25.0)
        check(tag + 'Total Activity agrees: no warning', p['statement_total'] == '1826.90' and p['total_warning'] == '')
        short = [row[:] for row in PACKED]
        short[-1] = [short[-1][0].split('\n', 1)[1]]
        check(tag + 'a row lost against Total Activity is a warning naming the difference',
              '13.50' in _parse(short, reader)['total_warning'])

        bare = [row[:] for row in ROWS]
        bare[3] = ['Date', 'Date', 'Description', 'Reference Number', 'MCC', 'Charge', 'Credit']
        bare[7] = bare[3]
        rb = _parse(bare, reader)
        check(tag + 'two bare "Date" headers read as posting then transaction',
              [x['transaction_date'] for x in rb['transactions']] == [x['transaction_date'] for x in t])

        # KNOWN GAP: the id carries the row's position in the file, so the same
        # charge in a re-exported statement with one more row above it gets a
        # new id, passes the duplicate check and is inserted twice.
        shifted = ROWS[:4] + [['12/27', '12/27', 'LUMBER YARD', '7000', '5200', '50.00', None]] + ROWS[4:]
        ids = {x['merchant']: x['transaction_id'] for x in _parse(shifted, reader)['transactions']}
        check(tag + 'KNOWN GAP: one charge, two statements, two ids',
              ids['THE HOME DEPOT #1234'] != t[0]['transaction_id'])

    try:
        parse_statement.main({'file_name': 'statement.xlsx', 'file_content_base64': ''})
        check('a file name off the pattern is refused', False)
    except ValueError:
        check('a file name off the pattern is refused', True)


def open_item_checks():
    base = {'cardholder_name': 'Pat  Sample', 'transaction_date': '2027-01-02', 'merchant': 'X', 'amount': 1.0}
    recs = [
        dict(base, **{'Record ID': 'a', 'transaction_id': 'a', 'matched': False, 'exempt': False,
                      'project_code': 'P1', 'cost_code': 'C1', 'reason': 'r'}),
        dict(base, **{'Record ID': 'b', 'transaction_id': 'b', 'matched': True, 'exempt': False,
                      'project_code': 'P1', 'cost_code': '', 'reason': 'r'}),
        dict(base, **{'Record ID': 'c', 'transaction_id': 'c', 'matched': False, 'exempt': True,
                      'project_code': 'P1', 'cost_code': 'C1', 'reason': 'r'}),
        dict(base, **{'Record ID': 'd', 'transaction_id': 'd', 'matched': False, 'exempt': True,
                      'project_code': None, 'cost_code': 'C1', 'reason': 'r'}),
        dict(base, **{'Record ID': 'a', 'transaction_id': 'a', 'matched': False, 'exempt': False,
                      'project_code': 'P1', 'cost_code': 'C1', 'reason': 'r'}),
    ]
    out = open_items.main({'records_json': __import__('json').dumps(recs)})
    items = {i['record_id']: i for g in out['groups'] for i in g['items']}
    check('open items: unmatched and not exempt needs a receipt', items['a']['missing_summary'] == 'receipt')
    check('open items: matched with a blank cost code needs coding', items['b']['missing_summary'] == 'cost_code')
    check('open items: exempt and fully coded is not open', 'c' not in items)
    check('open items: exempt waives the receipt, not the coding', items['d']['missing_summary'] == 'project_code')
    check('open items: a repeated record counts once', out['open_item_count'] == 3)
    check('open items: names grouped ignoring case and spacing', out['group_count'] == 1)


def finance_package_checks():
    import json
    coded = {'project_code': 'P1', 'cost_code': 'C1', 'reason': 'site supplies'}
    txns = [
        dict(coded, **{'Record ID': 't1', 'transaction_id': 'T1', 'matched': True, 'sent_in_package': True,
                       'package_version_sent': '2', 'matched_receipt_id': 'r1', 'amount': 10}),
        dict(coded, **{'Record ID': 't2', 'transaction_id': 'T2', 'matched': True, 'sent_in_package': False,
                       'matched_receipt_id': 'r2', 'amount': 5.5}),
        dict(coded, **{'Record ID': 't3', 'transaction_id': 'T3', 'matched': True, 'sent_in_package': False,
                       'matched_receipt_id': 'r3', 'amount': 7, 'project_code': 'P2'}),
        dict(coded, **{'Record ID': 't4', 'transaction_id': 'T4', 'matched': True, 'sent_in_package': False,
                       'matched_receipt_id': 'missing', 'amount': 1}),
        dict(coded, **{'Record ID': 't5', 'transaction_id': 'T5', 'matched': False, 'matched_receipt_id': '', 'amount': 1}),
        dict(coded, **{'Record ID': 't6', 'transaction_id': 'T6', 'matched': True, 'sent_in_package': False,
                       'matched_receipt_id': 'r2', 'amount': 2, 'cost_code': ''}),
        dict(coded, **{'Record ID': 't7', 'transaction_id': 'T7', 'matched': True, 'sent_in_package': False,
                       'matched_receipt_id': 'r2', 'amount': 3, 'coding_source': 'history',
                       'history_coded_on': '2027-01-10'}),
        dict(coded, **{'Record ID': 't8', 'transaction_id': 'T8', 'matched': True, 'sent_in_package': False,
                       'matched_receipt_id': 'r2', 'amount': 4, 'coding_source': 'history',
                       'history_coded_on': '2027-01-09'}),
    ]
    receipts = [
        {'Record ID': 'r1', 'receipt_month': '2027-01', 'project_code': 'P1', 'receipt_number': 'R-1'},
        {'Record ID': 'r2', 'receipt_month': '2027-01', 'project_code': 'P1', 'receipt_number': 'R-2'},
        {'Record ID': 'r3', 'receipt_month': '2027-01', 'project_code': '', 'receipt_number': 'R-3'},
    ]
    out = group_finance_package.main({'transactions_json': json.dumps(txns), 'receipts_json': json.dumps(receipts),
                                      'today': '2027-01-10'})
    g = {x['project_code']: x for x in out['groups']}
    new_ids = sorted(i['transaction_id'] for x in out['groups'] for i in x['new_transactions'])
    check('package: grouped by receipt month and the charge\'s own project', set(g) == {'P1', 'P2'})
    check('package: next version follows the highest sent', g['P1']['version'] == 3)
    check('package: previously sent rows ride along, not counted new',
          g['P1']['previous_count'] == 1 and g['P1']['grand_total'] == '19.50')
    check('package: a charge whose receipt has no project groups by the charge\'s', g['P2']['version'] == 1)
    check('package: a receipt that cannot be found is skipped, not sent', out['skipped_count'] == 1)
    check('package: a charge missing any coding is held back', 'T6' not in new_ids)
    check('package: history coding applied today waits for a digest', 'T7' not in new_ids)
    check('package: history coding from an earlier day is sent', 'T8' in new_ids)
    check('package: exactly the coded, matched, found charges are new', new_ids == ['T2', 'T3', 'T8'])
    check('package: held charges are counted', out['held_uncoded_count'] == 2)


def main():
    statement_checks()
    open_item_checks()
    finance_package_checks()
    failed = [label for label, ok in RESULTS if not ok]
    for label, ok in RESULTS:
        print(('  ok    ' if ok else '  FAIL  ') + label)
    print('%d checks, %d failed' % (len(RESULTS), len(failed)))
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
