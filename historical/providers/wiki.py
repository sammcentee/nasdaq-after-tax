"""Extract research candidates from the discontinued public-domain WIKI archive.

Original publisher: https://data.nasdaq.com/databases/WIKIP
Mirror: https://www.kaggle.com/datasets/marketneutral/quandl-wiki-prices-us-equites

This is a coverage tool, not a study-data replacement. WIKI stops in 2018 and
contains ticker reuse, stale post-delisting rows and missing dividends. Issuer
identity and corporate actions require independent checks before integration.
Raw and adjusted fields are kept separately; no missing observation is filled.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import urllib.request
import zipfile


SOURCE = "https://data.nasdaq.com/databases/WIKIP"
MIRROR = ("https://www.kaggle.com/api/v1/datasets/download/marketneutral/"
          "quandl-wiki-prices-us-equites?datasetVersionNumber=1")
FIELDS = ["ticker", "date", "open", "high", "low", "close", "volume",
          "ex-dividend", "split_ratio", "adj_open", "adj_high", "adj_low",
          "adj_close", "adj_volume"]


def extract_archive(archive: Path, output: Path, symbols: list[str],
                    start: str, end: str) -> dict:
    """Inspect the whole archive, retaining only requested symbols and dates."""
    if date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError("Start date must not follow end date")
    if not symbols or any(not re.fullmatch(r"[A-Z0-9][A-Z0-9_]{0,30}", s) for s in symbols):
        raise ValueError("Specify WIKI ticker symbols using uppercase letters, digits or underscores")
    selected = {symbol: [] for symbol in symbols}
    bounds = {symbol: {"source_rows": 0, "first": None, "last": None} for symbol in symbols}
    total = 0
    with zipfile.ZipFile(archive) as zipped:
        with zipped.open("WIKI_PRICES.csv") as stream:
            reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8"))
            if reader.fieldnames != FIELDS:
                raise ValueError("Unexpected WIKI archive columns")
            for row in reader:
                total += 1
                symbol = row["ticker"]
                if symbol not in selected:
                    continue
                observed = date.fromisoformat(row["date"]).isoformat()
                info = bounds[symbol]
                info["source_rows"] += 1
                info["first"] = min(info["first"] or observed, observed)
                info["last"] = max(info["last"] or observed, observed)
                if start <= observed <= end:
                    selected[symbol].append(row)
    output.mkdir(parents=True, exist_ok=True)
    files = {}
    for symbol, rows in selected.items():
        path = output / f"{symbol}.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        files[path.name] = {"rows": len(rows), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return {"archive_rows": total, "bounds": bounds, "files": files,
            "start": start, "end": end, "ready_for_study": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", type=Path, required=True, help="Use an ignored private research directory")
    args = parser.parse_args()
    digest = hashlib.sha256()
    with tempfile.TemporaryDirectory() as folder:
        archive = Path(folder) / "wiki.zip"
        with urllib.request.urlopen(MIRROR, timeout=60) as response, archive.open("wb") as stream:
            while block := response.read(1024 * 1024):
                digest.update(block)
                stream.write(block)
        result = extract_archive(archive, args.output, args.symbols, args.start, args.end)
    result.update(source_url=SOURCE, mirror_url=MIRROR, mirror_version=1,
                  archive_sha256=digest.hexdigest(),
                  license_basis="Original publisher describes WIKI Prices as public domain")
    (args.output / "extraction.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
