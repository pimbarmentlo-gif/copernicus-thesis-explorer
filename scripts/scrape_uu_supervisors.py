#!/usr/bin/env python3
"""Scrape UU staff profiles for supervisors that appear in the thesis explorer.

One-off script. Run from the repo root:

    pip install requests beautifulsoup4 lxml
    python scripts/scrape_uu_supervisors.py

Outputs:
    dashboard/supervisor_profiles.json
    dashboard/static/uu_photos/<slug>.jpg
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
import time
import unicodedata as ud
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup


# ── Paths ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
PROGRAMS_DIR = REPO_ROOT / "programs"
DASHBOARD_DIR = REPO_ROOT / "dashboard"
OUTPUT_JSON = DASHBOARD_DIR / "supervisor_profiles.json"
PHOTOS_DIR = DASHBOARD_DIR / "static" / "uu_photos"

CSV_FILENAME = "thesis_metadata_matched.csv"
PROGRAMS = [
    "energy_science",
    "innovation_sciences",
    "sbi",
    "sustainable_development",
    "water_management",
]

# ── UU endpoints ─────────────────────────────────────────────────────────────
UU_BASE = "https://www.uu.nl"
COPERNICUS_SECTIONS = [
    ("Energy & Resources",
     f"{UU_BASE}/en/research/copernicus-institute-of-sustainable-development/about-us/people/staff-energy-and-resources"),
    ("Environmental Governance",
     f"{UU_BASE}/en/research/copernicus-institute-of-sustainable-development/about-us/people/staff-environmental-governance"),
    ("Environmental Sciences",
     f"{UU_BASE}/en/research/copernicus-institute-of-sustainable-development/about-us/people/staff-environmental-sciences"),
    ("Innovation Studies",
     f"{UU_BASE}/en/research/copernicus-institute-of-sustainable-development/about-us/people/staff-innovation-studies"),
    ("Urban Futures Studio",
     f"{UU_BASE}/en/research/copernicus-institute-of-sustainable-development/about-us/people/staff-urban-futures-studio"),
]
SEARCH_URL = f"{UU_BASE}/staff/Search"

REQUEST_HEADERS = {
    "User-Agent": "ThesisExplorerScraper/1.0 (student project; pim.barmentlo@gmail.com)",
    "Accept": "text/html,application/xhtml+xml",
}
REQUEST_TIMEOUT = 25
REQUEST_DELAY = 1.2          # be nice; gap between fresh fetches
RATE_LIMIT_BACKOFF = 90      # seconds to wait after a 429
MAX_429_RETRIES = 2

CACHE_DIR = REPO_ROOT / ".cache" / "uu_html"


# ─────────────────────────────────────────────────────────────────────────────
# Name normalisation — mirrors dashboard.py
# ─────────────────────────────────────────────────────────────────────────────
_TITLE_PAT = re.compile(
    r'^(?:[\s\.,;:]+)?(?:Prof\.?\s*Dr\.?|Prof\.?|Dr\.?|Ir\.?|Drs\.?|'
    r'Mr\.?|Ms\.?|Mrs\.?|Dhr\.?|Mw\.?|Ing\.?|Ass\.?\s*Prof\.?|'
    r'Assoc\.?\s*Prof\.?|Emer\.?(?:\s*Prof\.)?)(?!\w)\s*',
    re.I,
)
_PARTICLES = {
    'de', 'den', 'der', 'van', 'von', 'ten', 'ter', 'te', 'op', 'het', 'la',
}
_NAME_FIXES: dict[str, str] = {
    'marko hekkert': 'Marco Hekkert',
    'jesus rosalen carreon': 'Jesus Rosales Carreon',
    'alonzo fradejas': 'Alberto Alonso Fradejas',
    'frank laerhoven': 'Frank van Laerhoven',
    'carel van dieperink': 'Carel Dieperink',
    'kees van de leeuwen': 'Kees van Leeuwen',
    'ine dorrestijn': 'Ine Dorresteijn',
    'martin junginer': 'Martin Junginger',
    'thomas bouwens': 'Thomas Bauwens',
    'elena fumagali': 'Elena Fumagalli',
    'heitor mancini texeira': 'Heitor Mancini Teixeira',
    'heitor teixeira': 'Heitor Mancini Teixeira',
    'heitor mancini': 'Heitor Mancini Teixeira',
    'iannis lampropoules': 'Ioannis Lampropoulos',
    'wouter boons': 'Wouter Boon',
    'ernst werrel': 'Ernst Worrell',
    'mariska te beet': 'Mariska te Beest',
    'mariska the beest': 'Mariska te Beest',
    'matthijs jansen': 'Matthijs Janssen',
    'abe hendrick': 'Abe Hendriks',
    'gaston heimriks': 'Gaston Heimeriks',
    'simona de negro': 'Simona Negro',
    'gert-jan kramer': 'Gert Jan Kramer',
    'dora martins sampaio': 'Dora Sampaio',
    'kim rak': 'Rakhyun Kim',
    'verkade n': 'Nick Verkade',
    'h van der loos': 'Adriaan van der Loos',
    'l van beek': 'Rens van Beek',
    'pr joost vervoort': 'Joost Vervoort',
    'stefanie lutz phd': 'Stefanie Lutz',
    'j wesseling msc': 'Joeri Wesseling',
    'jesus rosalescarreon': 'Jesus Rosales Carreon',
    'w graus': 'Wina Crijns-Graus',
}


def _strip_titles(s: str) -> str:
    s = s.strip().lstrip('.,;: ')
    while True:
        m = _TITLE_PAT.match(s)
        if m:
            s = s[m.end():].strip().lstrip('.,;: ')
        else:
            return s


def _fold_ascii(s: str) -> str:
    return ''.join(ch for ch in ud.normalize('NFKD', s) if not ud.combining(ch))


def _name_tokens(s: str) -> list[str]:
    s = _strip_titles(s)
    s = re.sub(r'\([^)]*\)', ' ', s)
    s = s.replace('/', ' ')
    s = re.sub(r'\.(?=[A-Za-z])', ' ', s)
    s = re.sub(r'[^\w\-\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    if not s:
        return []
    return [t for t in s.split(' ') if t]


def _is_initial(tok: str) -> bool:
    t = tok.replace('.', '')
    return bool(t) and len(t) <= 3 and t.isalpha() and t.upper() == t


def _title_case_name(s: str) -> str:
    bits = []
    for b in s.split():
        lb = b.lower()
        if lb in _PARTICLES:
            bits.append(lb)
        elif '-' in b:
            bits.append('-'.join(p.capitalize() for p in b.split('-')))
        else:
            bits.append(b.capitalize())
    return ' '.join(bits)


def _first_last_from_tokens(toks: list[str]):
    if len(toks) < 2:
        return None, None
    first = toks[0]
    start = len(toks) - 1
    while start - 1 >= 1 and toks[start - 1].lower() in _PARTICLES:
        start -= 1
    if start == len(toks) - 1 and start - 1 >= 1 and not _is_initial(toks[start - 1]):
        start -= 1
        while start - 1 >= 1 and toks[start - 1].lower() in _PARTICLES:
            start -= 1
    last = ' '.join(toks[start:])
    return first, last


def build_person(name: str) -> dict | None:
    """Return a record with cluster_key + display name, matching dashboard.py."""
    toks = _name_tokens(name)
    first, last = _first_last_from_tokens(toks)
    if not first or not last:
        return None
    first_clean = first.replace('.', '')
    last_clean = _title_case_name(last)
    display = f'{first_clean} {last_clean}'
    key = _fold_ascii(f'{first_clean} {last_clean}'.lower())
    if key in _NAME_FIXES:
        fixed = _NAME_FIXES[key]
        first_clean = fixed.split()[0]
        last_clean = ' '.join(fixed.split()[1:])
        display = fixed
    return {
        'first': first_clean,
        'last': last_clean,
        'first_is_initial': _is_initial(first),
        'display': display,
        'cluster_key': (
            _fold_ascii(last_clean.lower()),
            first_clean[0].lower(),
        ),
    }


def _split_cell(cell: str) -> list[str]:
    if cell is None:
        return []
    raw = str(cell).strip()
    if raw.lower() in ('n/a', 'nan', ''):
        return []
    parts = [_strip_titles(x) for x in raw.split(',')]
    return [p for p in parts if p and p.lower() not in ('n/a', 'nan', '') and len(p) > 1]


# ─────────────────────────────────────────────────────────────────────────────
# Canonical supervisor set from CSVs
# ─────────────────────────────────────────────────────────────────────────────

def build_canonical_supervisors() -> dict[tuple, str]:
    """Walk all programmes' thesis CSVs and return cluster_key → canonical display."""
    cluster_stats: dict[tuple, Counter] = defaultdict(Counter)
    total_rows = 0
    for prog in PROGRAMS:
        csv_path = PROGRAMS_DIR / prog / CSV_FILENAME
        if not csv_path.exists():
            print(f"  ! missing CSV: {csv_path}")
            continue
        with csv_path.open(newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_rows += 1
                for col in ('Supervisor', 'Second reader'):
                    for name in _split_cell(row.get(col, '')):
                        p = build_person(name)
                        if not p:
                            continue
                        score = 3 if not p['first_is_initial'] else 1
                        score += len(p['first']) / 100.0
                        cluster_stats[p['cluster_key']][p['display']] += score
    print(f"  scanned {total_rows} thesis rows across {len(PROGRAMS)} programmes")
    canon: dict[tuple, str] = {}
    for k, choices in cluster_stats.items():
        canon[k] = choices.most_common(1)[0][0]
    return canon


# ─────────────────────────────────────────────────────────────────────────────
# HTTP / fetch helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(url: str) -> Path:
    h = hashlib.sha1(url.encode('utf-8')).hexdigest()
    return CACHE_DIR / f"{h}.html"


def fetch(url: str, use_cache: bool = True) -> str | None:
    """GET a URL with disk cache + automatic backoff on 429."""
    cp = _cache_path(url)
    if use_cache and cp.exists() and cp.stat().st_size > 200:
        return cp.read_text(encoding='utf-8')

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    attempts = 0
    while True:
        attempts += 1
        try:
            r = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        except Exception as e:
            print(f"  fetch error {url}: {e}")
            return None
        if r.status_code == 200:
            cp.write_text(r.text, encoding='utf-8')
            time.sleep(REQUEST_DELAY)
            return r.text
        if r.status_code == 429 and attempts <= MAX_429_RETRIES:
            print(f"  HTTP 429 — backing off {RATE_LIMIT_BACKOFF}s ({url})")
            time.sleep(RATE_LIMIT_BACKOFF)
            continue
        print(f"  HTTP {r.status_code} for {url}")
        return None


def slug_for(canonical_name: str) -> str:
    s = _fold_ascii(canonical_name.lower())
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s or 'unknown'


def download_photo(photo_url: str, slug: str) -> str | None:
    """Save photo locally; return the relative path used by the dashboard."""
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    dst = PHOTOS_DIR / f"{slug}.jpg"
    rel = f"static/uu_photos/{slug}.jpg"
    if dst.exists() and dst.stat().st_size > 0:
        return rel
    try:
        r = requests.get(photo_url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT, stream=True)
        if r.status_code != 200:
            print(f"  photo HTTP {r.status_code} for {photo_url}")
            return None
        data = r.content
        # UU sometimes returns an empty 1x1 placeholder; require >2KB
        if len(data) < 2048:
            return None
        dst.write_bytes(data)
        return rel
    except Exception as e:
        print(f"  photo error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Section page harvest
# ─────────────────────────────────────────────────────────────────────────────

def harvest_section(section_name: str, url: str) -> list[dict]:
    html = fetch(url)
    if not html:
        return []
    soup = BeautifulSoup(html, 'lxml')
    out: list[dict] = []
    for card in soup.find_all('div', class_='profile'):
        link = card.find('a', href=re.compile(r'/staff/[A-Za-z]+'))
        if not link:
            continue
        href = link.get('href', '')
        if href.startswith('/'):
            href = UU_BASE + href
        raw_name = link.get_text(' ', strip=True)
        out.append({
            'section': section_name,
            'raw_name': raw_name,
            'profile_url': href,
        })
    return out


def harvest_all_sections() -> list[dict]:
    harvested: list[dict] = []
    for name, url in COPERNICUS_SECTIONS:
        print(f"  fetching section: {name}")
        rows = harvest_section(name, url)
        print(f"    found {len(rows)} staff entries")
        harvested.extend(rows)
    return harvested


# ─────────────────────────────────────────────────────────────────────────────
# Profile page parsing
# ─────────────────────────────────────────────────────────────────────────────

def clean_bio(text: str, max_sentences: int = 2, max_chars: int = 320) -> str:
    text = re.sub(r'\s+', ' ', text).strip()
    parts = re.split(r'(?<=[.!?])\s+', text)
    out = ' '.join(parts[:max_sentences]).strip()
    if len(out) > max_chars:
        out = out[:max_chars].rsplit(' ', 1)[0] + '…'
    return out


def parse_profile(url: str) -> dict:
    """Return a dict with whichever fields could be extracted."""
    html = fetch(url)
    out: dict = {'uu_url': url}
    if not html:
        return out
    soup = BeautifulSoup(html, 'lxml')

    # H1: full displayed name (with titles).
    h1 = soup.find('h1')
    if h1:
        out['_h1'] = h1.get_text(' ', strip=True)

    # Position block: <div class="position"> with stacked <div> children.
    pos = soup.find('div', class_='position')
    if pos:
        children = pos.find_all('div', recursive=False)
        lines: list[str] = []
        for c in children:
            txt = c.get_text(' ', strip=True)
            if txt and txt not in lines:
                lines.append(txt)
        if lines:
            out['position'] = lines[0]
            # Drop the faculty bullet (often "Geosciences") and the duplicated
            # research-group / section line. We want institute + group.
            tail = [t for t in lines[1:] if t.lower() not in {'geosciences'}]
            # dedupe consecutive equal entries
            dedup: list[str] = []
            for t in tail:
                if not dedup or dedup[-1] != t:
                    dedup.append(t)
            if dedup:
                out['department_group'] = ' · '.join(dedup[:3])

    # Areas of expertise: heading text → next <ul> items.
    for el in soup.find_all(string=lambda s: s and 'Areas of expertise' in s):
        parent = el.find_parent()
        ul = parent.find_next('ul') if parent else None
        if ul:
            items = [li.get_text(' ', strip=True) for li in ul.find_all('li')]
            items = [i for i in items if i]
            if items:
                out['expertise'] = items[:20]
        break

    # Photo
    img = soup.find('img', src=lambda s: s and 'GetImage' in s)
    if img and img.get('src'):
        src = img['src']
        if src.startswith('/'):
            src = UU_BASE + src
        out['_photo_src'] = src

    # Bio: first prose paragraph with 60-700 chars in the main column.
    main = soup.find('main') or soup
    for p in main.find_all('p'):
        txt = p.get_text(' ', strip=True)
        if 60 < len(txt) < 700:
            out['bio'] = clean_bio(txt)
            break

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Search fallback (for supervisors not in Copernicus sections)
# ─────────────────────────────────────────────────────────────────────────────

def search_for_lastname(lastname: str) -> list[dict]:
    url = f"{SEARCH_URL}?medewerker={lastname}"
    html = fetch(url)
    if not html:
        return []
    soup = BeautifulSoup(html, 'lxml')
    out: list[dict] = []
    # UU staff search rendered server-side embeds card links the same way.
    for link in soup.find_all('a', href=re.compile(r'/staff/[A-Za-z]+(?:$|["\'?#])')):
        href = link.get('href', '')
        if href.startswith('/'):
            href = UU_BASE + href
        raw_name = link.get_text(' ', strip=True)
        if not raw_name or 'staff' in raw_name.lower():
            continue
        out.append({'section': None, 'raw_name': raw_name, 'profile_url': href})
    # Dedup by URL.
    seen = set()
    dedup: list[dict] = []
    for r in out:
        if r['profile_url'] in seen:
            continue
        seen.add(r['profile_url'])
        dedup.append(r)
    return dedup


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────

_URL_SLUG_PAT = re.compile(r'/staff/([A-Za-z]+)')
_INITIALS_PAT = re.compile(r'^([A-Z]+?)([A-Z][a-z].*)$')


def url_initials_for(url: str) -> list[str]:
    """Pull the leading-initials letters from a /staff/<slug> URL.

    E.g. 'ETAHoefnagels' → ['e','t','a']; 'FHBBiermann' → ['f','h','b'];
    'CGMKleinGoldewijk' → ['c','g','m']; 'RKim' → ['r'].
    """
    m = _URL_SLUG_PAT.search(url)
    if not m:
        return []
    slug = m.group(1)
    m2 = _INITIALS_PAT.match(slug)
    if not m2:
        return []
    return list(m2.group(1).lower())


_BRACKET_PAT = re.compile(r'\(([^)]+)\)')


def bracketed_alias(raw_name: str) -> str | None:
    """Return a bracketed nickname like 'Kees' from 'C.G.M. (Kees) Klein Goldewijk'."""
    m = _BRACKET_PAT.search(raw_name)
    if not m:
        return None
    inner = m.group(1).strip()
    if ' ' in inner or len(inner) < 2:
        return None
    return inner


def index_by_cluster(harvested: Iterable[dict]) -> dict[tuple, dict]:
    """Map cluster_key → harvest record, preferring richer (longer) raw names.

    Also indexes aliases derived from the /staff URL initials and from
    bracketed nicknames in the raw name, so an entry like
    "dr. ir. C.G.M. (Kees) Klein Goldewijk" is reachable under
    ('klein goldewijk', 'c'), ('klein goldewijk', 'g'),
    ('klein goldewijk', 'm') and ('klein goldewijk', 'k').
    """
    idx: dict[tuple, dict] = {}

    def _put(ck: tuple, rec: dict, primary: bool):
        prev = idx.get(ck)
        # Primary keys always win; aliases only fill empty slots.
        if prev is None:
            idx[ck] = rec
            return
        if primary and not prev.get('_primary'):
            idx[ck] = rec
            return
        if primary and len(rec['raw_name']) > len(prev['raw_name']):
            idx[ck] = rec

    for rec in harvested:
        p = build_person(rec['raw_name'])
        if not p:
            continue
        last = p['cluster_key'][0]

        # Primary cluster_key (from displayed first-name initial).
        primary_rec = dict(rec, _primary=True)
        _put(p['cluster_key'], primary_rec, primary=True)

        # Alias: bracketed nickname (e.g. "(Kees)").
        alias = bracketed_alias(rec['raw_name'])
        if alias:
            alias_ck = (last, alias[0].lower())
            if alias_ck != p['cluster_key']:
                _put(alias_ck, dict(rec, _primary=False), primary=False)

        # Alias: initials from the staff URL slug.
        for ini in url_initials_for(rec['profile_url']):
            ck = (last, ini)
            if ck != p['cluster_key']:
                _put(ck, dict(rec, _primary=False), primary=False)
    return idx


def main() -> int:
    print("== Building canonical supervisor set from CSVs ==")
    canon = build_canonical_supervisors()
    print(f"  → {len(canon)} canonical supervisor clusters")

    print("\n== Harvesting Copernicus section pages ==")
    harvested = harvest_all_sections()
    harvested_idx = index_by_cluster(harvested)
    print(f"  → {len(harvested_idx)} unique staff clusters across sections")

    # For section context, also remember which section each cluster came from.
    section_by_cluster: dict[tuple, str] = {}
    for rec in harvested:
        p = build_person(rec['raw_name'])
        if not p:
            continue
        section_by_cluster.setdefault(p['cluster_key'], rec['section'])

    print("\n== Matching canonical supervisors → UU profiles ==")
    # Resume: keep entries already resolved in a prior run.
    profiles: dict[str, dict] = {}
    if OUTPUT_JSON.exists():
        try:
            profiles = json.loads(OUTPUT_JSON.read_text())
            print(f"  resuming from existing JSON ({len(profiles)} prior entries)")
        except Exception:
            profiles = {}
    unmatched_canon: list[str] = []

    for cluster_key, display_name in sorted(canon.items(), key=lambda kv: kv[1].lower()):
        if display_name in profiles and any(k in profiles[display_name]
                                            for k in ('position', 'expertise', 'bio', 'photo_path')):
            continue
        hit = harvested_idx.get(cluster_key)
        if not hit:
            # The UU /staff/Search endpoint returns a JavaScript SPA shell with
            # no embedded results, so a HTTP-only fallback can't help. Names
            # that aren't on the Copernicus organogram are simply skipped.
            unmatched_canon.append(display_name)
            continue

        print(f"  · {display_name}  ←  {hit['profile_url']}")
        prof = parse_profile(hit['profile_url'])

        entry: dict = {
            'uu_url': prof.get('uu_url', hit['profile_url']),
            'scraped_at': str(date.today()),
        }
        if prof.get('position'):
            entry['position'] = prof['position']
        # Prefer the section name as the department label when present, else
        # the parsed institute/group chain from the profile.
        dept = section_by_cluster.get(cluster_key)
        if dept and dept not in (None, ''):
            entry['department_group'] = f"Copernicus Institute · {dept}"
        elif prof.get('department_group'):
            entry['department_group'] = prof['department_group']
        if prof.get('expertise'):
            entry['expertise'] = prof['expertise']
        if prof.get('bio'):
            entry['bio'] = prof['bio']
        if prof.get('_photo_src'):
            slug = slug_for(display_name)
            rel = download_photo(prof['_photo_src'], slug)
            if rel:
                entry['photo_path'] = rel

        # Only keep the entry if at least one substantive field was populated.
        if any(k in entry for k in ('position', 'expertise', 'bio', 'photo_path')):
            profiles[display_name] = entry
            # Save after every successful profile so an interruption (or 429
            # streak) doesn't waste the work we already did.
            OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
            tmp = OUTPUT_JSON.with_suffix('.json.tmp')
            tmp.write_text(json.dumps(profiles, indent=2, ensure_ascii=False))
            os.replace(tmp, OUTPUT_JSON)

    print(f"\n== Resolved {len(profiles)} / {len(canon)} supervisors ==")
    print(f"   unmatched: {len(unmatched_canon)}")
    for n in unmatched_canon[:50]:
        print(f"     - {n}")
    if len(unmatched_canon) > 50:
        print(f"     … {len(unmatched_canon) - 50} more")

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_JSON.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(profiles, indent=2, ensure_ascii=False))
    os.replace(tmp, OUTPUT_JSON)
    print(f"\nWrote {OUTPUT_JSON}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
