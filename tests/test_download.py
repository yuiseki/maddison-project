import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
BASE = "https://www.rug.nl/ggdc/historicaldevelopment/maddison/releases/"

_spec = importlib.util.spec_from_file_location("download", ROOT / "scripts" / "01_download.py")
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


def page(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_release_pages_from_the_listing():
    got = m.release_pages(page("releases_listing.html"), BASE)
    assert got == {
        y: f"{BASE}maddison-project-database-{y}" for y in ("2013", "2018", "2020", "2023")
    }


def test_the_2010_maddison_database_is_not_a_release_page():
    got = m.release_pages(page("releases_listing.html"), BASE)
    assert not any("2010" in u for u in got.values())


@pytest.mark.parametrize(
    ("name", "stated"),
    [
        ("release_2018.html", True),
        ("release_2020.html", True),
        ("release_2023.html", True),
        ("release_2013.html", False),
    ],
)
def test_states_cc_by(name, stated):
    assert m.states_cc_by(page(name)) is stated


def test_release_files_2018():
    url = f"{BASE}maddison-project-database-2018"
    got = m.release_files(page("release_2018.html"), url)
    assert [m.name_for(f["url"]) for f in got] == [
        "mpd2018.xlsx",
        "mpd2018.dta",
        "gd174.pdf",
        "mpd2018_region_data.xlsx",
        "mpd2018_region_data.dta",
        "mpd2018_1990bm.xlsx",
        "mpd2018_1990bm.dta",
    ]
    assert got[0] == {
        "url": "https://www.rug.nl/ggdc/historicaldevelopment/maddison/data/mpd2018.xlsx",
        "label": "Excel",
    }
    # the paper is linked twice; the first label is kept
    assert got[2]["url"] == "https://www.rug.nl/ggdc/html_publications/memorandum/gd174.pdf"
    assert got[2]["label"] == "documentation"


def test_release_files_2020():
    url = f"{BASE}maddison-project-database-2020"
    got = m.release_files(page("release_2020.html"), url)
    assert [m.name_for(f["url"]) for f in got] == ["mpd2020.xlsx", "mpd2020.dta", "wp15.pdf"]


def test_release_files_2023_are_dataverse_access_links():
    url = f"{BASE}maddison-project-database-2023"
    got = m.release_files(page("release_2023.html"), url)
    assert got == [
        {"url": "https://dataverse.nl/api/access/datafile/421302", "label": "Excel"},
        {"url": "https://dataverse.nl/api/access/datafile/421303", "label": "Stata"},
    ]
    assert [m.datafile_id(f["url"]) for f in got] == [421302, 421303]


def test_datafile_id_of_a_plain_file_is_none():
    assert m.datafile_id("https://www.rug.nl/ggdc/x/mpd2020.xlsx") is None


def test_dataverse_doi_from_the_2023_page():
    assert m.dataverse_doi(page("release_2023.html")) == "10.34894/INZBF2"
    assert m.dataverse_doi(page("release_2020.html")) is None


def test_dataverse_files():
    ds = json.loads(page("dataverse_INZBF2.json"))
    info, files = m.dataverse_files(ds)
    assert info == {
        "doi": "doi:10.34894/INZBF2",
        "version": "1.0",
        "release_time": "2024-04-26T08:43:37Z",
        "licence": "CC-BY-4.0",
        "licence_uri": "http://creativecommons.org/licenses/by/4.0",
    }
    assert files == [
        {
            "id": 421303,
            "filename": "maddison2023_web.dta",
            "bytes": 10892389,
            "sha1": "264862c8a188d4bc770b607663211ec1c4eb0d5d",
            "content_type": "application/x-stata-14",
            "restricted": False,
        },
        {
            "id": 421302,
            "filename": "mpd2023_web.xlsx",
            "bytes": 4903804,
            "sha1": "1480521f602fbd5df64e108867ac971caa00ed1a",
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "restricted": False,
        },
    ]


def test_dataset_api_url():
    assert m.dataset_api_url("10.34894/INZBF2") == (
        "https://dataverse.nl/api/datasets/:persistentId/?persistentId=doi:10.34894/INZBF2"
    )


@pytest.mark.parametrize(
    ("url", "name"),
    [
        (
            "https://www.rug.nl/ggdc/historicaldevelopment/maddison/data/mpd2020.xlsx",
            "mpd2020.xlsx",
        ),
        ("https://www.rug.nl/ggdc/html_publications/memorandum/gd174.pdf", "gd174.pdf"),
    ],
)
def test_name_for(url, name):
    assert m.name_for(url) == name
