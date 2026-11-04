import base64
import io
import re
import xml.etree.ElementTree as ET
import zipfile

M = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R_ID = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
TXN_REF = re.compile(r'^\d{4}-\d{8}-\d+\.\d{2}-\d+$')
RCPT_REF = re.compile(r'^R-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
COLUMNS = {'ref': 'ref', 'project': 'project_code', 'costcode': 'cost_code', 'reason': 'reason'}


def _decode(content):
    s = (content or '').strip()
    try:
        data = base64.b64decode(re.sub(r'\s', '', s), validate=True)
        if data[:2] == b'PK':
            return data
    except Exception:
        pass
    raw = s.encode('latin-1', errors='ignore')
    if raw[:2] == b'PK':
        return raw
    raise ValueError('Attachment content is not a valid .xlsx (zip) file')


def _col_index(ref):
    m = re.match(r'([A-Z]+)', ref or '')
    n = 0
    for ch in (m.group(1) if m else 'A'):
        n = n * 26 + ord(ch) - 64
    return n - 1


def _text(v):
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r'\s+', ' ', '' if v is None else str(v)).strip()


def _rows(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    names = set(z.namelist())
    shared = []
    if 'xl/sharedStrings.xml' in names:
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall(M + 'si'):
            shared.append(''.join(t.text or '' for t in si.iter(M + 't')))
    rels = {}
    if 'xl/_rels/workbook.xml.rels' in names:
        for rel in ET.fromstring(z.read('xl/_rels/workbook.xml.rels')):
            rels[rel.get('Id')] = rel.get('Target') or ''
    wb = ET.fromstring(z.read('xl/workbook.xml'))
    for sh in wb.iter(M + 'sheet'):
        target = rels.get(sh.get(R_ID), '')
        path = target.lstrip('/') if target.startswith('/') else (target if target.startswith('xl/') else 'xl/' + target)
        if path not in names or 'worksheets/' not in path:
            continue
        rows = []
        for row in ET.fromstring(z.read(path)).iter(M + 'row'):
            vals = {}
            for c in row.findall(M + 'c'):
                t, v = c.get('t'), c.find(M + 'v')
                if t == 's' and v is not None:
                    val = shared[int(v.text)]
                elif t == 'inlineStr':
                    val = ''.join(x.text or '' for x in c.iter(M + 't'))
                elif v is not None:
                    try:
                        val = float(v.text)
                    except (TypeError, ValueError):
                        val = v.text
                else:
                    val = None
                vals[_col_index(c.get('r'))] = val
            number = int(row.get('r') or len(rows) + 1)
            rows.append((number, [vals.get(i) for i in range(max(vals) + 1)] if vals else []))
        yield rows


def main(input):
    data = _decode(input.get('file_content_base64'))
    for rows in _rows(data):
        for h, (_, row) in enumerate(rows):
            keys = {re.sub(r'[^a-z]', '', _text(v).lower()): i for i, v in enumerate(row) if _text(v)}
            cols = {field: keys[k] for k, field in COLUMNS.items() if k in keys}
            if len(cols) == len(COLUMNS):
                break
        else:
            continue
        updates, problems, blank = [], [], 0
        seen = set()
        for n, row in rows[h + 1:]:
            get = lambda f: _text(row[cols[f]]) if cols[f] < len(row) else ''
            ref = get('ref')
            coding = {f: get(f) for f in ('project_code', 'cost_code', 'reason')}
            if not ref and not any(coding.values()):
                continue
            if not any(coding.values()):
                blank += 1
                continue
            if TXN_REF.match(ref):
                ref_type, value = 'transaction', ref
            elif RCPT_REF.match(ref):
                ref_type, value = 'receipt', ref[2:]
            else:
                problems.append('Row %d: "%s" is not a charge or receipt reference.' % (n, ref or '(blank)'))
                continue
            if value in seen:
                problems.append('Row %d: %s appears twice; the first row was used.' % (n, ref))
                continue
            seen.add(value)
            updates.append(dict(coding, ref=value, ref_type=ref_type))
        return {
            'is_coding_sheet': True,
            'updates': updates,
            'update_count': len(updates),
            'rows_left_blank': blank,
            'problems': ' '.join(problems),
        }
    return {'is_coding_sheet': False, 'updates': [], 'update_count': 0, 'rows_left_blank': 0,
            'problems': 'No sheet has the columns Ref, Project, Cost code and Reason.'}
