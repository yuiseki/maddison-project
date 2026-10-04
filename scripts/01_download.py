#!/usr/bin/env python3
"""Fetch the Maddison Project Database releases that are stated as CC BY 4.0.

The version directory is the release year (data/raw/2018, 2020, 2023): each
release is a fixed publication, not a file overwritten in place.

Where the files come from:
  - The release pages are found on the official listing
    https://www.rug.nl/ggdc/historicaldevelopment/maddison/releases/ ;
    only the releases in RELEASES are taken, and a release page that does
    not link the CC BY 4.0 licence stops the run. MPD 2013 and the
    Maddison Database 2010 state no licence and are not taken.
  - 2018 and 2020: every .xlsx, .dta and .pdf linked from the release page
    (data files on www.rug.nl, and the documentation paper).
  - 2023: the page links DataverseNL access URLs; the file list, sizes and
    SHA-1 checksums come from DataverseNL's public dataset API for the DOI
    the page names (10.34894/INZBF2). Every unrestricted file is taken, and
    each must have the stated size and SHA-1.

Each file is written to a .part file, checked against Content-Length when the
server sends one, and renamed. data/raw/<release>/MANIFEST.json records each
file's url, bytes, sha256, Last-Modified, fetch time and what the source
states. A file already in the manifest whose local copy has the recorded
sha256 is not fetched again. Requests are sequential, at least 1 s apart.
Before fetching, the stated sizes of everything missing are added up and the
run stops if they exceed MAX_TOTAL_BYTES.

    uv run python scripts/01_download.py
"""

import hashlib
import json
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
LISTING = "https://www.rug.nl/ggdc/historicaldevelopment/maddison/releases/"
DATAVERSE = "https://dataverse.nl"
RELEASES = ("2018", "2020", "2023")
MAX_TOTAL_BYTES = 500_000_000
UA = "maddison-project/1 (+https://github.com/yuiseki/maddison-project)"
FILE_SUFFIXES = (".xlsx", ".dta", ".pdf")
CC_BY_4 = re.compile(r"creativecommons\.org/licenses/by/4\.0", re.I)
RELEASE_PAGE = re.compile(r"/maddison/releases/maddison-project-database-(\d{4})$")
DATAFILE = re.compile(r"^https://dataverse\.nl/api/access/datafile/(\d+)$")
DATAVERSE_DOI = re.compile(r"^https?://doi\.org/(10\.34894/[A-Z0-9]+)$", re.I)


# ---------------------------------------------------------------- parsing


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None


def links(html: str, base: str) -> list[tuple[str, str]]:
    """Every <a href> on the page as (absolute url, link text)."""
    p = _Links()
    p.feed(html)
    return [(urllib.parse.urljoin(base, h), t) for h, t in p.links]


def release_pages(listing_html: str, base: str = LISTING) -> dict[str, str]:
    """Release year -> release page url, from the official listing page."""
    out: dict[str, str] = {}
    for url, _ in links(listing_html, base):
        m = RELEASE_PAGE.search(urllib.parse.urlsplit(url).path)
        if m:
            out.setdefault(m.group(1), url)
    return out


def states_cc_by(html: str) -> bool:
    """True when the page links the CC BY 4.0 licence."""
    return any(CC_BY_4.search(u) for u, _ in links(html, LISTING))


def datafile_id(url: str) -> int | None:
    m = DATAFILE.match(url)
    return int(m.group(1)) if m else None


def release_files(html: str, base: str) -> list[dict]:
    """Data and documentation files linked from a release page, first label kept."""
    out: dict[str, dict] = {}
    for url, text in links(html, base):
        path = urllib.parse.urlsplit(url).path.lower()
        if (path.endswith(FILE_SUFFIXES) or datafile_id(url) is not None) and url not in out:
            out[url] = {"url": url, "label": text}
    return list(out.values())


def dataverse_doi(html: str) -> str | None:
    """The DataverseNL DOI a release page names, if any."""
    for url, _ in links(html, LISTING):
        m = DATAVERSE_DOI.match(url)
        if m:
            return m.group(1)
    return None


def dataset_api_url(doi: str) -> str:
    return f"{DATAVERSE}/api/datasets/:persistentId/?persistentId=doi:{doi}"


def dataverse_files(ds: dict) -> tuple[dict, list[dict]]:
    """Dataset facts and its files from a DataverseNL dataset API response."""
    v = ds["data"]["latestVersion"]
    info = {
        "doi": v["datasetPersistentId"],
        "version": f"{v['versionNumber']}.{v['versionMinorNumber']}",
        "release_time": v["releaseTime"],
        "licence": v["license"]["name"],
        "licence_uri": v["license"]["uri"],
    }
    files = []
    for f in v["files"]:
        df = f["dataFile"]
        if df["checksum"]["type"] != "SHA-1":
            raise ValueError(f"{df['filename']}: checksum type {df['checksum']['type']}")
        files.append(
            {
                "id": df["id"],
                "filename": df["filename"],
                "bytes": df["filesize"],
                "sha1": df["checksum"]["value"],
                "content_type": df["contentType"],
                "restricted": f["restricted"],
            }
        )
    return info, files


def name_for(url: str) -> str:
    return urllib.parse.unquote(urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1])


# ---------------------------------------------------------------- network

_last = 0.0


def _request(url: str, method: str = "GET"):
    global _last
    wait = 1.0 - (time.monotonic() - _last)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
    try:
        return urllib.request.urlopen(req, timeout=300)
    finally:
        _last = time.monotonic()


def get_text(url: str) -> str:
    with _request(url) as r:
        return r.read().decode("utf-8")


def head_length(url: str) -> int | None:
    with _request(url, "HEAD") as r:
        n = r.headers.get("Content-Length")
    return int(n) if n else None


def digest(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(url: str, dest: Path) -> dict:
    tmp = dest.with_name(dest.name + ".part")
    with _request(url) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
        stated = r.headers.get("Content-Length")
        lm = r.headers.get("Last-Modified", "")
        ctype = r.headers.get("Content-Type", "")
    got = tmp.stat().st_size
    if stated is not None and got != int(stated):
        tmp.unlink()
        raise SystemExit(f"{url}: got {got} bytes, the server stated {stated}")
    tmp.replace(dest)
    return {
        "url": url,
        "bytes": got,
        "sha256": digest(dest, "sha256"),
        "last_modified": lm,
        "content_type": ctype,
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ---------------------------------------------------------------- plan


def plan_release(year: str, page_url: str) -> tuple[dict, list[dict]]:
    """What the release states, and the files to take with their stated facts."""
    html = get_text(page_url)
    if not states_cc_by(html):
        raise SystemExit(f"{year}: {page_url} does not link CC BY 4.0; not taken")
    meta = {
        "release": year,
        "page": page_url,
        "licence": "CC BY 4.0, linked from the release page",
    }
    linked = release_files(html, page_url)
    if not linked:
        raise SystemExit(f"{year}: no data files linked from {page_url}")
    ids = [datafile_id(f["url"]) for f in linked]
    if all(i is None for i in ids):
        return meta, [{**f, "name": name_for(f["url"])} for f in linked]

    # DataverseNL: the page links access URLs; names, sizes and checksums are the API's
    doi = dataverse_doi(html)
    if doi is None:
        raise SystemExit(f"{year}: the page links DataverseNL files but names no DOI")
    info, files = dataverse_files(json.loads(get_text(dataset_api_url(doi))))
    meta["dataverse"] = {**info, "api": dataset_api_url(doi)}
    by_id = {f["id"]: f for f in files}
    labels = {datafile_id(f["url"]): f["label"] for f in linked}
    missing = [i for i in ids if i is not None and i not in by_id]
    if missing:
        raise SystemExit(f"{year}: the page links datafiles {missing} the dataset does not list")
    out = []
    for f in files:
        if f["restricted"]:
            print(f"{year}: {f['filename']} is restricted, skipped")
            continue
        out.append(
            {
                "url": f"{DATAVERSE}/api/access/datafile/{f['id']}",
                "label": labels.get(f["id"], ""),
                "name": f["filename"],
                "dataverse_file_id": f["id"],
                "stated_bytes": f["bytes"],
                "stated_sha1": f["sha1"],
                "stated_content_type": f["content_type"],
            }
        )
    return meta, out


def is_current(d: Path, manifest: dict, name: str) -> bool:
    e = manifest.get("files", {}).get(name)
    return e is not None and (d / name).exists() and digest(d / name, "sha256") == e["sha256"]


def main() -> int:
    pages = release_pages(get_text(LISTING))
    absent = [y for y in RELEASES if y not in pages]
    if absent:
        raise SystemExit(f"releases {absent} are not on {LISTING}")

    plans = []
    for year in RELEASES:
        d = RAW / year
        mpath = d / "MANIFEST.json"
        manifest = json.loads(mpath.read_text()) if mpath.exists() else {}
        meta, files = plan_release(year, pages[year])
        todo = [f for f in files if not is_current(d, manifest, f["name"])]
        plans.append((year, d, mpath, manifest, meta, todo))

    total = 0
    for year, _, _, _, _, todo in plans:
        for f in todo:
            n = f.get("stated_bytes") or head_length(f["url"])
            if n is None:
                raise SystemExit(f"{year}/{f['name']}: no stated size; cannot check the limit")
            total += n
    print(f"{sum(len(p[5]) for p in plans)} files to fetch, {total:,} bytes stated")
    if total > MAX_TOTAL_BYTES:
        raise SystemExit(f"{total:,} bytes exceeds the limit of {MAX_TOTAL_BYTES:,}; stopped")

    for year, d, mpath, manifest, meta, todo in plans:
        d.mkdir(parents=True, exist_ok=True)
        files = manifest.get("files", {})
        manifest = {**meta, "files": files}
        for f in todo:
            entry = fetch(f["url"], d / f["name"])
            entry["label"] = f["label"]
            for k in ("dataverse_file_id", "stated_bytes", "stated_sha1", "stated_content_type"):
                if k in f:
                    entry[k] = f[k]
            if "stated_bytes" in f and entry["bytes"] != f["stated_bytes"]:
                raise SystemExit(
                    f"{year}/{f['name']}: {entry['bytes']} bytes, stated {f['stated_bytes']}"
                )
            if "stated_sha1" in f and digest(d / f["name"], "sha1") != f["stated_sha1"]:
                raise SystemExit(f"{year}/{f['name']}: SHA-1 differs from DataverseNL's")
            files[f["name"]] = entry
            mpath.write_text(json.dumps(manifest, indent=1) + "\n")
            print(f"{year}/{f['name']}: {entry['bytes']:,} bytes, {entry['last_modified']}")
        mpath.write_text(json.dumps(manifest, indent=1) + "\n")
        if not todo:
            print(f"{year}: nothing new ({len(files)} files current)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
