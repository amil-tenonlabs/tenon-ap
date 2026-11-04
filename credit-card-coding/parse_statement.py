import base64
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from itertools import zip_longest
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP

M = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R_ID = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
FILE_RE = re.compile(r'^(.+)_([0-9]{4,8}[xX*]+[0-9]{4})_([0-9]+)_([0-9]{8})\.xlsx$', re.I)
# Labelled columns matched by normalized key (letters only, lower-case). Bare 'Date' cells are handled separately.
LABEL_COLS = ['posting date', 'transaction date', 'description', 'reference number', 'mcc', 'charge', 'credit']
NON_DATE_COLS = ['description', 'reference number', 'mcc', 'charge', 'credit']
COL_KEYS = {c: re.sub(r'[^a-z]', '', c) for c in LABEL_COLS}
MAX_KEY_LEN = max(len(k) for k in COL_KEYS.values())
DATE_KEY = 'date'
MAX_SPAN = 4          # max adjacent cells joined to form one header label
MAX_DIAG_ROWS = 100   # cap on diagnostic rows per sheet in the error message
MD_TOKEN = re.compile(r'(?<!\d)\d{1,2}[/\-]\d{1,2}(?:[/\-]\d{2,4})?(?!\d)')


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


def _text(v):
    if v is None:
        return ''
    return re.sub(r'\s+', ' ', str(v)).strip()


def _key(v):
    # Header comparison key: lower-case letters only (ignores case, spaces, newlines, punctuation)
    return re.sub(r'[^a-z]', '', str(v).lower()) if v is not None else ''


# ---------- workbook readers: yield (sheet_name, rows) in workbook order ----------

def _sheets_openpyxl(data):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    for ws in wb.worksheets:
        if hasattr(ws, 'reset_dimensions'):
            ws.reset_dimensions()  # ignore wrong <dimension> metadata from converters
        yield ws.title, [list(r) for r in ws.iter_rows(values_only=True)]


def _col_index(ref, fallback):
    m = re.match(r'([A-Z]+)', ref or '')
    if not m:
        return fallback
    n = 0
    for ch in m.group(1):
        n = n * 26 + ord(ch) - 64
    return n - 1


def _zip_sheet_rows(z, path, shared):
    rows = []
    for row in ET.fromstring(z.read(path)).iter(M + 'row'):
        vals = {}
        for pos, c in enumerate(row.findall(M + 'c')):
            t = c.get('t')
            v = c.find(M + 'v')
            if t == 's' and v is not None:
                val = shared[int(v.text)]
            elif t == 'inlineStr':
                val = ''.join(x.text or '' for x in c.iter(M + 't'))
            elif t in ('str', 'b', 'e') and v is not None:
                val = v.text
            elif v is not None:
                try:
                    val = float(v.text)
                except (TypeError, ValueError):
                    val = v.text
            else:
                val = None
            vals[_col_index(c.get('r'), pos)] = val
        rows.append([vals.get(i) for i in range(max(vals) + 1)] if vals else [])
    return rows


def _sheets_zip(data):
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
    for sh in wb.iter(M + 'sheet'):  # workbook.xml lists sheets in workbook order
        sname = sh.get('name') or ''
        target = rels.get(sh.get(R_ID), '')
        if target.startswith('/'):
            path = target.lstrip('/')
        elif target.startswith('xl/'):
            path = target
        else:
            path = 'xl/' + target
        if not target or path not in names or 'worksheets/' not in path:
            yield sname, []  # chartsheet or unresolved sheet: no rows
            continue
        yield sname, _zip_sheet_rows(z, path, shared)


# ---------- header detection ----------

def _match_keys(keys):
    """Header rule: Description + Charge + (Credit or Reference Number), plus EITHER
    (b) explicit 'Posting Date' and 'Transaction Date' labels (preferred when both found), OR
    (a) two cells whose normalized text is exactly 'date': 1st = Posting Date, 2nd = Transaction Date.
    Labels may be split across up to MAX_SPAN adjacent cells. Returns {col: (first_cell, last_cell)} or None."""
    spans = {}
    n = len(keys)
    for j in range(n):
        if not keys[j]:
            continue
        acc = ''
        for e in range(j, min(n, j + MAX_SPAN)):
            acc += keys[e]
            if len(acc) > MAX_KEY_LEN:
                break
            for col in LABEL_COLS:
                if col not in spans and acc == COL_KEYS[col]:
                    spans[col] = (j, e)
    if not ('description' in spans and 'charge' in spans and ('credit' in spans or 'reference number' in spans)):
        return None
    # (b) explicit Posting Date / Transaction Date labels
    if 'posting date' in spans and 'transaction date' in spans:
        return spans
    # (a) two bare 'Date' cells not belonging to another header label
    used = set()
    for col in NON_DATE_COLS:
        if col in spans:
            a, b = spans[col]
            used.update(range(a, b + 1))
    date_cells = [j for j, k in enumerate(keys) if k == DATE_KEY and j not in used]
    if len(date_cells) >= 2:
        out = {c: spans[c] for c in NON_DATE_COLS if c in spans}
        out['posting date'] = (date_cells[0], date_cells[0])
        out['transaction date'] = (date_cells[1], date_cells[1])
        return out
    return None


def _effective_ranges(spans):
    # Each column reads from its header start up to the cell before the next header starts
    # (tolerates data that is shifted right / merged cells in PDF-style conversions).
    order = sorted(spans.items(), key=lambda kv: kv[1][0])
    eff = {}
    for n, (col, (a, b)) in enumerate(order):
        if n + 1 < len(order):
            end = max(b, order[n + 1][1][0] - 1)
        else:
            end = b + 2
        eff[col] = (a, end)
    return eff


def _find_header(rows):
    """Returns (first_header_row_idx, last_header_row_idx, ranges) for the FIRST header found, or None.
    Later repeated header rows (page headers/footers) are ignored here and skipped as data rows."""
    keyed = [[_key(c) for c in row] for row in rows]
    # Pass 1: single-row header (fragments in one cell or adjacent cells)
    for i, keys in enumerate(keyed):
        spans = _match_keys(keys)
        if spans:
            return i, i, _effective_ranges(spans)
    # Pass 2 (fallback): header spanning two consecutive rows (e.g. 'Posting' above 'Date')
    for i in range(len(keyed) - 1):
        merged = [(a or '') + (b or '') for a, b in zip_longest(keyed[i], keyed[i + 1])]
        spans = _match_keys(merged)
        if spans:
            return i, i + 1, _effective_ranges(spans)
    return None


def _diagnostics(rows):
    out = []
    for i, row in enumerate(rows):
        texts = [_text(c) for c in row if _text(c)]
        low = ' '.join(texts).lower()
        if 'date' in low or 'description' in low:
            out.append('row %d: %s' % (i + 1, [t[:40] for t in texts[:10]]))
            if len(out) >= MAX_DIAG_ROWS:
                out.append('... (truncated)')
                break
    return out


# ---------- value parsing ----------

def _cell(row, i):
    return row[i] if i is not None and 0 <= i < len(row) else None


def _range_val(row, rng):
    if not rng:
        return None
    for k in range(rng[0], rng[1] + 1):
        v = _cell(row, k)
        if v is not None and _text(v):
            return v
    return None


def _range_text(row, rng):
    if not rng:
        return ''
    return ' '.join(_text(_cell(row, k)) for k in range(rng[0], rng[1] + 1) if _text(_cell(row, k)))


def _month_day(v):
    """Valid transaction date -> (month, day); anything else (e.g. 'Date', 'Total', page numbers) -> None."""
    if isinstance(v, (datetime, date)):
        return v.month, v.day
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if 20000 <= v < 80000:  # plausible Excel date serial (1954-2119); rejects page numbers / amounts
            d = datetime(1899, 12, 30) + timedelta(days=float(v))
            return d.month, d.day
        return None
    s = _text(v)
    m = re.match(r'^(\d{1,2})[/\-](\d{1,2})(?:[/\-]\d{2,4})?$', s)
    if not m:
        m = re.match(r'^\d{4}-(\d{2})-(\d{2})', s)
    if m:
        mo, dy = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= dy <= 31:
            return mo, dy
    return None


def _num(v):
    if v is None or isinstance(v, bool):
        return Decimal('0')
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    s = str(v).strip()
    neg = (s.startswith('(') and s.endswith(')')) or s.startswith('-')
    s = re.sub(r'[^0-9.]', '', s)
    if s in ('', '.'):
        return Decimal('0')
    try:
        n = Decimal(s)
    except Exception:
        return Decimal('0')
    return -n if neg else n


# ---------- exemption rules ----------

FALSE_WORDS = ('false', '0', 'no', 'n', 'f', 'off')
NUMERIC_RE = re.compile(r'^[+-]?(\d+(\.\d*)?|\.\d+)$')


def _norm(v):
    # trim, collapse internal whitespace, lower-case
    return re.sub(r'\s+', ' ', '' if v is None else str(v)).strip().lower()


def _is_active(v):
    # blank / absent 'active' counts as active; only an explicit false value deactivates a rule
    if v is None:
        return True
    if isinstance(v, bool):
        return v
    return _norm(v) not in FALSE_WORDS


def _threshold(v):
    s = '' if v is None else str(v).strip()
    if not NUMERIC_RE.match(s):
        return None
    try:
        return Decimal(s)
    except Exception:
        return None


def _load_rules(raw):
    """Returns (vendor_values, max_amount_thresholds, warnings). Invalid rules are ignored with a warning."""
    if isinstance(raw, str):
        raw = json.loads(raw) if raw.strip() else []
    vendors, limits, warnings = [], [], []
    for i, r in enumerate(raw or [], 1):
        if not isinstance(r, dict):
            warnings.append('rule #%d ignored: not an object' % i)
            continue
        if not _is_active(r.get('active')):
            continue
        rtype = _norm(r.get('rule_type'))
        if rtype == 'vendor':
            v = _norm(r.get('value'))
            if v:
                vendors.append(v)
            else:
                warnings.append('rule #%d ignored: vendor rule with blank value' % i)
        elif rtype == 'max_amount':
            t = _threshold(r.get('value'))
            if t is None:
                warnings.append('rule #%d ignored: max_amount value %r is not numeric' % (i, r.get('value')))
            else:
                limits.append(t)
        else:
            warnings.append('rule #%d ignored: unknown rule_type %r' % (i, r.get('rule_type')))
    return vendors, limits, warnings


def _is_exempt(merchant, amount, vendors, limits):
    # vendor rule: normalized merchant CONTAINS normalized rule value
    m = _norm(merchant)
    if any(v in m for v in vendors):
        return True
    # max_amount rule: charges only (amount > 0), strictly below the threshold; credits are never amount-exempt
    return amount > 0 and any(amount < t for t in limits)


def main(input):
    name = (input.get('file_name') or '').strip()
    fm = FILE_RE.match(name)
    if not fm:
        raise ValueError('File name does not match <CARDHOLDER NAME>_<masked card>_<number>_<YYYYMMDD>.xlsx: ' + name)
    # Cardholder name = text before the FIRST underscore of the file name, trimmed
    cardholder_name = name.split('_', 1)[0].strip()
    card_last4 = re.sub(r'\D', '', fm.group(2))[-4:]
    stmt = fm.group(4)
    stmt_year, stmt_month = int(stmt[:4]), int(stmt[4:6])
    statement_month = '%s-%s' % (stmt[:4], stmt[4:6])

    vendors, limits, rule_warnings = _load_rules(input.get('exemption_rules'))
    if _text(input.get('rules_next_page_token')):
        rule_warnings.append('Exemption Rules has more than 1000 records; only the first 1000 were evaluated')

    data = _decode(input.get('file_content_base64'))
    try:
        import openpyxl  # noqa: F401
        sheets = _sheets_openpyxl(data)
        parser = 'openpyxl'
    except ImportError:
        sheets = _sheets_zip(data)
        parser = 'zipfile+xml'

    sheet_names = []
    diags = {}
    found = None
    for sname, rows in sheets:
        sheet_names.append(sname)
        res = _find_header(rows)
        if res:
            found = (sname, rows, res)
            break
        diags[sname] = {'total_rows': len(rows), 'rows_with_date_or_description': _diagnostics(rows)}

    if found is None:
        raise ValueError(
            'No sheet has a header row with Description, Charge and Credit or Reference Number plus either two '
            '"Date" columns (1st = Posting Date, 2nd = Transaction Date) or explicit Posting Date and Transaction Date '
            'labels (all rows scanned, including headers split across cells or two rows). '
            'Sheets found: %s. Rows containing Date/Description: %s' % (sheet_names, diags)
        )
    sheet_name, rows, (h_first, h_last, rng) = found

    out = []
    skipped = 0
    seq = 0
    for row in rows[h_last + 1:]:
        if not any(_text(c) for c in row):
            continue  # blank row
        td_raw = _range_val(row, rng.get('transaction date'))
        md = _month_day(td_raw)
        if md is None and td_raw is None:
            # PDF conversions sometimes merge both dates into the Posting Date cell: use the 2nd date
            toks = MD_TOKEN.findall(_range_text(row, rng.get('posting date')))
            if len(toks) >= 2:
                md = _month_day(toks[1])
        if md is None:
            skipped += 1  # repeated header rows, totals, page footers: no row_sequence consumed
            continue
        charge = _num(_range_val(row, rng.get('charge')))
        credit = _num(_range_val(row, rng.get('credit')))
        if charge == 0 and credit == 0:
            skipped += 1
            continue
        mo, dy = md
        year = stmt_year - 1 if mo > stmt_month else stmt_year
        try:
            tdate = date(year, mo, dy)
        except ValueError:
            skipped += 1
            continue
        amount = (charge if charge != 0 else -abs(credit)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        seq += 1  # only rows that become transactions get a sequence number
        merchant = _range_text(row, rng.get('description'))
        out.append({
            'row_sequence': seq,
            'transaction_id': '%s-%s-%s-%d' % (card_last4, tdate.strftime('%Y%m%d'), format(amount, '.2f'), seq),
            'transaction_date': tdate.isoformat(),
            'merchant': merchant,
            'amount': float(amount),
            'card_last4': card_last4,
            'cardholder_name': cardholder_name,
            'statement_month': statement_month,
            'matched': False,
            'exempt': _is_exempt(merchant, amount, vendors, limits),
        })

    return {
        'card_last4': card_last4,
        'statement_date': stmt,
        'statement_month': statement_month,
        'cardholder_name': cardholder_name,
        'parser': parser,
        'sheet_name': sheet_name,
        'header_row': h_first + 1,
        'row_count': len(out),
        'skipped_count': skipped,
        'active_rule_count': len(vendors) + len(limits),
        'ignored_rule_count': sum(1 for w in rule_warnings if w.startswith('rule #')),
        'rule_warnings': '; '.join(rule_warnings),
        'exempt_count': sum(1 for t in out if t['exempt']),
        'transactions': out,
    }
