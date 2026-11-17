"""Penulis file Excel (.xlsx) sederhana tanpa paket tambahan.

File .xlsx sebenarnya adalah ZIP berisi beberapa file XML. Di sini hanya dibuat satu lembar dengan baris judul
tebal, kolom otomatis selebar isinya, baris judul yang terkunci saat digulir, dan filter di judul kolom.

Teks ditulis sebagai teks (inlineStr), bukan rumus, jadi isi sel yang diawali "=" tetap dibaca Excel sebagai teks.
"""
import io
import re
import zipfile
from xml.sax.saxutils import escape

# Karakter yang tidak boleh ada di XML 1.0 (kalau lolos, Excel menolak membuka file)
_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_BAD_SHEET_CHARS = re.compile(r"[\[\]:*?/\\']")

MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _column_letters(index):
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def _clean(text):
    return _ILLEGAL.sub("", str(text))


def _cell(ref, value, style=None):
    s = f' s="{style}"' if style else ""
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        value = "Ya" if value else "Tidak"
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"{s}><v>{value}</v></c>'
    text = escape(_clean(value))
    return f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _sheet_title(title):
    cleaned = _BAD_SHEET_CHARS.sub(" ", _clean(title)).strip() or "Data"
    return cleaned[:31]


def build_workbook(sheet_title, headers, rows):
    """Kembalikan isi file .xlsx (bytes). `rows` berupa daftar baris; tiap baris daftar nilai sepanjang `headers`."""
    title = _sheet_title(sheet_title)
    width = len(headers)
    last_col = _column_letters(max(width - 1, 0))
    last_row = len(rows) + 1

    # lebar kolom mengikuti isi (dilihat dari 300 baris pertama), dibatasi 8..60
    widths = [len(_clean(h)) + 4 for h in headers]
    for row in rows[:300]:
        for i, value in enumerate(row[:width]):
            if value is not None:
                widths[i] = max(widths[i], len(_clean(value)) + 2)
    cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{min(max(w, 8), 60)}" customWidth="1"/>'
                   for i, w in enumerate(widths))

    sheet_rows = ['<row r="1">' + "".join(_cell(f"{_column_letters(i)}1", h, style=1) for i, h in enumerate(headers)) + "</row>"]
    for r, row in enumerate(rows, start=2):
        cells = "".join(_cell(f"{_column_letters(i)}{r}", value) for i, value in enumerate(row[:width]))
        sheet_rows.append(f'<row r="{r}">{cells}</row>')

    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '<selection pane="bottomLeft"/></sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        f"<cols>{cols}</cols>"
        f"<sheetData>{''.join(sheet_rows)}</sheetData>"
        f'<autoFilter ref="A1:{last_col}{last_row}"/>'
        "</worksheet>"
    )

    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{escape(title)}" sheetId="1" r:id="rId1"/></sheets>'
        f'<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">'
        f"'{escape(title)}'!$A$1:${last_col}${last_row}</definedName></definedNames>"
        "</workbook>"
    )

    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFE8ECF8"/><bgColor indexed="64"/></patternFill></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        z.writestr("xl/styles.xml", styles)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()
