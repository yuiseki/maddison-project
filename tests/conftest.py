"""A minimal xlsx writer for the tests, standard library only.

Text goes into the shared strings table as Excel writes it; a cell given as
a number is written as a plain numeric cell with the text as its value; None
leaves the cell out. Rows are written in order from row 1.
"""

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


class Num(str):
    """A cell written as a numeric cell; the text is what goes into <v>."""


def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def write_xlsx(path: Path, sheets: dict[str, list[list]]) -> Path:
    shared: list[str] = []
    index: dict[str, int] = {}
    sheet_xml = []
    for rows in sheets.values():
        out = []
        for r, row in enumerate(rows, start=1):
            cells = []
            for c, v in enumerate(row):
                ref = f"{_col(c)}{r}"
                if v is None:
                    continue
                if isinstance(v, Num):
                    cells.append(f'<c r="{ref}"><v>{v}</v></c>')
                else:
                    if v not in index:
                        index[v] = len(shared)
                        shared.append(v)
                    cells.append(f'<c r="{ref}" t="s"><v>{index[v]}</v></c>')
            out.append(f'<row r="{r}">{"".join(cells)}</row>')
        sheet_xml.append(
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<worksheet xmlns="{MAIN}"><sheetData>{"".join(out)}</sheetData></worksheet>'
        )
    names = list(sheets)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for i in range(len(names))
            )
            + '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
            "</Types>",
        )
        z.writestr(
            "_rels/.rels",
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{PKG}">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        z.writestr(
            "xl/workbook.xml",
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<workbook xmlns="{MAIN}" xmlns:r="{REL}"><sheets>'
            + "".join(
                f'<sheet name="{escape(n)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
                for i, n in enumerate(names)
            )
            + "</sheets></workbook>",
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{PKG}">'
            + "".join(
                f'<Relationship Id="rId{i + 1}" Type="{REL}/worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
                for i in range(len(names))
            )
            + f'<Relationship Id="rId{len(names) + 1}" Type="{REL}/sharedStrings" Target="sharedStrings.xml"/>'
            "</Relationships>",
        )
        for i, x in enumerate(sheet_xml):
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", x)
        z.writestr(
            "xl/sharedStrings.xml",
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<sst xmlns="{MAIN}" count="{len(shared)}" uniqueCount="{len(shared)}">'
            + "".join(f'<si><t xml:space="preserve">{escape(s)}</t></si>' for s in shared)
            + "</sst>",
        )
    return path


@pytest.fixture
def xlsx(tmp_path):
    def make(rows: list[list], sheet: str = "Full data") -> Path:
        return write_xlsx(tmp_path / "t.xlsx", {"Legend": [["x"]], sheet: rows})

    return make
