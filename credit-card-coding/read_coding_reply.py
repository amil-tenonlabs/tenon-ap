import re

TXN_REF = r'\d{4}-\d{8}-\d+\.\d{2}-\d+'
RCPT_REF = r'R-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
REF = re.compile(r'(?<![\w.-])(' + TXN_REF + r'|' + RCPT_REF + r')(?![\w.])')
QUOTE_START = re.compile(
    r'^\s*(>|from:|sent:\s|-{2,}\s*original message|_{5,}|on .{3,200} wrote:\s*$)', re.I)
LABELS = {
    'project_code': re.compile(r'\b(?:project|job)(?:\s*(?:code|name|number|no\.?|#))?\s*[:=]\s*(.+)', re.I),
    'cost_code': re.compile(r'\b(?:cost\s*code|cost\s*#|phase\s*code|work\s*order(?:\s*#)?)\s*[:=]\s*(.+)', re.I),
    'reason': re.compile(r'\b(?:reason|purpose|for)\s*[:=]\s*(.+)', re.I),
}
SEP = re.compile(r'\s*[,;|\t]\s*')
SHARE_TOK = re.compile(r'(?<![\w.$%])(\(?-?\$\s?[\d,]*\.?\d+\)?|-?\d+(?:\.\d+)?\s?%)(?![\w.%])')
SHARE_LABEL = re.compile(r'\b(?:share|split|amount)\s*[:=]\s*', re.I)


def _clean(v):
    return re.sub(r'\s+', ' ', v or '').strip(' .')


def _ref_type(ref):
    return 'receipt' if ref.upper().startswith('R-') else 'transaction'


def _ref_value(ref):
    return ref[2:] if _ref_type(ref) == 'receipt' else ref


def _new_text(body):
    """The reply's own words: everything above the first quoted line."""
    out = []
    for line in (body or '').replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        if QUOTE_START.match(line):
            break
        out.append(line)
    return '\n'.join(out).strip()


def _labelled(text):
    found = {}
    for line in text.split('\n'):
        for field, rx in LABELS.items():
            m = rx.search(line)
            if m and field not in found:
                found[field] = _clean(m.group(1))
    return found


def _coding_line(rest):
    """'Perry, 01-750, e-signature plan' -> project, cost code, reason. The reason keeps
    any separators of its own; fewer than three parts leave the rest blank."""
    share = ''
    m = SHARE_TOK.search(rest)
    if m:
        share = m.group(1).replace(' ', '')
        rest = rest[:m.start()] + rest[m.end():]
        rest = SHARE_LABEL.sub('', rest)
        rest = re.sub(r'\s*([,;|])(\s*[,;|])+\s*', r'\1 ', rest)
        rest = re.sub(r'[,;|]\s*$', '', rest.strip())
    labelled = _labelled(rest)
    if labelled:
        coding = labelled
    else:
        parts = SEP.split(rest.strip(' :-\u2013\u2014'), maxsplit=2)
        fields = ('project_code', 'cost_code', 'reason')
        coding = {f: _clean(p) for f, p in zip(fields, parts) if _clean(p)}
    if share:
        coding['share'] = share
    return coding


def _update(ref, codings, problems):
    blank = {'ref': _ref_value(ref), 'ref_type': _ref_type(ref),
             'project_code': '', 'cost_code': '', 'reason': '', 'shares': []}
    with_share = [c for c in codings if c.get('share')]
    if len(codings) > 1 and len(with_share) == len(codings):
        blank['shares'] = [dict({'project_code': '', 'cost_code': '', 'reason': ''}, **c) for c in codings]
        return blank
    if len(codings) > 1:
        problems.append('%s is given more than once without a share on every line; the first line '
                        'was used. To split a charge, give each line its $ amount or %%.' % ref)
    first = dict(codings[0])
    first.pop('share', None)
    return dict(blank, **first)


def main(input):
    body = input.get('body') or ''
    new = _new_text(body)
    updates, problems = [], []

    lines = {}
    for line in new.split('\n'):
        m = REF.search(line)
        if not m:
            continue
        coding = _coding_line(line[m.end():])
        if coding:
            lines.setdefault(m.group(1), []).append(coding)
    for ref, codings in lines.items():
        updates.append(_update(ref, codings, problems))

    single_ref, single_type, needs_ai = '', '', False
    if not updates:
        refs = []
        for m in REF.finditer(body):
            if m.group(1) not in refs:
                refs.append(m.group(1))
        if len(refs) == 1:
            single_ref, single_type = _ref_value(refs[0]), _ref_type(refs[0])
            coding = _labelled(new)
            if coding:
                updates.append(dict({'ref': single_ref, 'ref_type': single_type,
                                     'project_code': '', 'cost_code': '', 'reason': '', 'shares': []}, **coding))
            elif new:
                needs_ai = True
            else:
                problems.append('The reply has no text above the quoted email.')
        elif not refs:
            problems.append('No charge or receipt reference was found. Reply to the email that '
                            'lists the charge, or give each charge on its own line as '
                            '"REF: project, cost code, reason".')
        else:
            problems.append('The email refers to %d charges but no line gives coding for one. '
                            'Give each on its own line as "REF: project, cost code, reason".' % len(refs))

    all_refs = set(m.group(1) for m in REF.finditer(body))
    return {
        'ref_count': len(all_refs),
        'updates': updates,
        'update_count': len(updates),
        'needs_ai': needs_ai,
        'single_ref': single_ref,
        'single_ref_type': single_type,
        'new_text': new,
        'problems': ' '.join(problems),
    }
