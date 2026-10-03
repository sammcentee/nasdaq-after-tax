"""Read-only, RAM-only Tiingo EOD coverage probe; not a study-data replacement.

API: https://www.tiingo.com/documentation/end-of-day
Terms: https://app.tiingo.com/tos/ (sections 1.6(a) and 1.6(c)).
Starter data must never be persisted. This module has no download/cache writer;
the CLI retains only aggregate coverage counts, not prices or issuer metadata.
Callers must also avoid saving returned frames or reconstructable trade ledgers.

Prices and dividends remain in the security's original currency (USD for the
study's US stocks). Dividend dates are ex-dates. The split column preserves the
vendor's splitFactor; distributions can also affect this field, so corporate
actions need independent review before engine integration. Neither adjusted
prices nor adjusted dividends are used. Issuer identity is NOT verified here:
recycled ticker symbols can refer to a different company.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import math
import os
from pathlib import Path
import re

import pandas as pd
import requests


class TiingoError(ValueError):
    """Safe-to-display error without request credentials or response bodies."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def normalize_daily(rows: list[dict]) -> pd.DataFrame:
    """Return raw date/close/dividend/split observations, without adjustment."""
    if not isinstance(rows, list):
        raise TiingoError("Expected a daily-price list from Tiingo")
    columns = ["date", "close", "dividend", "split"]
    if not rows:
        return pd.DataFrame(columns=columns)
    try:
        frame = pd.DataFrame(rows)[["date", "close", "divCash", "splitFactor"]].copy()
        frame.columns = columns
        frame["date"] = pd.to_datetime(frame.date, utc=True, errors="raise").dt.tz_localize(None).dt.normalize()
        for column in columns[1:]:
            frame[column] = pd.to_numeric(frame[column], errors="raise")
    except (KeyError, TypeError, ValueError):
        raise TiingoError("Invalid daily-price fields from Tiingo") from None
    if frame.date.isna().any() or frame.date.duplicated().any():
        raise TiingoError("Missing or duplicate daily-price dates from Tiingo")
    if (not frame[columns[1:]].map(math.isfinite).all().all()
            or (frame.close <= 0).any() or (frame.dividend < 0).any()
            or (frame.split <= 0).any()):
        raise TiingoError("Invalid daily-price amounts from Tiingo")
    return frame.sort_values("date").reset_index(drop=True)


class TiingoClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = (api_key if api_key is not None else os.environ.get("TIINGO_API_KEY", "")).strip()
        if not self.api_key or len(self.api_key.splitlines()) != 1:
            raise TiingoError("Set TIINGO_API_KEY or supply a one-line --key-file")

    def _get(self, symbol: str, suffix: str = "", params: dict | None = None):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,30}", symbol):
            raise TiingoError("Invalid Tiingo symbol; use hyphens for share classes")
        try:
            response = requests.get(
                f"https://api.tiingo.com/tiingo/daily/{symbol.upper()}{suffix}",
                params=params,
                headers={"Authorization": f"Token {self.api_key}"},
                timeout=30,
            )
        except requests.RequestException:
            raise TiingoError("Tiingo request failed; no response content retained") from None
        if response.status_code != 200:
            raise TiingoError(f"Tiingo returned HTTP {response.status_code}; check access and rate limits",
                              status_code=response.status_code)
        try:
            return response.json()
        except ValueError:
            raise TiingoError("Tiingo returned invalid JSON") from None

    def metadata(self, symbol: str) -> dict:
        metadata = self._get(symbol)
        if not isinstance(metadata, dict):
            raise TiingoError("Expected an issuer metadata object from Tiingo")
        return metadata

    def daily(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        try:
            first, last = date.fromisoformat(start), date.fromisoformat(end)
        except ValueError:
            raise TiingoError("Use ISO dates YYYY-MM-DD") from None
        if first > last:
            raise TiingoError("Start date must not follow end date")
        rows = self._get(symbol, "/prices", {"startDate": first.isoformat(), "endDate": last.isoformat()})
        frame = normalize_daily(rows)
        if not frame.empty and not frame.date.between(pd.Timestamp(first), pd.Timestamp(last)).all():
            raise TiingoError("Tiingo returned dates outside the requested interval")
        return frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", required=True, help="Up to 25 priority tickers; two requests each")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--key-file", type=Path, help="Private one-line token file; otherwise use TIINGO_API_KEY")
    args = parser.parse_args()
    if len(args.symbols) > 25:
        parser.error("Probe at most 25 symbols to stay within one 50-request hourly allowance")
    counts = {"symbols_requested": len(args.symbols), "symbols_with_prices": 0,
              "symbols_without_prices": 0, "symbols_not_found": 0, "metadata_without_date_range": 0,
              "metadata_starts_after_requested_start": 0,
              "metadata_ends_before_requested_end": 0,
              "issuer_identities_verified": 0, "ready_for_study": False}
    try:
        first, last = date.fromisoformat(args.start), date.fromisoformat(args.end)
        if first > last:
            raise TiingoError("Start date must not follow end date")
        key = args.key_file.read_text(encoding="utf-8").strip() if args.key_file else None
        client = TiingoClient(key)
        for symbol in args.symbols:
            metadata = frame = None
            try:
                metadata = client.metadata(symbol)
                if metadata.get("startDate") and metadata.get("endDate"):
                    counts["metadata_starts_after_requested_start"] += date.fromisoformat(metadata["startDate"][:10]) > first
                    counts["metadata_ends_before_requested_end"] += date.fromisoformat(metadata["endDate"][:10]) < last
                else:
                    counts["metadata_without_date_range"] += 1
                frame = client.daily(symbol, args.start, args.end)
                counts["symbols_without_prices" if frame.empty else "symbols_with_prices"] += 1
            except TiingoError as error:
                if error.status_code != 404:
                    raise
                counts["symbols_not_found"] += 1
            finally:
                del frame, metadata
    except TiingoError as error:
        print(json.dumps({"probe_completed": False, "error": str(error)}))
        return 1
    except (OSError, ValueError, TypeError):
        print(json.dumps({"probe_completed": False, "error": "Invalid date, metadata date, or unreadable key file"}))
        return 1
    print(json.dumps({"probe_completed": True, **counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
