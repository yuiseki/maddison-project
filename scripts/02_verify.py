#!/usr/bin/env python3
"""Check every file under data/raw/<release>/ against its MANIFEST.json.

For each file: the size and sha256 recorded when it was fetched, the SHA-1
DataverseNL states (2023), and its content: xlsx and zip pass
zipfile.testzip, gzip is read to the end, CSV rows are counted with the csv
module, .dta starts with a Stata header, .pdf with %PDF-. A file in the
directory but not in the manifest, or the reverse, is a failure. Prints
ok/FAIL lines and exits non-zero on any failure.

    uv run python scripts/02_verify.py
"""

import csv
import gzip
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"


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

    print(f"\n{failures} failures" if failures else "\nall checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
