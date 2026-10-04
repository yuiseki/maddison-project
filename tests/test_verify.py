import gzip
import importlib.util
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location("verify", ROOT / "scripts" / "02_verify.py")
v = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v)


def test_xlsx_is_tested_as_a_zip(tmp_path):
    good = tmp_path / "a.xlsx"
    with zipfile.ZipFile(good, "w") as z:
        z.writestr("xl/workbook.xml", "<workbook/>")
    assert v.check_content(good) == (True, "zip ok, 1 members")
    bad = tmp_path / "b.xlsx"
    bad.write_bytes(b"not a zip")
    ok, _ = v.check_content(bad)
    assert not ok


def test_dta_header(tmp_path):
    new = tmp_path / "a.dta"
    new.write_bytes(b"<stata_dta><header><release>118</release>")
    assert v.check_content(new) == (True, "Stata release 118")
    old = tmp_path / "b.dta"
    old.write_bytes(bytes([115, 2, 1, 0]))
    assert v.check_content(old) == (True, "Stata format 115")
    bad = tmp_path / "c.dta"
    bad.write_bytes(b"<html>")
    assert not v.check_content(bad)[0]


def test_pdf_header(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF-1.5\n...")
    assert v.check_content(p) == (True, "PDF 1.5")
    q = tmp_path / "b.pdf"
    q.write_bytes(b"<!doctype html>")
    assert not v.check_content(q)[0]


def test_csv_rows_and_gzip(tmp_path):
    c = tmp_path / "a.csv"
    c.write_text('a,b\n1,"x\ny"\n2,z\n', encoding="utf-8")
    assert v.check_content(c) == (True, "2 rows")
    g = tmp_path / "a.gz"
    g.write_bytes(gzip.compress(b"x" * 1000))
    assert v.check_content(g) == (True, "gzip ok, 1,000 bytes inside")
