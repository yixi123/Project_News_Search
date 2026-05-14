"""
GDELT 2.0 News Collector (Fast Edition)
=========================================
Optimized version with:
  - Concurrent downloads via ThreadPoolExecutor
  - Connection pooling via requests.Session
  - HEAD request pre-check to skip empty time slices
  - Same output format as collector.py (Title, Description, Date, Link)

Usage:
    python collector_fast.py --days 3
    python collector_fast.py --start 20250501 --end 20250507 --workers 8 --min-mentions 5
    python collector_fast.py --days 3 --domains reuters.com,bbc.com,apnews.com
    python collector_fast.py --start 20250501 --end 20250507 --output data/news.jsonl
"""

import argparse
import csv
import io
import json
import os
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from urllib.parse import urlparse

import requests

# ── Config ────────────────────────────────────────────────────────

BASE_URL = "http://data.gdeltproject.org/gdeltv2"
HEADERS = {"User-Agent": "GDELT-Collector/2.0 (research prototype)"}
CAMEO_CODE_URL = "https://www.gdeltproject.org/data/lookups/CAMEO.eventcodes.txt"

# Default concurrency — GDELT server tolerates up to ~10-16 well
DEFAULT_WORKERS = 8
# Delay between batches (seconds) to be polite
BATCH_DELAY = 0.5
# Files per batch
BATCH_SIZE = 16

EXPORT_COLUMNS = [
    "GlobalEventID", "Day", "MonthYear", "Year", "FractionDate",
    "Actor1Code", "Actor1Name", "Actor1CountryCode", "Actor1KnownGroupCode",
    "Actor1EthnicCode", "Actor1Religion1Code", "Actor1Religion2Code",
    "Actor1Type1Code", "Actor1Type2Code", "Actor1Type3Code",
    "Actor2Code", "Actor2Name", "Actor2CountryCode", "Actor2KnownGroupCode",
    "Actor2EthnicCode", "Actor2Religion1Code", "Actor2Religion2Code",
    "Actor2Type1Code", "Actor2Type2Code", "Actor2Type3Code",
    "IsRootEvent", "EventCode", "EventBaseCode", "EventRootCode",
    "QuadClass", "GoldsteinScale", "NumMentions", "NumSources",
    "NumArticles", "AvgTone",
    "Actor1Geo_Type", "Actor1Geo_Fullname", "Actor1Geo_CountryCode",
    "Actor1Geo_ADM1Code", "Actor1Geo_Lat", "Actor1Geo_Long",
    "Actor1Geo_FeatureID", "Actor1Geo_ADM2Code",
    "Actor2Geo_Type", "Actor2Geo_Fullname", "Actor2Geo_CountryCode",
    "Actor2Geo_ADM1Code", "Actor2Geo_Lat", "Actor2Geo_Long",
    "Actor2Geo_FeatureID", "Actor2Geo_ADM2Code",
    "ActionGeo_Type", "ActionGeo_Fullname", "ActionGeo_CountryCode",
    "ActionGeo_ADM1Code", "ActionGeo_Lat", "ActionGeo_Long",
    "ActionGeo_FeatureID", "ActionGeo_ADM2Code",
    "DATEADDED", "SOURCEURL",
]

# ── Verb Map (same as collector.py) ──────────────────────────────

VERB_MAP = {
    "010": "{A1} made a public statement about {A2}",
    "011": "{A1} declined to comment on {A2}",
    "012": "{A1} made a pessimistic comment about {A2}",
    "013": "{A1} expressed optimism regarding {A2}",
    "014": "{A1} considered policy options regarding {A2}",
    "015": "{A1} acknowledged or claimed responsibility related to {A2}",
    "016": "{A1} denied responsibility regarding {A2}",
    "017": "{A1} engaged in a symbolic act regarding {A2}",
    "018": "{A1} made an empathetic comment about {A2}",
    "019": "{A1} expressed agreement with {A2}",
    "020": "{A1} appealed to {A2}",
    "021": "{A1} appealed to {A2} for material cooperation",
    "022": "{A1} appealed to {A2} for diplomatic cooperation",
    "023": "{A1} appealed to {A2} for aid",
    "024": "{A1} appealed to {A2} for political reform",
    "025": "{A1} appealed to {A2} to yield",
    "026": "{A1} appealed to {A2} to meet or negotiate",
    "027": "{A1} appealed to {A2} to settle a dispute",
    "028": "{A1} appealed to {A2} to engage in mediation",
    "030": "{A1} expressed intent to cooperate with {A2}",
    "031": "{A1} expressed intent to cooperate materially with {A2}",
    "032": "{A1} expressed intent to cooperate diplomatically with {A2}",
    "033": "{A1} expressed intent to provide aid to {A2}",
    "034": "{A1} expressed intent for political reform regarding {A2}",
    "035": "{A1} expressed intent to yield to {A2}",
    "036": "{A1} expressed intent to meet or negotiate with {A2}",
    "037": "{A1} expressed intent to settle disputes with {A2}",
    "038": "{A1} expressed intent to accept mediation with {A2}",
    "040": "{A1} consulted with {A2}",
    "041": "{A1} met with {A2} for diplomatic consultation",
    "042": "{A1} proposed to {A2} to make a joint statement",
    "043": "{A1} proposed to {A2} to engage in a strategic partnership",
    "044": "{A1} discussed with {A2} a potential economic development",
    "045": "{A1} engaged with {A2} in a bilateral discussion",
    "046": "{A1} proposed a cultural or scientific exchange with {A2}",
    "047": "{A1} proposed to {A2} to establish a military alliance",
    "048": "{A1} proposed to {A2} to establish peacekeeping",
    "050": "{A1} engaged in diplomatic cooperation with {A2}",
    "051": "{A1} made a joint statement with {A2}",
    "052": "{A1} established a strategic partnership with {A2}",
    "053": "{A1} signed a bilateral agreement with {A2}",
    "054": "{A1} offered economic assistance to {A2}",
    "055": "{A1} offered a ceasefire to {A2}",
    "056": "{A1} engaged in peacekeeping with {A2}",
    "057": "{A1} engaged in mediation with {A2}",
    "060": "{A1} engaged in material cooperation with {A2}",
    "061": "{A1} provided economic aid to {A2}",
    "062": "{A1} provided military aid to {A2}",
    "063": "{A1} provided humanitarian aid to {A2}",
    "064": "{A1} provided military protection to {A2}",
    "065": "{A1} provided economic assistance to {A2}",
    "066": "{A1} engaged in joint military operations with {A2}",
    "067": "{A1} provided intelligence to {A2}",
    "070": "{A1} provided aid to {A2}",
    "071": "{A1} provided emergency relief to {A2}",
    "072": "{A1} provided medical aid to {A2}",
    "073": "{A1} provided food aid to {A2}",
    "074": "{A1} provided shelter to {A2}",
    "075": "{A1} provided financial assistance to {A2}",
    "080": "{A1} yielded to {A2}",
    "081": "{A1} relaxed sanctions against {A2}",
    "082": "{A1} eased a blockade against {A2}",
    "083": "{A1} released prisoners to {A2}",
    "084": "{A1} withdrew military forces from {A2}",
    "085": "{A1} de-escalated military engagement with {A2}",
    "086": "{A1} agreed to a ceasefire with {A2}",
    "090": "{A1} investigated {A2}",
    "091": "{A1} conducted a domestic investigation on {A2}",
    "092": "{A1} investigated {A2} through international channels",
    "093": "{A1} investigated {A2} for suspected violations",
    "094": "{A1} demanded an explanation from {A2}",
    "100": "{A1} made demands of {A2}",
    "101": "{A1} demanded a policy change from {A2}",
    "102": "{A1} demanded an apology from {A2}",
    "103": "{A1} demanded compensation from {A2}",
    "104": "{A1} demanded the release of persons from {A2}",
    "105": "{A1} demanded a ceasefire from {A2}",
    "110": "{A1} disapproved of {A2}",
    "111": "{A1} criticized {A2}",
    "112": "{A1} accused {A2}",
    "113": "{A1} lodged a formal complaint against {A2}",
    "114": "{A1} brought a case against {A2} in an international body",
    "115": "{A1} refused to comply with {A2}",
    "120": "{A1} rejected demands from {A2}",
    "121": "{A1} refused to yield to {A2}",
    "122": "{A1} rejected a ceasefire proposal from {A2}",
    "123": "{A1} refused to negotiate with {A2}",
    "124": "{A1} rejected a mediation proposal from {A2}",
    "130": "{A1} threatened {A2}",
    "131": "{A1} threatened {A2} with sanctions",
    "132": "{A1} threatened {A2} with military force",
    "133": "{A1} threatened {A2} with a trade embargo",
    "134": "{A1} issued an ultimatum to {A2}",
    "140": "{A1} protested against {A2}",
    "141": "{A1} demonstrated against {A2}",
    "142": "{A1} organized a hunger strike regarding {A2}",
    "143": "{A1} organized a boycott against {A2}",
    "144": "{A1} staged a strike regarding {A2}",
    "145": "{A1} engaged in violent protests against {A2}",
    "150": "{A1} reduced relations with {A2}",
    "151": "{A1} recalled its ambassador from {A2}",
    "152": "{A1} severed diplomatic relations with {A2}",
    "153": "{A1} imposed sanctions on {A2}",
    "154": "{A1} imposed a blockade against {A2}",
    "155": "{A1} expelled diplomats from {A2}",
    "156": "{A1} imposed a trade embargo on {A2}",
    "160": "{A1} used force against {A2}",
    "161": "{A1} used military force against {A2}",
    "162": "{A1} conducted an arrest or detention of {A2}",
    "163": "{A1} kidnapped or abducted individuals related to {A2}",
    "164": "{A1} tortured or mistreated individuals related to {A2}",
    "165": "{A1} used physical violence against {A2}",
    "166": "{A1} engaged in mass killings against {A2}",
    "167": "{A1} used forced disappearances against {A2}",
    "170": "{A1} engaged in unconventional mass violence against {A2}",
    "171": "{A1} engaged in mob violence against {A2}",
    "172": "{A1} used chemical or biological weapons against {A2}",
    "173": "{A1} used nuclear materials against {A2}",
    "174": "{A1} engaged in suicide bombing against {A2}",
    "175": "{A1} engaged in sabotage against {A2}",
    "180": "{A1} conducted an assassination against {A2}",
    "181": "{A1} conducted an execution against {A2}",
    "182": "{A1} targeted {A2} for assassination",
    "190": "{A1} used conventional military force against {A2}",
    "191": "{A1} engaged in artillery fire against {A2}",
    "192": "{A1} engaged in a military engagement with {A2}",
    "193": "{A1} conducted an airstrike against {A2}",
    "194": "{A1} conducted a naval engagement against {A2}",
    "195": "{A1} used special forces against {A2}",
    "200": "{A1} used unconventional force against {A2}",
    "201": "{A1} conducted a cyber attack against {A2}",
    "202": "{A1} used chemical weapons against {A2}",
    "203": "{A1} used biological weapons against {A2}",
}

ROOT_VERB_FALLBACK = {
    "01": "made a public statement about {A2}",
    "02": "appealed to {A2}",
    "03": "expressed intent to cooperate with {A2}",
    "04": "consulted with {A2}",
    "05": "engaged in diplomatic cooperation with {A2}",
    "06": "engaged in material cooperation with {A2}",
    "07": "provided aid to {A2}",
    "08": "yielded to {A2}",
    "09": "investigated {A2}",
    "10": "made demands of {A2}",
    "11": "disapproved of {A2}",
    "12": "rejected demands from {A2}",
    "13": "threatened {A2}",
    "14": "protested against {A2}",
    "15": "reduced relations with {A2}",
    "16": "used force against {A2}",
    "17": "engaged in mass violence against {A2}",
    "18": "conducted an assassination against {A2}",
    "19": "used military force against {A2}",
    "20": "used unconventional force against {A2}",
}

# ── CAMEO Code Table ──────────────────────────────────────────────

_cameo_cache = {}


def load_cameo_codes(cache_path=None):
    global _cameo_cache
    if _cameo_cache:
        return _cameo_cache

    local_paths = []
    if cache_path:
        local_paths.append(cache_path)
    if __file__:
        local_paths.append(os.path.join(os.path.dirname(__file__), "cameo_eventcodes.txt"))
    local_paths.append("cameo_eventcodes.txt")

    for lp in local_paths:
        if os.path.exists(lp):
            with open(lp, "r", encoding="utf-8") as f:
                _cameo_cache = _parse_cameo(f.read())
            return _cameo_cache

    try:
        r = requests.get(CAMEO_CODE_URL, headers=HEADERS, timeout=15)
        content = r.text
        _cameo_cache = _parse_cameo(content)
        save_path = os.path.join(os.path.dirname(__file__) if __file__ else ".", "cameo_eventcodes.txt")
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(content)
        return _cameo_cache
    except Exception as e:
        print(f"[WARNING] Failed to load CAMEO codes: {e}", file=sys.stderr)
        return {}


def _parse_cameo(content):
    codes = {}
    for line in content.strip().split("\n")[1:]:
        parts = line.split("\t")
        if len(parts) >= 2:
            codes[parts[0].strip()] = parts[1].strip()
    return codes


# ── Title / Description Generation ────────────────────────────────

def _get_verb_template(event_code, cameo_codes):
    if not event_code:
        return "{A1} was involved in an event with {A2}"
    base = event_code[:3] if len(event_code) >= 3 else ""
    if base in VERB_MAP:
        return VERB_MAP[base]
    root = event_code[:2] if len(event_code) >= 2 else ""
    if root in ROOT_VERB_FALLBACK:
        return ROOT_VERB_FALLBACK[root]
    return "{A1} was involved in an event with {A2}"


def _fill_actor(name, country_code):
    n = (name or "").strip()
    c = (country_code or "").strip()
    if n and c and c not in n.upper():
        return f"{n} ({c})"
    if n:
        return n
    if c:
        return c
    return "Unknown"


def _is_uuid_or_id(seg):
    """Check if segment is a UUID, article ID, or similar non-slug identifier."""
    # Remove extension if present
    clean_seg = seg.rsplit('.', 1)[0] if '.' in seg else seg
    
    # Skip if it's purely numeric (date segments like "2017", "01", etc)
    if clean_seg.isdigit():
        return True
    
    # UUID patterns: 8-4-4-4-12 hex format (with or without dashes/spaces)
    # e.g., "70c25956-d12c-11e6-945a-76f69a399dd5" or "70c25956 d12c 11e6 945a 76f69a399dd5"
    hex_chars = set('0123456789abcdefABCDEF-. ')
    if all(c in hex_chars for c in clean_seg):
        # Must be mostly hex digits (after removing separators)
        hex_only = clean_seg.replace('-', '').replace(' ', '').replace('.', '')
        if len(hex_only) >= 20 and hex_only.isalnum():
            return True
    
    # Article ID patterns: "idUSL4N1ET0EB", "idINKBN14N055", etc
    if clean_seg.startswith(('id', 'a-', 'story-')) and not ' ' in seg:
        return True
    
    # Segments that are mostly numbers with maybe one letter: "38490343", "38490593"
    if len(clean_seg) > 6 and clean_seg.replace(' ', '').isdigit():
        return True
    
    return False


def generate_title(event, cameo_codes):
    """Extract title from URL path slug instead of generating from CAMEO templates."""
    source_url = (event.get("SOURCEURL") or "").strip()
    if source_url:
        try:
            path = urlparse(source_url).path
            # Remove file extension from the last segment
            if path.endswith(('.html', '.htm', '.php', '.aspx')):
                path = path.rsplit('.', 1)[0]
            
            # Split by '/' and filter out empty segments
            segments = [s for s in path.split('/') if s]
            
            if segments:
                # Filter out non-slug segments: UUIDs, IDs, dates, common dirs
                slugs = []
                for seg in segments:
                    # Skip if it's a UUID, ID, or similar pattern
                    if _is_uuid_or_id(seg):
                        continue
                    # Skip common directory names
                    if seg in ('www', 'index', 'article', 'story', 'news', 'opinion', 'opinions'):
                        continue
                    # Keep segments that contain letters (likely slugs or meaningful text)
                    if any(c.isalpha() for c in seg):
                        slugs.append(seg)
                
                # If we found slugs, join them and format as title
                if slugs:
                    title = ' '.join(slugs).replace('-', ' ').strip()
                    # Clean up extra spaces
                    title = ' '.join(title.split())
                    if title and len(title) > 3:  # Require minimum length
                        return title
        except Exception:
            pass
    
    # Fallback: generate from CAMEO if URL extraction fails
    a1 = _fill_actor(event.get("Actor1Name"), event.get("Actor1CountryCode"))
    a2 = _fill_actor(event.get("Actor2Name"), event.get("Actor2CountryCode"))
    template = _get_verb_template(event.get("EventCode", ""), cameo_codes)
    return template.replace("{A1}", a1).replace("{A2}", a2)


def generate_description(event, cameo_codes):
    a1 = _fill_actor(event.get("Actor1Name"), event.get("Actor1CountryCode"))
    a2 = _fill_actor(event.get("Actor2Name"), event.get("Actor2CountryCode"))
    geo = (event.get("ActionGeo_Fullname") or "").strip()
    event_code = event.get("EventCode", "")
    num_articles = _safe_int(event.get("NumArticles"), 0)
    avg_tone = _safe_float(event.get("AvgTone"), 0.0)

    template = _get_verb_template(event_code, cameo_codes)
    sentence = template.replace("{A1}", a1).replace("{A2}", a2)

    if geo:
        sentence = f"{sentence} in {geo}."

    base = event_code[:3] if len(event_code) >= 3 else ""
    if base and base in cameo_codes:
        detail = cameo_codes[base].lower()
        if detail not in sentence.lower():
            sentence = f"{sentence} (Category: {cameo_codes[base]})."
    else:
        sentence = f"{sentence}."

    parts = [sentence]

    if avg_tone < -8:
        parts.append("Media coverage of this event was overwhelmingly negative.")
    elif avg_tone < -4:
        parts.append("Media coverage was largely negative.")
    elif avg_tone > 8:
        parts.append("Media coverage was overwhelmingly positive.")
    elif avg_tone > 4:
        parts.append("Media coverage was largely positive.")

    if num_articles >= 50:
        parts.append(f"This event received extensive coverage with over {num_articles} articles.")
    elif num_articles >= 10:
        parts.append(f"This event was covered by {num_articles} articles.")

    return " ".join(parts)


# ── Utilities ─────────────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _safe_int(val, default=0):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _safe_float(val, default=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _day_start(dt):
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _day_end(dt):
    return dt.replace(hour=23, minute=59, second=59, microsecond=999999)


def generate_time_slices(start_date, end_date):
    """Generate 15-minute time slice filenames for the date range."""
    slices = []
    current = _day_start(start_date)
    last_day = _day_start(end_date)
    while current <= last_day:
        for hour in range(24):
            for minute in (0, 15, 30, 45):
                ts = current.replace(hour=hour, minute=minute)
                slices.append(ts.strftime("%Y%m%d%H%M%S"))
        current += timedelta(days=1)
    return slices


def parse_tsv_from_bytes(zip_bytes):
    """Parse a GDELT export CSV zip file from raw bytes."""
    records = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        csv_name = zf.namelist()[0]
        with zf.open(csv_name) as f:
            text = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
            reader = csv.reader(text, delimiter="\t")
            for row in reader:
                if len(row) < 10:
                    continue
                record = {}
                for i, col in enumerate(EXPORT_COLUMNS):
                    record[col] = row[i] if i < len(row) else ""
                records.append(record)
    return records


def _normalize_hostname(url):
    """Return a normalized hostname for URL matching."""
    try:
        hostname = urlparse(url).hostname or ""
        return hostname.lower().removeprefix("www.")
    except Exception:
        return ""


def _matches_domain_filter(source_url, allowed_domains):
    """Match a source URL against exact trusted domains and their subdomains."""
    if not allowed_domains:
        return True

    host = _normalize_hostname(source_url)
    if not host:
        return False

    for domain in allowed_domains:
        trusted = (domain or "").lower().strip().removeprefix("www.")
        if not trusted:
            continue
        if host == trusted or host.endswith("." + trusted):
            return True
    return False


# ── Concurrent Downloader ────────────────────────────────────────

def download_batch(session, urls, workers=BATCH_SIZE):
    """Download a batch of URLs concurrently. Returns list of (url, records_or_None)."""
    results = []

    def fetch(url):
        try:
            r = session.get(url, timeout=120)
            if r.status_code == 404:
                return url, None
            r.raise_for_status()
            records = parse_tsv_from_bytes(r.content)
            return url, records
        except Exception:
            return url, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, url): url for url in urls}
        for future in as_completed(futures, timeout=300):
            results.append(future.result())

    return results


# ── Core Collection ───────────────────────────────────────────────

def collect_news(start_date, end_date, keywords=None, min_mentions=1, domains=None,
                 workers=DEFAULT_WORKERS, batch_size=BATCH_SIZE, head_check=True, batch_delay=BATCH_DELAY):
    """
    Collect GDELT 2.0 events with concurrent downloads.
    Returns: [{"Title": ..., "Description": ..., "Date": ..., "Link": ...}, ...]
    """
    cameo_codes = load_cameo_codes()
    if not cameo_codes:
        log("WARNING: CAMEO codes not loaded")

    time_slices = generate_time_slices(start_date, end_date)
    total_slices = len(time_slices)
    log(f"Time slices: {total_slices} ({start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')})")
    log(f"Workers: {workers}, Batch size: {batch_size}")

    # Optional: HEAD pre-check to skip non-existent slices
    # GDELT 2.0 is ~continuous since 2015-02-20, so skip for recent dates
    # but enable for older dates where gaps may exist
    if head_check:
        log("HEAD pre-checking time slices...")
        session_check = requests.Session()
        session_check.headers.update(HEADERS)
        valid_slices = []
        batch_urls = []
        batch_ts = []
        for ts in time_slices:
            url = f"{BASE_URL}/{ts}.export.CSV.zip"
            batch_urls.append(url)
            batch_ts.append(ts)
            if len(batch_urls) >= workers * 4:
                valid_batch = _head_check_batch(session_check, batch_urls, batch_ts, workers)
                valid_slices.extend(valid_batch)
                batch_urls = []
                batch_ts = []
        if batch_urls:
            valid_batch = _head_check_batch(session_check, batch_urls, batch_ts, workers)
            valid_slices.extend(valid_batch)
        time_slices = valid_slices
        log(f"Valid slices after HEAD check: {len(time_slices)}/{total_slices}")
    else:
        log("Skipping HEAD check (assuming all slices exist)")

    # Download in batches
    session = requests.Session()
    session.headers.update(HEADERS)

    # Mount adapter with connection pooling
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=workers,
        pool_maxsize=workers,
        max_retries=2,
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    seen_ids = set()
    results = []
    downloaded = 0
    skipped = 0
    total_slices = len(time_slices)
    t_start = time.time()

    for batch_start in range(0, total_slices, batch_size):
        batch = time_slices[batch_start:batch_start + batch_size]
        urls = [f"{BASE_URL}/{ts}.export.CSV.zip" for ts in batch]

        batch_results = download_batch(session, urls, workers=batch_size)

        for url, records in batch_results:
            if records is None:
                skipped += 1
                continue
            downloaded += 1

            for event in records:
                eid = event.get("GlobalEventID", "")
                if eid in seen_ids:
                    continue

                num_mentions = _safe_int(event.get("NumMentions"), 0)
                if num_mentions < min_mentions:
                    continue

                actor1 = (event.get("Actor1Name") or "").strip()
                actor2 = (event.get("Actor2Name") or "").strip()
                if not actor1 and not actor2:
                    continue

                if keywords:
                    text = f"{actor1} {actor2} {event.get('SOURCEURL', '')} {event.get('ActionGeo_Fullname', '')}"
                    if not any(kw.lower() in text.lower() for kw in keywords):
                        continue

                if not _matches_domain_filter(event.get("SOURCEURL") or "", domains):
                    continue

                seen_ids.add(eid)

                # Ensure event Day falls within requested start/end dates
                day_str = event.get("Day", "")
                event_date = None
                if isinstance(day_str, str) and len(day_str) == 8 and day_str.isdigit():
                    try:
                        event_date = datetime.strptime(day_str, "%Y%m%d").date()
                    except Exception:
                        event_date = None

                # Normalize incoming start/end to dates for comparison
                req_start = start_date.date() if isinstance(start_date, datetime) else start_date
                req_end = end_date.date() if isinstance(end_date, datetime) else end_date

                if event_date is None:
                    continue
                if event_date < req_start or event_date > req_end:
                    continue

                date = event_date.isoformat()

                results.append({
                    "Title": generate_title(event, cameo_codes),
                    "Description": generate_description(event, cameo_codes),
                    "Date": date,
                    "Link": (event.get("SOURCEURL") or "").strip(),
                })

        # Progress
        done = min(batch_start + batch_size, total_slices)
        elapsed = time.time() - t_start
        rate = done / max(elapsed, 1)
        eta = (total_slices - done) / max(rate, 0.01)
        log(f"  Progress: {done}/{total_slices} | "
            f"dl: {downloaded} | skip: {skipped} | news: {len(results)} | "
            f"{rate:.1f} slices/s | ETA: {eta:.0f}s")

        # Be polite — small delay between batches
        if batch_start + batch_size < total_slices:
            time.sleep(batch_delay)

    # Merge articles with same link on same day
    merged = {}
    for item in results:
        key = (item["Link"], item["Date"])
        if key in merged:
            # Concatenate descriptions
            merged[key]["Description"] += " | " + item["Description"]
        else:
            merged[key] = item

    results = list(merged.values())
    results.sort(key=lambda x: x["Date"], reverse=True)
    elapsed = time.time() - t_start
    log(f"Done in {elapsed:.0f}s. {len(results)} news articles collected (after merging duplicates).")
    return results


def _head_check_batch(session, urls, timestamps, workers):
    """Quickly check which URLs return 200 via HEAD requests."""
    def check(pair):
        url, ts = pair
        try:
            r = session.head(url, timeout=15, allow_redirects=True)
            return (ts, r.status_code == 200)
        except Exception:
            return (ts, False)

    valid = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(check, (u, t)) for u, t in zip(urls, timestamps)]
        for f in as_completed(futures, timeout=120):
            ts, exists = f.result()
            if exists:
                valid.append(ts)
    return valid


# ── Output ────────────────────────────────────────────────────────

def save_jsonl(news_list, output_path):
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for item in news_list:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    log(f"Saved {len(news_list)} items to {output_path}")


def save_json(news_list, output_path):
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(news_list, f, ensure_ascii=False, indent=2)
    log(f"Saved {len(news_list)} items to {output_path}")


def save_csv(news_list, output_path):
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Title", "Description", "Date", "Link"])
        writer.writeheader()
        writer.writerows(news_list)
    log(f"Saved {len(news_list)} items to {output_path}")


# ── CLI ───────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="GDELT 2.0 News Collector (Fast Edition)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Collect last 3 days with 8 workers (default)
  python collector_fast.py --days 3

  # Aggressive: 16 workers, no HEAD check (fastest for recent dates)
  python collector_fast.py --days 7 --workers 16 --no-head-check

  # Filter by domain and keywords
  python collector_fast.py --days 3 --domains reuters.com,bbc.com,apnews.com --keywords China,trade

  # Specific date range
  python collector_fast.py --start 20250501 --end 20250507 --output data/news.jsonl

  # Conservative: be nice to GDELT server
  python collector_fast.py --days 30 --workers 4 --batch-delay 1.0
        """
    )
    p.add_argument("--start", type=str, help="Start date YYYYMMDD")
    p.add_argument("--end", type=str, help="End date YYYYMMDD")
    p.add_argument("--days", type=int, default=3, help="Recent N days (default: 3)")
    p.add_argument("--output", type=str, default="data/news.jsonl")
    p.add_argument("--format", type=str, default="jsonl", choices=["jsonl", "json", "csv"])
    p.add_argument("--keywords", type=str, default=None, help="Comma-separated keywords")
    p.add_argument("--domains", type=str, default=None,
                   help="Comma-separated domains (e.g. reuters.com,bbc.com,nytimes.com)")
    p.add_argument("--min-mentions", type=int, default=1)
    p.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                   help=f"Concurrent download threads (default: {DEFAULT_WORKERS})")
    p.add_argument("--batch-size", type=int, default=BATCH_SIZE,
                   help=f"URLs per download batch (default: {BATCH_SIZE})")
    p.add_argument("--batch-delay", type=float, default=BATCH_DELAY,
                   help="Delay between batches in seconds (default: 0.5)")
    p.add_argument("--no-head-check", action="store_true",
                   help="Skip HEAD pre-check (faster for recent dates, wastes time for old dates with gaps)")
    return p.parse_args()


def main():
    args = parse_args()

    # Override global batch settings
    global BATCH_SIZE, BATCH_DELAY
    BATCH_SIZE = args.batch_size
    BATCH_DELAY = args.batch_delay

    if args.start and args.end:
        start_date = datetime.strptime(args.start, "%Y%m%d")
        end_date = datetime.strptime(args.end, "%Y%m%d")
    else:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=args.days - 1)

    earliest = datetime(2015, 2, 20)
    if start_date < earliest:
        log("WARNING: GDELT 2.0 starts from 2015-02-20")
        start_date = earliest
    if end_date > datetime.now():
        end_date = datetime.now()

    start_date = _day_start(start_date)
    end_date = _day_end(end_date)

    keywords = args.keywords.split(",") if args.keywords else None
    domains = args.domains.split(",") if args.domains else None

    log("=== GDELT 2.0 News Collector (Fast) ===")
    log(f"  Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    log(f"  Keywords: {keywords or 'All'}")
    log(f"  Domains: {domains or 'All'}")
    log(f"  Min mentions: {args.min_mentions}")
    log(f"  Workers: {args.workers}")
    log(f"  HEAD check: {'off' if args.no_head_check else 'on'}")
    log(f"  Output: {args.output}")

    news_list = collect_news(
        start_date=start_date,
        end_date=end_date,
        keywords=keywords,
        min_mentions=args.min_mentions,
        domains=domains,
        workers=args.workers,
        head_check=not args.no_head_check,
    )

    if args.format == "jsonl":
        save_jsonl(news_list, args.output)
    elif args.format == "json":
        save_json(news_list, args.output)
    elif args.format == "csv":
        save_csv(news_list, args.output)

    log(f"\n=== Sample ({len(news_list)} total) ===")
    for item in news_list[:5]:
        print(json.dumps(item, ensure_ascii=False, indent=2))
        print()


if __name__ == "__main__":
    main()
