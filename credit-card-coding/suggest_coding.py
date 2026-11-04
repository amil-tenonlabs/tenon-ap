import json
import re

FIELDS = ('project_code', 'cost_code', 'reason')
NOISE = {'inc', 'llc', 'co', 'corp', 'the', 'www', 'com', 'tst', 'sq', 'pp', 'paypal'}


def _s(v):
    return re.sub(r'\s+', ' ', '' if v is None else str(v)).strip()


def _person(v):
    return re.sub(r'\s+', '', _s(v)).lower()


def merchant_key(merchant):
    """Two leading words of the merchant, so 'DOCUSIGN INC. 800-3799973 DE' and
    'DocuSign Inc' agree: lower-case, punctuation, digits, state codes and filler words dropped."""
    words = [w for w in re.split(r'[^a-z]+', _s(merchant).lower()) if len(w) > 2 and w not in NOISE]
    return ' '.join(words[:2])


def _coded(r):
    return all(_s(r.get(f)) for f in FIELDS)


def _coding(r):
    return tuple(_s(r.get(f)) for f in FIELDS)


def main(input):
    records = input.get('records_json') or '[]'
    records = json.loads(records) if isinstance(records, str) else records
    records = records or []

    history = {}
    for r in records:
        if not _coded(r):
            continue
        key = (_person(r.get('cardholder_name')), merchant_key(r.get('merchant')))
        if not key[1]:
            continue
        history.setdefault(key, []).append(r)
    for rows in history.values():
        rows.sort(key=lambda r: (_s(r.get('transaction_date')), _s(r.get('Created at') or r.get('created_at'))), reverse=True)

    apply, suggested, out = [], 0, []
    for r in records:
        r = dict(r)
        r['suggestion'] = ''
        for f in FIELDS:
            r['suggested_' + f] = ''
        if _coded(r):
            out.append(r)
            continue
        key = (_person(r.get('cardholder_name')), merchant_key(r.get('merchant')))
        rows = [h for h in history.get(key, []) if h.get('Record ID') != r.get('Record ID')]
        explicit = [h for h in rows if _s(h.get('coding_source')).lower() != 'history']
        if len(explicit) >= 2 and _coding(explicit[0]) == _coding(explicit[1]):
            coding = dict(zip(FIELDS, _coding(explicit[0])))
            # only blanks are filled: a field the cardholder already gave is kept
            fill = {f: (_s(r.get(f)) or coding[f]) for f in FIELDS}
            apply.append(dict(fill, ref=_s(r.get('transaction_id')), ref_type='transaction',
                              record_id=_s(r.get('Record ID')), cardholder_name=_s(r.get('cardholder_name')),
                              cardholder_key=_person(r.get('cardholder_name')),
                              transaction_date=_s(r.get('transaction_date')), merchant=_s(r.get('merchant')),
                              amount=_s(r.get('amount')),
                              based_on='%d earlier %s charges' % (len(explicit), key[1])))
            r.update(fill)
            r['coding_source'] = 'history'
        elif rows:
            coding = dict(zip(FIELDS, _coding(rows[0])))
            for f in FIELDS:
                r['suggested_' + f] = _s(r.get(f)) or coding[f]
            r['suggestion'] = ' / '.join(r['suggested_' + f] for f in FIELDS)
            suggested += 1
        out.append(r)

    return {
        'apply': apply,
        'apply_count': len(apply),
        'suggested_count': suggested,
        'records_json': json.dumps(out, default=str),
    }
