#!/usr/bin/env python3
"""
Build point-in-time historical membership lists for the S&P 500 and Nasdaq-100.

Output format matches the fja05680/sp500 convention:

    date,tickers
    1996-01-02,"AAL,AAMRQ,AAPL,..."

Each row is a full snapshot of index membership *effective on that date*; a new
row is emitted only on dates when membership changed. To get membership on any
query date, take the most recent row with date <= query date.

Sources (all parsed from structured wiki tables, NOT revision-history diffs):
  * S&P 500 : fja05680 base (1996 .. 2026-01-14, authoritative) + the Wikipedia
              "Selected changes" table applied FORWARD for the post-base gap.
  * Nasdaq-100: reconstructed BACKWARD from the current Wikipedia components
              table by un-applying the Wikipedia "Component changes" table
              (covers 2007 .. present).

Validation gates (see build_*): forward/backward reconstruction must reproduce
the independently-parsed current components table; integrity + count + spot
checks are reported.

Usage:
    python build.py fetch              # (re)download Wikipedia sources
    python build.py build [--as-of YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import re
import subprocess
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "data", "raw")

UA = "sp500nq100-membership-builder/0.1 (drummania@gmail.com)"

SOURCES = {
    # fja05680 base is a FIXED historical anchor; pinned filename intentionally.
    "sp500_fja_base.csv": (
        "https://raw.githubusercontent.com/fja05680/sp500/refs/heads/master/"
        "S%26P%20500%20Historical%20Components%20%26%20Changes(01-17-2026).csv"
    ),
    "sp500_wiki.wikitext": (
        "https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&action=raw"
    ),
    "nq100_wiki.wikitext": (
        "https://en.wikipedia.org/w/index.php?title=Nasdaq-100&action=raw"
    ),
}

# ---------------------------------------------------------------------------
# wikitext helpers
# ---------------------------------------------------------------------------

_RE_REF_SELF = re.compile(r"<ref[^>]*?/>", re.IGNORECASE)
_RE_REF_PAIR = re.compile(r"<ref[^>]*?>.*?</ref\s*>", re.DOTALL | re.IGNORECASE)
_RE_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_RE_CELL_SEP = re.compile(r"(?:\n\s*\|)|(?:\|\|)")
_RE_US_DATE = re.compile(r"([A-Za-z]+)\.?\s+(\d{1,2}),\s*(\d{4})")
_RE_WIKILINK = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]|]*)\]\]")
_RE_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")


def strip_refs(s: str) -> str:
    # self-closing reuses (<ref name="x" />) MUST go first: otherwise the paired
    # regex matches "<ref .../>" as an opening tag and eats forward to the next
    # real </ref>, deleting every table row in between.
    s = _RE_REF_SELF.sub("", s)
    s = _RE_REF_PAIR.sub("", s)
    s = _RE_COMMENT.sub("", s)
    return s


def wiki_to_text(s: str) -> str:
    """Flatten wikilinks/templates/bold to plain text (for reason fields)."""
    s = strip_refs(s)
    prev = None
    while prev != s:  # nested templates
        prev = s
        s = _RE_TEMPLATE.sub("", s)
    s = _RE_WIKILINK.sub(r"\1", s)
    s = s.replace("'''", "").replace("''", "")
    return re.sub(r"\s+", " ", s).strip()


def clean_ticker(cell: str) -> str:
    """Extract a bare ticker symbol from a (possibly wiki-linked) table cell."""
    cell = strip_refs(cell)
    m = _RE_WIKILINK.search(cell)
    if m:
        cell = m.group(1)
    cell = cell.replace("'''", "").replace("''", "").strip()
    # keep only the leading symbol token (letters, digits, dot, dash)
    m = re.match(r"[A-Za-z0-9.\-]+", cell)
    tok = m.group(0).upper() if m else ""
    return tok


def parse_us_date(cell: str) -> dt.date | None:
    cell = strip_refs(cell)
    m = _RE_US_DATE.search(cell)
    if not m:
        return None
    mon, day, year = m.group(1), int(m.group(2)), int(m.group(3))
    for fmt in ("%B", "%b"):
        try:
            month = dt.datetime.strptime(mon[:9] if fmt == "%B" else mon[:3], fmt).month
            return dt.date(year, month, day)
        except ValueError:
            continue
    return None


def extract_table(wikitext: str, table_id: str) -> str:
    """Return the wikitext slice for the table whose opening line has id="<id>"."""
    lines = wikitext.splitlines()
    start = None
    for i, ln in enumerate(lines):
        s = ln.lstrip()
        if s.startswith("{|") and f'id="{table_id}"' in ln:
            start = i
            break
    if start is None:
        raise ValueError(f'table id="{table_id}" not found')
    for j in range(start + 1, len(lines)):
        if lines[j].strip() == "|}":
            return "\n".join(lines[start : j + 1])
    raise ValueError(f'table id="{table_id}" not closed')


def split_cells(chunk: str) -> list[str]:
    chunk = chunk.strip()
    if chunk.startswith("|"):
        chunk = chunk[1:]
    return [p.strip() for p in _RE_CELL_SEP.split(chunk)]


# ---------------------------------------------------------------------------
# parsers
# ---------------------------------------------------------------------------

def parse_changes_table(wikitext: str, table_id: str = "changes") -> list[dict]:
    """Parse a Wikipedia index "changes" table.

    Schema (both S&P 500 and Nasdaq-100):
        Date | Added(Ticker, Security) | Removed(Ticker, Security) | Reason
    Returns a list of {date, added:set[str], removed:set[str], reason:str},
    skipping header/blank rows. Rows whose cell count != schema are reported.
    """
    table = strip_refs(extract_table(wikitext, table_id))
    # split into row chunks on lines that are exactly a row separator "|-"
    chunks = re.split(r"(?m)^\s*\|-.*$", table)
    out: list[dict] = []
    problems: list[str] = []
    for chunk in chunks:
        if not chunk.strip():
            continue
        cells = split_cells(chunk)
        date = parse_us_date(cells[0]) if cells else None
        if date is None:
            continue  # header / opening "{|" line / notes
        if len(cells) < 6:
            problems.append(f"  short row ({len(cells)} cells): {cells!r}")
            continue
        added = clean_ticker(cells[1])
        removed = clean_ticker(cells[3])
        out.append(
            {
                "date": date,
                "added": {added} if added else set(),
                "removed": {removed} if removed else set(),
                "reason": wiki_to_text(" ".join(cells[5:])),
            }
        )
    if problems:
        print(f"[warn] {table_id}: {len(problems)} unparsed rows:", file=sys.stderr)
        for p in problems:
            print(p, file=sys.stderr)
    return out


_RE_SP_SYMBOL = re.compile(r"\{\{(?:[A-Za-z]+Symbol|BZX link)\|\s*([^}|]+?)\s*\}\}")


def parse_sp_components(wikitext: str) -> set[str]:
    """Current S&P 500 tickers from the id="constituents" table.

    The symbol cell is the first cell of each row; almost all use
    {{NyseSymbol|X}} / {{NasdaqSymbol|X}}, but Cboe uses {{BZX link|CBOE}}.
    Parse row-by-row and warn on any unrecognised encoding.
    """
    table = extract_table(wikitext, "constituents")
    syms, missed = set(), []
    for ch in re.split(r"(?m)^\s*\|-.*$", table):
        ch = ch.strip()
        if not ch or ch.startswith("{|") or ch.startswith("!"):
            continue
        first = split_cells(ch)[0]
        m = _RE_SP_SYMBOL.search(first)
        if m:
            syms.add(clean_ticker(m.group(1)))
            continue
        tok = clean_ticker(first)
        if re.fullmatch(r"[A-Z][A-Z0-9.]*", tok or ""):
            syms.add(tok)
        else:
            missed.append(first[:80])
    if missed:
        print(f"[warn] sp constituents: {len(missed)} rows with unparsed symbol:", file=sys.stderr)
        for m in missed:
            print("  " + m, file=sys.stderr)
    return syms


def parse_nq_components(wikitext: str) -> set[str]:
    """Current Nasdaq-100 tickers from the id="constituents" table.

    Rows look like:  | ADBE || [[Adobe Inc.]] || Technology || Computer Software
    """
    table = extract_table(wikitext, "constituents")
    out = set()
    for ln in table.splitlines():
        if not ln.lstrip().startswith("|"):
            continue
        if ln.lstrip().startswith("|}") or ln.strip().startswith("|-"):
            continue
        if "||" not in ln:
            continue
        first = ln.lstrip()[1:].split("||", 1)[0].strip()
        tok = clean_ticker(first)
        if re.fullmatch(r"[A-Z][A-Z0-9.]*", tok or ""):
            out.add(tok)
    return out


# ---------------------------------------------------------------------------
# reconstruction
# ---------------------------------------------------------------------------

def group_by_date(changes: list[dict]) -> list[tuple[dt.date, set, set]]:
    by: dict[dt.date, tuple[set, set]] = defaultdict(lambda: (set(), set()))
    for c in changes:
        add, rem = by[c["date"]]
        add |= c["added"]
        rem |= c["removed"]
        by[c["date"]] = (add, rem)
    return [(d, by[d][0], by[d][1]) for d in sorted(by)]


def read_fja(path: str) -> list[tuple[str, list[str]]]:
    rows = []
    with open(path, newline="") as f:
        r = csv.reader(f)
        next(r)  # header
        for date_str, tickers in r:
            rows.append((date_str, tickers.split(",")))
    return rows


def write_csv(path: str, rows: list[tuple[str, list[str]]]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "tickers"])
        for date_str, tickers in rows:
            w.writerow([date_str, ",".join(sorted(set(tickers)))])


def fmt_set_diff(name_a: str, a: set, name_b: str, b: set) -> str:
    only_a = sorted(a - b)
    only_b = sorted(b - a)
    lines = [f"    |{name_a}|={len(a)}  |{name_b}|={len(b)}  matched={len(a & b)}"]
    if only_a:
        lines.append(f"    only in {name_a} ({len(only_a)}): {', '.join(only_a)}")
    if only_b:
        lines.append(f"    only in {name_b} ({len(only_b)}): {', '.join(only_b)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Ticker renames (NOT index changes -> excluded from the Wikipedia changes
# tables by policy, so reconstruction must handle them explicitly).
#
# NQ_CANON collapses a renamed pair to ONE representative for set operations so
# a name's add (old ticker) and removal (new ticker) pair up instead of leaving
# a phantom member. Verified from the changes-table add/remove history.
#   continuous current members -> collapse to current ticker
#   departed names             -> collapse to the earlier ticker
NQ_CANON: dict[str, str] = {
    "FB": "META", "KFT": "MDLZ", "PCLN": "BKNG", "HANS": "MNST",
    "WTW": "WLTW", "TCOM": "CTRP", "WFM": "WFMI",
    "NWSA": "TCFCA",   # News Corp class A (2009) -> 21st Century Fox class A lineage
    "FI": "FISV",      # Fiserv left NDX (2023) as FISV; FI is its later symbol
}

# Spurious changes-table rows to drop (membership non-events recorded as adds).
# 2016-02-01 "+AVGO": Avago *renamed* itself Broadcom (already a member since
# 2011); the real event was -BRCM, which is separately recorded on 2015-11-11.
NQ_DROP_ROWS: set[tuple[dt.date, str]] = {(dt.date(2016, 2, 1), "AVGO")}

# Relabel a specific changes-table cell. 2014-12-22 multi-class add "FOX" is
# 21st Century Fox class B (= TCFCB), distinct from new Fox Corp's later "FOX".
NQ_RELABEL: dict[tuple[dt.date, str], str] = {(dt.date(2014, 12, 22), "FOX"): "TCFCB"}

# Uniform internal->real-ticker map for Wikipedia disambiguation labels.
NQ_DISPLAY_MAP: dict[str, str] = {"TCFCA": "FOXA", "TCFCB": "FOX"}

# Point-in-time symbol pass: (new, old, effective). Snapshots dated >= effective
# show `new`; earlier snapshots show `old`. Applied to final rows of each index.
SP_RENAMES: list[tuple[str, str, dt.date]] = [
    ("BNY", "BK", dt.date(2026, 5, 21)),   # BNY Mellon ticker change
]
NQ_RENAMES: list[tuple[str, str, dt.date]] = [
    ("META", "FB", dt.date(2022, 6, 9)),
    ("BKNG", "PCLN", dt.date(2018, 2, 27)),
    ("MDLZ", "KFT", dt.date(2012, 10, 2)),
    ("MNST", "HANS", dt.date(2012, 1, 5)),
]
# GOOG/GOOGL is NOT a 1:1 rename (class A GOOG->GOOGL in 2014 AND class C reused
# "GOOG"), so it is handled one-directionally below, not via apply_renames.
GOOG_SPLIT = dt.date(2014, 4, 3)


def apply_renames(rows, renames):
    """Rewrite each snapshot's tickers to the symbol valid on that row's date."""
    out = []
    for date_str, tickers in rows:
        d = dt.date.fromisoformat(date_str)
        s = set(tickers)
        for new, old, eff in renames:
            if d >= eff and old in s:
                s.discard(old); s.add(new)
            elif d < eff and new in s:
                s.discard(new); s.add(old)
        out.append((date_str, sorted(s)))
    return out


def insert_carry_rows(rows, eff_dates):
    """Insert a carry-forward snapshot at each effective date that lacks a row,
    so a ticker rename shows up on its exact date rather than the next change."""
    by = {d: list(t) for d, t in rows}
    for eff in eff_dates:
        es = eff.isoformat()
        if es in by:
            continue
        prior = [d for d in by if d <= es]
        if prior:
            by[es] = list(by[max(prior)])
    return sorted(by.items())


def build_sp500(as_of: dt.date) -> dict:
    wiki = open(os.path.join(RAW, "sp500_wiki.wikitext")).read()
    base = read_fja(os.path.join(RAW, "sp500_fja_base.csv"))
    base_last_date = dt.date.fromisoformat(base[-1][0])
    changes = group_by_date(parse_changes_table(wiki))
    now = parse_sp_components(wiki)

    gap = [(d, a, r) for (d, a, r) in changes if base_last_date < d <= as_of]
    cur = set(base[-1][1])
    bridge, warns = [], []
    for d, add, rem in gap:
        for t in rem:
            if t not in cur:
                warns.append(f"{d}: remove {t} not in set (ticker mismatch / missing prior change)")
        for t in add:
            if t in cur:
                warns.append(f"{d}: add {t} already present")
        cur = (cur - rem) | add
        bridge.append((d.isoformat(), sorted(cur)))

    rows = [(d, sorted(set(t))) for d, t in base] + bridge
    rows = insert_carry_rows(rows, [e for _, _, e in SP_RENAMES])
    rows = apply_renames(rows, SP_RENAMES)
    write_csv(os.path.join(ROOT, "sp500_components_history.csv"), rows)
    final = set(rows[-1][1])
    return {
        "rows": rows, "bridge": bridge, "warns": warns,
        "recon": final, "now": now, "base_last_date": base_last_date,
        "match": final == now,
    }


def build_nq100(as_of: dt.date) -> dict:
    wiki = open(os.path.join(RAW, "nq100_wiki.wikitext")).read()
    now = parse_nq_components(wiki)  # already in current (canonical) tickers

    raw = parse_changes_table(wiki)
    canon = lambda s: {NQ_CANON.get(t, t) for t in s}
    norm = []
    for c in raw:
        added = set()
        for t in c["added"]:
            if (c["date"], t) in NQ_DROP_ROWS:
                continue
            added.add(NQ_RELABEL.get((c["date"], t), t))
        norm.append({"date": c["date"], "added": canon(added), "removed": canon(c["removed"])})
    changes = [(d, a, r) for (d, a, r) in group_by_date(norm) if d <= as_of]

    # backward walk: membership is reconstructed in canonical tickers
    cur = set(now)
    rows_desc, integrity = [], []
    for d, add, rem in reversed(changes):
        rows_desc.append((d.isoformat(), sorted(cur)))
        for t in add:
            if t not in cur:
                integrity.append(f"{d}: +{t} not in forward membership (missing removal / symbol reuse)")
        cur = (cur - add) | rem
    pre_first = sorted(cur)  # membership just before the earliest recorded change

    rows = insert_carry_rows(list(reversed(rows_desc)), [e for _, _, e in NQ_RENAMES])
    rows = [(d, sorted({NQ_DISPLAY_MAP.get(t, t) for t in ts})) for d, ts in rows]
    rows = apply_renames(rows, NQ_RENAMES)  # point-in-time symbols
    # Google class A was "GOOG" before the 2014 class-C split; relabel only that
    # single pre-split line (post-split GOOG class C is a distinct member).
    rows = [(d, sorted({("GOOG" if (t == "GOOGL" and dt.date.fromisoformat(d) < GOOG_SPLIT) else t)
                        for t in ts})) for d, ts in rows]
    write_csv(os.path.join(ROOT, "nasdaq100_components_history.csv"), rows)
    counts = [len(t) for _, t in rows]
    big = [(d, len(t)) for d, t in rows if len(t) > 102]
    latest = set(max(rows, key=lambda r: r[0])[1])
    return {
        "rows": rows, "now": now, "integrity": integrity, "big": big,
        "counts": (min(counts), max(counts)), "pre_first": pre_first,
        "first_date": rows[0][0], "n_pre_first": len(pre_first),
        "match": latest == now,
    }


def first_appearance(rows: list[tuple[str, list[str]]], ticker: str) -> str | None:
    prev = False
    for d, ts in rows:
        here = ticker in ts
        if here and not prev:
            return d
        prev = here
    return None


def main_build(as_of: dt.date) -> int:
    sp = build_sp500(as_of)
    nq = build_nq100(as_of)

    print("=" * 72)
    print(f"S&P 500   (as-of {as_of})")
    print("=" * 72)
    print(f"base (fja05680) through {sp['base_last_date']}; bridge rows added: {len(sp['bridge'])}")
    for d, ts in sp["bridge"]:
        print(f"  + bridge {d}  -> {len(ts)} tickers")
    print(f"output rows: {len(sp['rows'])}  ({sp['rows'][0][0]} .. {sp['rows'][-1][0]})")
    print(f"\nVALIDATION  forward-reconstructed set  vs  current Wikipedia components:")
    print("  " + ("PASS — identical" if sp["match"] else "DIFF:"))
    if not sp["match"]:
        print(fmt_set_diff("reconstructed", sp["recon"], "wiki_now", sp["now"]))
    if sp["warns"]:
        print(f"  integrity notes ({len(sp['warns'])}):")
        for w in sp["warns"]:
            print("   - " + w)

    print("\n" + "=" * 72)
    print(f"NASDAQ-100   (as-of {as_of})")
    print("=" * 72)
    print(f"reconstructed BACKWARD from {len(nq['now'])} current components")
    print(f"VALIDATION  latest snapshot vs current components: "
          + ("PASS — identical" if nq["match"] else "FAIL (latest row != current!)"))
    print(f"output rows: {len(nq['rows'])}  ({nq['rows'][0][0]} .. {nq['rows'][-1][0]})")
    print(f"snapshot size range: {nq['counts'][0]}..{nq['counts'][1]}")
    print(f"pre-{nq['first_date']} membership size (before earliest recorded change): {nq['n_pre_first']}")
    print(f"\nINTEGRITY  '+ticker not in forward membership' (residual gaps): {len(nq['integrity'])}")
    for w in nq["integrity"]:
        print("   - " + w)
    if nq["big"]:
        yrs = sorted({d[:4] for d, _ in nq["big"]})
        print(f"  snapshots >102 members (residual pre-2019 multi-class/phantom): "
              f"{len(nq['big'])} rows in years {', '.join(yrs)}")
    print("\nSPOT CHECKS (first appearance walking forward):")
    for tk in ["PLTR", "MSTR", "AXON", "META", "FB", "GOOGL", "GOOG", "NVDA", "TSLA"]:
        print(f"   {tk:6s} first present: {first_appearance(nq['rows'], tk)}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["fetch", "build", "diagnose"])
    ap.add_argument("--as-of", default=dt.date.today().isoformat())
    args = ap.parse_args()
    as_of = dt.date.fromisoformat(args.as_of)
    if args.action == "fetch":
        os.makedirs(RAW, exist_ok=True)
        for fname, url in SOURCES.items():
            dest = os.path.join(RAW, fname)
            if fname.endswith(".csv") and os.path.exists(dest):
                print(f"[skip] {fname} (pinned base already present)")
                continue
            print(f"[get ] {fname}")
            subprocess.run(["curl", "-sS", "--max-time", "60", "-A", UA, url, "-o", dest], check=True)
        sys.exit(0)
    sys.exit(main_build(as_of))
