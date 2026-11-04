# ============================================================================
# test_read_receipt.py
#
# read_receipt.py: Claude's reading of one receipt - a text PDF, a scan or a
# photo turned into a PDF - checked and put into the fields FNC-001 logs.
# No real data.
#
#   python3 tests/test_read_receipt.py
#
# The load-bearing cases: a reply that is not the JSON object never logs a
# blank receipt, "not a receipt" (a logo, a signature) logs nothing, and a
# total that cannot be read is said, never logged as zero.
# ============================================================================

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('read_receipt', os.path.join(HERE, '..', 'credit-card-coding', 'read_receipt.py'))
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)

RESULTS = []


def check(label, ok):
    RESULTS.append((label, bool(ok)))


def run(obj, wrap='%s'):
    return rr.main({'response_text': wrap % (obj if isinstance(obj, str) else json.dumps(obj))})


def main():
    good = {'is_receipt': True, 'merchant': 'Docusign Inc.', 'receipt_date': '2026-10-25', 'amount': 606,
            'currency': 'usd', 'card_last_4': 'XXXX 8678', 'receipt_number': 'INV1', 'project_code': 'Perry',
            'cost_code': '01-750', 'reason': 'e-signature plan', 'split_text': '', 'notes': ''}
    r = run(good)
    check('a clean reading passes through', r['ok'] and r['is_receipt'] and r['merchant'] == 'Docusign Inc.'
          and r['amount'] == 606.0 and r['problems'] == '')
    check('the month is the date\'s', r['receipt_month'] == '2026-10')
    check('currency upper-cased, card cut to four digits', r['currency'] == 'USD' and r['card_last_4'] == '8678')
    check('a reply in a code fence or with a sentence around it still reads',
          run(good, '```json\n%s\n```')['ok'] and run(good, 'Here is the receipt:\n%s\nThanks.')['merchant'] == 'Docusign Inc.')

    r = rr.main({'response_text': 'I could not read this image.'})
    check('a reply that is not JSON is a problem, never a blank receipt', not r['ok'] and 'not the JSON' in r['problems'])
    r = run({'is_receipt': False, 'merchant': 'Logo Co', 'notes': 'an email signature logo'})
    check('not a receipt: ok, nothing to log, and the reason kept',
          r['ok'] and not r['is_receipt'] and r['merchant'] == '' and 'logo' in r['notes'])

    for raw, want in (('$1,234.50', 1234.5), ('1234.5', 1234.5), (49.999, 50.0), ('(12.00)', -12.0)):
        check('amount %r reads as %r' % (raw, want), run(dict(good, amount=raw))['amount'] == want)
    r = run(dict(good, amount='illegible'))
    check('an unreadable total is said, never zero', r['amount'] is None and 'No total' in r['problems'])

    for raw, want in (('10/25/2026', '2026-10-25'), ('Oct 25, 2026', '2026-10-25'), ('October 5 2026', '2026-10-05'),
                      ('10/25/26', '2026-10-25'), ('25 Oct', ''), ('2026-02-30', '')):
        check('date %r reads as %r' % (raw, want), run(dict(good, receipt_date=raw))['receipt_date'] == want)

    r = run(dict(good, split_text=['Perry | 01-750 | 60% | plan', 'Oak St | 01-750 | 40% | plan', 'not a share']))
    check('a split keeps only its share lines and clears the single coding',
          r['split_text'] == 'Perry | 01-750 | 60% | plan\nOak St | 01-750 | 40% | plan' and r['project_code'] == '')

    failed = [label for label, ok in RESULTS if not ok]
    for label, ok in RESULTS:
        print(('  ok    ' if ok else '  FAIL  ') + label)
    print('%d checks, %d failed' % (len(RESULTS), len(failed)))
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
