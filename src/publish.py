#!/usr/bin/env python3
"""Push the card, the licence, the provenance, the Parquet and the raw files to the Hub.

Dry run by default: lists the files and their total size. With --push, the
folder data/ is uploaded with HfApi.upload_folder to yuiseki/maddison-project,
limited to the listed files. It refuses to run when a Parquet file under
data/parquet/ is not declared as a subset in data/README.md, when a table the
export makes has no Parquet, or when a raw file's sha256 is not the one in
its release's MANIFEST.json. The raw files go up unchanged.

    uv run python src/publish.py             # dry run
    uv run python src/publish.py --push
"""

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPO = "yuiseki/maddison-project"

_spec = importlib.util.spec_from_file_location("export", ROOT / "scripts" / "03_export_parquet.py")
export = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def subset_entry(version: str, table: str) -> str:
    return f"- config_name: '{version}.{table}'\n  data_files: parquet/{version}/{table}.parquet\n"


def files_to_push() -> list[str]:
    card = (DATA / "README.md").read_text(encoding="utf-8")
    files = ["README.md", "LICENSE", "provenance.yaml"]

    made = {f"parquet/{t['version']}/{t['table']}.parquet" for t in export.TABLES}
    found = {p.relative_to(DATA).as_posix() for p in (DATA / "parquet").glob("*/*.parquet")}
    if made - found:
        raise SystemExit(f"no Parquet for {sorted(made - found)}; run 03_export_parquet.py")
    for rel in sorted(found):
        version, name = rel.split("/")[1], Path(rel).stem
        if subset_entry(version, name) not in card:
            raise SystemExit(f"the card does not declare {rel} as the subset '{version}.{name}'")
    files += sorted(found)

    for mpath in sorted((DATA / "raw").glob("*/MANIFEST.json")):
        d = mpath.parent
        manifest = json.loads(mpath.read_text())["files"]
        for name, m in manifest.items():
            if sha256(d / name) != m["sha256"]:
                raise SystemExit(f"raw/{d.name}/{name} is not the file in its manifest")
        files += [f"raw/{d.name}/MANIFEST.json"] + [f"raw/{d.name}/{n}" for n in manifest]
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args()

    files = files_to_push()
    total = 0
    print(a.repo)
    for f in files:
        size = (DATA / f).stat().st_size
        total += size
        print(f"  {size:>12,}  {f}")
    print(f"  {len(files)} files, {total:,} bytes ({total / 1e6:.1f} MB)")
    if not a.push:
        print("\ndry run. pass --push to upload")
        return 0

    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(a.repo, repo_type="dataset", exist_ok=True, private=False)
    api.upload_folder(
        folder_path=str(DATA), repo_id=a.repo, repo_type="dataset", allow_patterns=files
    )
    print(f"\npushed to https://huggingface.co/datasets/{a.repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
