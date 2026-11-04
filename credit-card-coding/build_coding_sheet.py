import base64
import io
import json
import re
import zipfile
from datetime import date
from xml.sax.saxutils import escape

HEADER = ['Ref', 'Cardholder', 'Date', 'Merchant', 'Amount', 'Still needed', 'Project', 'Cost code', 'Reason']
WIDTHS = [26, 18, 12, 36, 11, 24, 18, 14, 36]
NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'application/vnd.openxmlformats-officedocument.spreadsheetml'


def _col(i):
    s = ''
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell(ref, v, style):
    if v is None or v == '':
        return '<c r="%s" s="%d"/>' % (ref, style)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return '<c r="%s" s="%d"><v>%s</v></c>' % (ref, style, repr(float(v)))
    return '<c r="%s" s="%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, style, escape(str(v)))


def _amount(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return v


def main(input):
    items = input.get('items_json') or '[]'
    items = json.loads(items) if isinstance(items, str) else items
    rows = [HEADER]
    for it in items or []:
        rows.append([
            it.get('transaction_id') or '',
            it.get('cardholder_name') or '',
            str(it.get('transaction_date') or ''),
            it.get('merchant') or '',
            _amount(it.get('amount')),
            it.get('missing_summary') or '',
            it.get('suggested_project_code') or '',
            it.get('suggested_cost_code') or '',
            it.get('suggested_reason') or '',
        ])
    # style 0 plain, 1 bold header, 2 amount, 3 unlocked input cell
    xml_rows = []
    for r, row in enumerate(rows):
        cells = []
        for c, v in enumerate(row):
            style = 1 if r == 0 else (2 if c == 4 else (3 if c >= 6 else 0))
            cells.append(_cell('%s%d' % (_col(c), r + 1), v, style))
        xml_rows.append('<row r="%d">%s</row>' % (r + 1, ''.join(cells)))
    cols = ''.join('<col min="%d" max="%d" width="%d" customWidth="1"/>' % (i + 1, i + 1, w) for i, w in enumerate(WIDTHS))
    last = '%s%d' % (_col(len(HEADER) - 1), len(rows))
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="%s"><sheetViews><sheetView workbookViewId="0">'
             '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
             '<cols>%s</cols><sheetData>%s</sheetData><autoFilter ref="A1:%s"/></worksheet>'
             % (NS, cols, ''.join(xml_rows), last))
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<styleSheet xmlns="%s"><numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.00"/></numFmts>'
              '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
              '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
              '<fill><patternFill patternType="solid"><fgColor rgb="FFFFF2CC"/><bgColor indexed="64"/></patternFill></fill></fills>'
              '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
              '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
              '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
              '<xf numFmtId="49" fontId="0" fillId="2" borderId="0" xfId="0" applyFill="1" applyNumberFormat="1"/></cellXfs>'
              '</styleSheet>' % NS)
    files = {
        '[Content_Types].xml':
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="%s.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="%s.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="%s.styles+xml"/>'
            '</Types>' % (CT, CT, CT),
        '_rels/.rels':
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="%s"><Relationship Id="rId1" Type="%s/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>' % (PKG, REL),
        'xl/workbook.xml':
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="%s" xmlns:r="%s"><sheets><sheet name="Open items" sheetId="1" r:id="rId1"/></sheets>'
            '<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">\'Open items\'!$A$1:$%s$%d</definedName></definedNames>'
            '</workbook>' % (NS, REL, _col(len(HEADER) - 1), len(rows)),
        'xl/_rels/workbook.xml.rels':
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="%s"><Relationship Id="rId1" Type="%s/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="%s/styles" Target="styles.xml"/></Relationships>' % (PKG, REL, REL),
        'xl/worksheets/sheet1.xml': sheet,
        'xl/styles.xml': styles,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, body in files.items():
            z.writestr(name, body)
    who = re.sub(r'[^A-Za-z0-9]+', '_', (input.get('label') or 'Open_items')).strip('_') or 'Open_items'
    today = (input.get('today') or date.today().isoformat()).replace('-', '')
    return {
        'file_name': 'CC_Coding_%s_%s.xlsx' % (who, today),
        'file_base64': base64.b64encode(buf.getvalue()).decode(),
        'row_count': len(rows) - 1,
    }
