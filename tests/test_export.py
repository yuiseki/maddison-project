import importlib.util
from pathlib import Path

import duckdb
import pytest
from conftest import Num

_spec = importlib.util.spec_from_file_location(
    "export", Path(__file__).parents[1] / "scripts" / "03_export_parquet.py"
)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


@pytest.mark.parametrize(
    ("name", "sql"),
    [
        ("year", "INTEGER"),
        ("gdppc", "DOUBLE"),
        ("cgdppc", "DOUBLE"),
        ("rgdpnapc", "DOUBLE"),
        ("pop", "DOUBLE"),
        ("countrycode", "VARCHAR"),
        ("country", "VARCHAR"),
        ("region", "VARCHAR"),
        ("region_name", "VARCHAR"),
        ("region1870", "VARCHAR"),
        ("i_cig", "VARCHAR"),
        ("i_bm", "VARCHAR"),
        ("Year", "VARCHAR"),
        ("a_column_not_in_the_rule", "VARCHAR"),
    ],
)
def test_column_type(name, sql):
    assert m.column_type(name) == sql


def test_every_release_and_table_is_listed():
    assert [(t["version"], t["table"]) for t in m.TABLES] == [
        ("2018", "full_data"),
        ("2018", "regional_data"),
        ("2018", "region_composition"),
        ("2018", "benchmark_1990"),
        ("2020", "full_data"),
        ("2023", "full_data"),
    ]


def _rel(path, sheet="Full data"):
    con = duckdb.connect()
    con.execute("install excel; load excel")
    return con.sql(m.select_sql(con, path, sheet))


HEADER = ["countrycode", "country", "year", "gdppc", "pop", "i_cig"]


def test_values_are_typed_and_text_stays_text(xlsx):
    p = xlsx(
        [
            HEADER,
            ["AZE", "Azerbaijan", Num("2001"), Num("4498.7943999999998"), Num("8193.79"), ""],
            ["AFG", "Afghanistan", Num("1820"), None, Num("3280"), "Extrapolated"],
        ]
    )
    rel = _rel(p)
    assert dict(zip(rel.columns, rel.types, strict=True)) == {
        "countrycode": "VARCHAR",
        "country": "VARCHAR",
        "year": "INTEGER",
        "gdppc": "DOUBLE",
        "pop": "DOUBLE",
        "i_cig": "VARCHAR",
    }
    assert rel.fetchall() == [
        ("AZE", "Azerbaijan", 2001, float("4498.7943999999998"), 8193.79, ""),
        ("AFG", "Afghanistan", 1820, None, 3280.0, "Extrapolated"),
    ]


def test_a_blank_row_does_not_end_the_table_and_is_dropped(xlsx):
    p = xlsx(
        [
            HEADER,
            ["AFG", "Afghanistan", Num("1820"), None, Num("3280"), ""],
            [None, None, None, None, None, None],
            ["AGO", "Angola", Num("1820"), None, Num("1000"), ""],
        ]
    )
    assert [r[0] for r in _rel(p).fetchall()] == ["AFG", "AGO"]


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (["A", "B", Num("1820"), "n/a", None, ""], "t.xlsx, Full data: gdppc is not a number: n/a"),
        (["A", "B", Num("1820"), "1,234", None, ""], "gdppc is not a number: 1,234"),
        (["A", "B", Num("1820"), None, "", ""], "pop is not a number: "),
        (["A", "B", Num("1820.5"), None, None, ""], "year is not an integer: 1820.5"),
        (["A", "B", "c. 1820", None, None, ""], "year is not an integer: c. 1820"),
    ],
)
def test_a_value_that_does_not_fit_stops_the_run(xlsx, row, message):
    p = xlsx([HEADER, row])
    with pytest.raises(duckdb.Error, match=message.replace(".", r"\.")):
        _rel(p).fetchall()


def test_a_number_in_exponent_form_is_read(xlsx):
    p = xlsx([HEADER, ["A", "B", Num("1820"), Num("1.5E-3"), Num("2E+5"), ""]])
    assert _rel(p).fetchone()[3:5] == (0.0015, 200000.0)


def test_column_names_that_clash_without_case_stop_the_run():
    with pytest.raises(SystemExit, match="clash"):
        m.check_names(["year", "Year"], "t.xlsx")
    m.check_names(["year", "gdppc"], "t.xlsx")
