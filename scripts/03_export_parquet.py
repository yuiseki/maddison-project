#!/usr/bin/env python3
"""Turn each release's tables into typed Parquet, for the Hub viewer and DuckDB.

The tables are read from the xlsx files with DuckDB's excel extension; the
dta files beside them are not read. Each table is one sheet that is already
a plain table, one header row and one row per observation:

    2018  full_data           mpd2018.xlsx, sheet "Full data"
    2018  regional_data       mpd2018_region_data.xlsx, sheet "Long data"
    2018  region_composition  mpd2018_region_data.xlsx, sheet "Composition"
    2018  benchmark_1990      mpd2018_1990bm.xlsx, sheet "LongForm"
    2020  full_data           mpd2020.xlsx, sheet "Full data"
    2023  full_data           mpd2023_web.xlsx, sheet "Full data"

Every cell is read as its text (all_varchar) and typed by the column's name,
never by inference: year is INTEGER; gdppc, cgdppc, rgdpnapc and pop are
DOUBLE; every other column stays the text of the cell. A value is checked
with a regular expression before the cast; one that does not fit stops the
run with an error naming the file, sheet, column and value.

The sheet is read to its last row (stop_at_empty false), so a blank row in
the middle does not cut the table short. Rows with no value in any column,
such as the 126 formatted but empty rows at the foot of the 2018 sheet, are
dropped. Rows keep the order of the sheet. Files are written with zstd and
without bloom filters.

    uv run python scripts/03_export_parquet.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "parquet"

TABLES = [
    {"version": "2018", "table": "full_data", "file": "mpd2018.xlsx", "sheet": "Full data"},
    {"version": "2018", "table": "regional_data", "file": "mpd2018_region_data.xlsx", "sheet": "Long data"},
    {"version": "2018", "table": "region_composition", "file": "mpd2018_region_data.xlsx", "sheet": "Composition"},
    {"version": "2018", "table": "benchmark_1990", "file": "mpd2018_1990bm.xlsx", "sheet": "LongForm"},
    {"version": "2020", "table": "full_data", "file": "mpd2020.xlsx", "sheet": "Full data"},
    {"version": "2023", "table": "full_data", "file": "mpd2023_web.xlsx", "sheet": "Full data"},
]  # fmt: skip

INTEGERS = {"year"}
DOUBLES = {"gdppc", "cgdppc", "rgdpnapc", "pop"}
INTEGER_RE = "[0-9]+"
NUMBER_RE = "-?[0-9]+([.][0-9]+)?([eE][-+]?[0-9]+)?"


def column_type(name: str) -> str:
    if name in INTEGERS:
        return "INTEGER"
    if name in DOUBLES:
        return "DOUBLE"
    return "VARCHAR"


def check_names(names: list[str], where: str) -> None:
    """DuckDB matches column names without case; two that differ only in case would clash."""
    seen: dict[str, str] = {}
    for n in names:
        if n.lower() in seen:
            raise SystemExit(f"{where}: columns {seen[n.lower()]!r} and {n!r} clash in DuckDB")
        seen[n.lower()] = n


def _q(s: str) -> str:
    return s.replace("'", "''")


def _expr(where: str, name: str) -> str:
    c, t = f'"{name}"', column_type(name)
    if t == "VARCHAR":
        return c
    pattern, what = (INTEGER_RE, "an integer") if t == "INTEGER" else (NUMBER_RE, "a number")
    return (
        f"case when {c} is null then null "
        f"when regexp_full_match({c}, '{pattern}') then cast({c} as {t}) "
        f"else error('{_q(where)}: {_q(name)} is not {what}: ' || {c}) end"
    )


def source_sql(path: Path, sheet: str) -> str:
    return (
        f"read_xlsx('{_q(str(path))}', sheet = '{_q(sheet)}', header = true, "
        "all_varchar = true, stop_at_empty = false)"
    )


def select_sql(con, path: Path, sheet: str) -> str:
    src = source_sql(path, sheet)
    names = con.sql(f"select * from {src} limit 0").columns
    where = f"{path.name}, {sheet}"
    check_names(names, where)
    cols = ", ".join(f'{_expr(where, n)} as "{n}"' for n in names)
    not_blank = " or ".join(f'"{n}" is not null' for n in names)
    return f"select {cols} from {src} where {not_blank}"


def main() -> int:
    import duckdb

    con = duckdb.connect()
    con.execute("set memory_limit = '8GB'; install excel; load excel")
    for t in TABLES:
        src = RAW / t["version"] / t["file"]
        out = OUT / t["version"]
        out.mkdir(parents=True, exist_ok=True)
        p = out / f"{t['table']}.parquet"
        con.execute(
            f"copy ({select_sql(con, src, t['sheet'])}) to '{p}' "
            "(format parquet, compression zstd, write_bloom_filter false)"
        )
        n = con.sql(f"select count(*) from '{p}'").fetchone()[0]
        print(f"{t['version']}.{t['table']}: {n:,} rows, {p.stat().st_size:,} bytes", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
