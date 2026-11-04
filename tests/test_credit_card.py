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
    txns = [
        {'Record ID': 't1', 'transaction_id': 'T1', 'matched': True, 'sent_in_package': True,
         'package_version_sent': '2', 'matched_receipt_id': 'r1', 'amount': 10},
        {'Record ID': 't2', 'transaction_id': 'T2', 'matched': True, 'sent_in_package': False,
         'matched_receipt_id': 'r2', 'amount': 5.5},
        {'Record ID': 't3', 'transaction_id': 'T3', 'matched': True, 'sent_in_package': False,
         'matched_receipt_id': 'r3', 'amount': 7},
        {'Record ID': 't4', 'transaction_id': 'T4', 'matched': True, 'sent_in_package': False,
         'matched_receipt_id': 'missing', 'amount': 1},
        {'Record ID': 't5', 'transaction_id': 'T5', 'matched': False, 'matched_receipt_id': '', 'amount': 1},
    ]
    receipts = [
        {'Record ID': 'r1', 'receipt_month': '2027-01', 'project_code': 'P1', 'receipt_number': 'R-1'},
        {'Record ID': 'r2', 'receipt_month': '2027-01', 'project_code': 'P1', 'receipt_number': 'R-2'},
        {'Record ID': 'r3', 'receipt_month': '2027-01', 'project_code': '', 'receipt_number': 'R-3'},
    ]
    out = group_finance_package.main({'transactions_json': json.dumps(txns), 'receipts_json': json.dumps(receipts)})
    g = {x['project_code']: x for x in out['groups']}
    check('package: grouped by receipt month and project', set(g) == {'P1', 'Unassigned'})
    check('package: next version follows the highest sent', g['P1']['version'] == 3)
    check('package: previously sent rows ride along, not counted new',
          g['P1']['new_count'] == 1 and g['P1']['previous_count'] == 1 and g['P1']['grand_total'] == '15.50')
    check('package: a blank project code is Unassigned, version 1', g['Unassigned']['version'] == 1)
    check('package: a receipt that cannot be found is skipped, not sent', out['skipped_count'] == 1)
    check('package: unmatched transactions never enter', out['new_count'] == 2)


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
