"""Repeat the full study in a fresh output directory and compare every result."""
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/latest"


def contents(path):
    data = path.read_bytes()
    return gzip.decompress(data) if path.suffix == ".gz" else data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    manifest = OUT / "study_manifest.json"
    manifest_hash = hashlib.sha256(manifest.read_bytes()).hexdigest()
    checks, hashes = [], {}
    with TemporaryDirectory(prefix="nasdaq-replay-") as temporary:
        copied = Path(temporary) / "historical"
        shutil.copytree(ROOT, copied, ignore=shutil.ignore_patterns("results", "__pycache__"))
        subprocess.run([sys.executable, str(copied / "run_tax_optimization_study.py"),
                        "--workers", str(args.workers)], check=True)
        for fresh in sorted((copied / "results/latest").rglob("*")):
            if not fresh.is_file():
                continue
            relative = fresh.relative_to(copied / "results/latest")
            saved = OUT / relative
            if fresh.suffix == ".json":
                assert json.loads(fresh.read_text()) == json.loads(saved.read_text()), relative
                method = "parsed_json_exact"
            elif not contents(fresh).strip():
                assert contents(fresh) == contents(saved), relative
                method = "empty_csv_bytes_exact"
            else:
                pd.testing.assert_frame_equal(pd.read_csv(fresh, low_memory=False),
                                              pd.read_csv(saved, low_memory=False), check_exact=True)
                method = "parsed_csv_exact"
            checks.append(dict(file=str(relative), method=method, status="PASS"))
            hashes[str(saved.relative_to(ROOT))] = hashlib.sha256(contents(saved)).hexdigest()
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == manifest_hash, "Study changed during replay"
    study = json.loads(manifest.read_text())
    result = dict(
        classification="CACHED_INPUT_REPLAY_VERIFICATION",
        assessment_date=datetime.now(timezone.utc).date().isoformat(),
        command="python historical/checks/verify_replay.py --workers " + str(args.workers),
        method="Fresh run in an isolated copy with no saved results. Compare every generated JSON and CSV exactly after parsing. This repeats the same engine and inputs; it is not independent source validation.",
        source_state="Working tree bound by the study manifest input and code hashes",
        stock_replays=study["stock_replays"], etf_replays=1,
        files_compared=len(checks), all_match=True, files=checks,
        study_manifest_sha256=manifest_hash, output_sha256=hashes,
        verification_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        output_hash_method="SHA256 of file bytes after decompression for .gz files; container timestamps are excluded.")
    (OUT / "accuracy_replay.json").write_text(json.dumps(result, indent=2)+"\n")
    print(f"Full replay: {len(checks)} output files match exactly after parsing.")


if __name__ == "__main__":
    main()
