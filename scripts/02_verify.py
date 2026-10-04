#!/usr/bin/env python3
"""Check every file under data/raw/<release>/ against its MANIFEST.json, and the Parquet.

For each raw file: the size and sha256 recorded when it was fetched, the
SHA-1 DataverseNL states (2023), and its content: xlsx and zip pass
zipfile.testzip, gzip is read to the end, CSV rows are counted with the csv
module, .dta starts with a Stata header, .pdf with %PDF-. A file in the
directory but not in the manifest, or the reverse, is a failure.

For each Parquet table (when data/parquet/ exists):
  - the sheet is read again with the standard library alone (zipfile and
    xml.etree), without DuckDB's excel extension, and its rows are counted
  - the Parquet has that many rows, and the pinned number
  - every value equals the cell it came from, typed as the export types it,
    row by row in sheet order; a sha256 over all values is printed for both
  - every column has the type column_type gives its name
  - the key (country or region, and year) is unique where the table has one
  - a plain DuckDB with no extension loaded opens the file
  - no row group carries a bloom filter

Prints ok/FAIL lines and exits non-zero on any failure.

    uv run python scripts/02_verify.py
"""

import csv
import gzip
import hashlib
import importlib.util
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PQ = ROOT / "data" / "parquet"
EXPECTED_ROWS = {
    "2018.full_data": 19873, "2018.regional_data": 1039, "2018.region_composition": 147,
    "2018.benchmark_1990": 17872, "2020.full_data": 21682, "2023.full_data": 131144,
}  # fmt: skip
KEYS = {
    "full_data": ("countrycode", "year"), "benchmark_1990": ("countrycode", "year"),
    "regional_data": ("region", "year"), "region_composition": ("countrycode",),
}  # fmt: skip
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

_spec = importlib.util.spec_from_file_location("export", ROOT / "scripts" / "03_export_parquet.py")
export = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export)


def digest(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def check_content(path: Path) -> tuple[bool, str]:
    """Open the file the way its type allows and say what was found."""
    suffix = path.suffix.lower()
    try:
        if suffix in (".xlsx", ".zip"):
            with zipfile.ZipFile(path) as z:
                bad = z.testzip()
                if bad:
                    return False, f"zip member {bad} is corrupt"
                return True, f"zip ok, {len(z.namelist())} members"
        if suffix == ".gz":
            n = 0
            with gzip.open(path, "rb") as f:
                for block in iter(lambda: f.read(1 << 20), b""):
                    n += len(block)
            return True, f"gzip ok, {n:,} bytes inside"
        if suffix == ".csv":
            with open(path, encoding="utf-8", newline="") as f:
                rows = sum(1 for _ in csv.reader(f)) - 1
            return True, f"{rows:,} rows"
        if suffix == ".dta":
            head = path.read_bytes()[:64]
            m = re.match(rb"<stata_dta><header><release>(\d+)</release>", head)
            if m:
                return True, f"Stata release {m.group(1).decode()}"
            if head and head[0] in (113, 114, 115):
                return True, f"Stata format {head[0]}"
            return False, "no Stata header"
        if suffix == ".pdf":
            head = path.read_bytes()[:16]
            m = re.match(rb"%PDF-(\d\.\d)", head)
            return (True, f"PDF {m.group(1).decode()}") if m else (False, "no %PDF- header")
    except (
        OSError,
        zipfile.BadZipFile,
        gzip.BadGzipFile,
        EOFError,
        UnicodeDecodeError,
        csv.Error,
    ) as e:
        return False, f"{type(e).__name__}: {e}"
    return True, "no content check for this type"


def _col(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_sheet(path: Path, sheet: str) -> tuple[list[str], list[list]]:
    """Header and rows of one sheet as the text of each cell, standard library only.

    A shared string is resolved to its text, a number is the text in <v>, an
    empty cell is None. Rows with no value at all are left out, as the export
    leaves them out. A value right of the header stops the read.
    """
    with zipfile.ZipFile(path) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rid = next(s.get(RNS + "id") for s in wb.iter(NS + "sheet") if s.get("name") == sheet)
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = next(r.get("Target") for r in rels if r.get("Id") == rid).lstrip("/")
        target = target if target.startswith("xl/") else "xl/" + target
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(NS + "si"):
                shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
        header: list[str] | None = None
        rows: list[list] = []
        with z.open(target) as f:
            for _, el in ET.iterparse(f):
                if el.tag != NS + "row":
                    continue
                cells = {}
                for c in el.iter(NS + "c"):
                    t, v = c.get("t"), c.find(NS + "v")
                    if t == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter(NS + "t"))
                    elif v is None:
                        val = None
                    elif t == "s":
                        val = shared[int(v.text)]
                    else:
                        val = v.text
                    if val is not None:
                        cells[_col(c.get("r"))] = val
                el.clear()
                if header is None:
                    header = [cells.get(i) for i in range(max(cells) + 1)]
                    continue
                if not cells:
                    continue
                if max(cells) >= len(header):
                    raise ValueError(f"{path.name}, {sheet}: a value right of the header")
                rows.append([cells.get(i) for i in range(len(header))])
    return header or [], rows


def typed(row: list, types: list[str]) -> tuple:
    """A raw row typed as the export types it, with Python's int and float."""
    conv = {"INTEGER": int, "DOUBLE": float, "VARCHAR": str}
    return tuple(None if x is None else conv[t](x) for x, t in zip(row, types, strict=True))


def values_sha256(rows) -> str:
    h = hashlib.sha256()
    for r in rows:
        h.update(repr(tuple(r)).encode())
    return h.hexdigest()


def check_parquet(report) -> None:
    import duckdb

    con = duckdb.connect()
    con.execute("set memory_limit = '8GB'")
    plain = duckdb.connect()
    for t in export.TABLES:
        name = f"{t['version']}.{t['table']}"
        p = PQ / t["version"] / f"{t['table']}.parquet"
        if not p.exists():
            report(False, f"{name}: {p.relative_to(ROOT)} missing")
            continue
        header, raw = read_sheet(RAW / t["version"] / t["file"], t["sheet"])
        types = [export.column_type(c) for c in header]
        want = [typed(r, types) for r in raw]
        got = con.sql(
            f"select * exclude (file_row_number) from read_parquet('{p}', file_row_number = true) "
            "order by file_row_number"
        ).fetchall()
        report(
            len(got) == len(want) == EXPECTED_ROWS[name],
            f"{name}: {len(got):,} rows, {len(want):,} in the sheet, {EXPECTED_ROWS[name]:,} pinned",
        )
        a, b = values_sha256(want), values_sha256(got)
        report(got == want and a == b, f"{name}: every value as in the sheet (sha256 {b[:16]})")

        cols = con.sql(f"select column_name, column_type from (describe from '{p}')").fetchall()
        report(
            [c for c, _ in cols] == header,
            f"{name}: columns as the sheet's header {header}",
        )
        wrong = {c: ty for c, ty in cols if ty != export.column_type(c)}
        report(not wrong, f"{name}: every column has its type ({wrong or 'all as named'})")

        key = KEYS[t["table"]]
        k = ", ".join(key)
        dup = con.sql(
            f"select count(*) from (select {k} from '{p}' group by all having count(*) > 1)"
        ).fetchone()[0]
        report(dup == 0, f"{name}: ({k}) unique")

        n = plain.sql(f"select count(*) from '{p}'").fetchone()[0]
        ext = plain.sql(
            "select count(*) from duckdb_extensions() where loaded and extension_name = 'excel'"
        ).fetchone()[0]
        report(
            n == len(want) and ext == 0, f"{name}: a DuckDB without the excel extension opens it"
        )

        bloom = con.sql(
            f"select count(*) filter (where bloom_filter_offset is not null) from parquet_metadata('{p}')"
        ).fetchone()[0]
        report(bloom == 0, f"{name}: no bloom filters")


def main() -> int:
    failures = 0

    def report(ok: bool, what: str) -> None:
        nonlocal failures
        print(("ok    " if ok else "FAIL  ") + what)
        failures += not ok

    manifests = sorted(RAW.glob("*/MANIFEST.json"))
    report(bool(manifests), f"{len(manifests)} releases with a MANIFEST.json under {RAW}")
    for mpath in manifests:
        d = mpath.parent
        rel = d.name
        files = json.loads(mpath.read_text())["files"]
        on_disk = {p.name for p in d.iterdir() if p.name != "MANIFEST.json"}
        extra = sorted(on_disk - files.keys())
        report(not extra, f"{rel}: no files outside the manifest {extra or ''}".rstrip())
        for name, e in files.items():
            p = d / name
            if not p.exists():
                report(False, f"{rel}/{name}: missing")
                continue
            size = p.stat().st_size
            report(size == e["bytes"], f"{rel}/{name}: {size:,} bytes")
            report(digest(p, "sha256") == e["sha256"], f"{rel}/{name}: sha256 as in MANIFEST")
            if "stated_sha1" in e:
                report(
                    digest(p, "sha1") == e["stated_sha1"],
                    f"{rel}/{name}: SHA-1 as DataverseNL states",
                )
            ok, what = check_content(p)
            report(ok, f"{rel}/{name}: {what}")

    if PQ.exists():
        check_parquet(report)
    else:
        print("      no data/parquet/ yet, Parquet not checked")

    print(f"\n{failures} failures" if failures else "\nall checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
