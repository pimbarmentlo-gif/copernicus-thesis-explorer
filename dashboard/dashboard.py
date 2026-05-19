# the try/except blocks below guard against missing dependencies during execution.
# we also add type-ignore comments so linters like Pylance stop complaining.
try:
    import streamlit as st  # type: ignore[import]
except ImportError as e:
    raise ImportError("streamlit is required to run this dashboard. install with `pip install streamlit`") from e

try:
    from streamlit_pdf_viewer import pdf_viewer as _pdf_viewer_fn  # type: ignore[import]
    _PDF_VIEWER_AVAILABLE = True
except ImportError:
    _pdf_viewer_fn = None  # type: ignore[assignment]
    _PDF_VIEWER_AVAILABLE = False

try:
    import pandas as pd  # type: ignore[import]
except ImportError as e:
    raise ImportError("pandas is required; install via `pip install pandas`") from e

try:
    import plotly.express as px  # type: ignore[import]
except ImportError as e:
    raise ImportError("plotly is required; install via `pip install plotly`") from e

import os
import base64
import json
import urllib.parse
import threading as _threading
import socketserver as _socketserver
import http.server as _http_server
from pathlib import Path



def _render_html_iframe(html_body: str, *, height: int | str = "content") -> None:
    """Render custom HTML inline via st.components.v1.html."""
    iframe_height = 1 if isinstance(height, int) and height <= 0 else height
    st.components.v1.html(html_body, height=iframe_height, scrolling=False)

# ----- cached data-loading helpers -----------------------------------------
# These functions are decorated with @st.cache_data so that expensive I/O and
# data processing only runs once per unique set of arguments per session.
# Streamlit automatically invalidates the cache when the function arguments
# change (e.g. a different programme directory is requested).

@st.cache_data(show_spinner=False)
def _load_thesis_data(program_dir: str, program: str, mtime: float = 0) -> tuple:
    """Load, validate and clean the thesis metadata CSV for a programme directory.

    Returns (dataframe, error_message).  On success error_message is ''.
    All post-load transforms (fillna, Year normalisation, Featured flag) are
    applied inside this function so they are also covered by the cache.
    """
    import zipfile as _zf

    _featured_sbi = {
        "nijssen_2023.pdf",
        "peters_2025.pdf",
        "colom_2023.pdf",
        "harms_2025.pdf",
        "hu_2025.pdf",
        "klink_2025.pdf",
        "pelgrim_2024.pdf",
        "schutter_2025.pdf",
        "soltys_2023.pdf",
    }
    # Featured theses for Sustainable Development — matched by Thesis_PDF filename.
    # Koster, Mayer, Harvey, Kálmán, Oelschläger not yet in metadata; will activate once rows are added.
    _featured_sd = {
        # 2025
        "aupoix_2025.pdf",          # Séréna Aupoix
        # 2024
        "koster_2024.pdf",          # Fardau Koster (not yet in metadata)
        "mayer_2024.pdf",           # Severin Mayer (not yet in metadata)
        # 2023
        "ambraziejus_2025.pdf",     # Lukas Ambraziejus
        "breedveld_2023.pdf",       # Nina Breedveld
        "harvey_2023.pdf",          # Blake Harvey (not yet in metadata)
        "kalman_2024.pdf",          # Greta Kálmán (not yet in metadata)
        "prawiromaruto_2024.pdf",   # Michele Joie Prawiromaruto
        "popkema_2024.pdf",         # Karst Popkema
        # 2022
        "grunwald_2023.pdf",        # Lotte Grünwald
        "jans_2023.pdf",            # Sem Jans
        "jaspers_2023.pdf",         # Anouk Jaspers
        "latour_2023.pdf",          # Moritz Latour
        "oelschlager_2022.pdf",     # Lucia Oelschläger (not yet in metadata)
        "sijbers_2023.pdf",         # Marije Sijbers
        # 2021
        "visweswaran_2021.pdf",     # Anushri Narayan Visweswaran
    }
    # Featured theses for Innovation Sciences — matched by Thesis_PDF filename (same as SBI).
    # Bentum, Craen, Tim Dekker, Janssen not yet in metadata; will activate once rows are added.
    _featured_is = {
        "schuitemaker_2025.pdf",   # Nena Schuitemaker
        "conijn_2025.pdf",         # Maike Conijn
        "trooijen_2025.pdf",       # Steven van Trooijen
        "jongh_2025.pdf",          # Luc (Lodewijk) de Jongh
        "khachatryan_2025.pdf",    # Lilya Khachatryan
        "raedts_2025.pdf",         # Cas Raedts
        "bentum_2025.pdf",         # Caspar van Bentum (not yet in metadata)
        "craen_2025.pdf",          # Teun de Craen (not yet in metadata)
        "dekker_2025.pdf",         # Tim Dekker (not yet in metadata)
        "janssen_2025.pdf",        # Bart Janssen (not yet in metadata)
    }

    metadata_path = os.path.join(program_dir, "thesis_metadata_matched.csv")

    if not os.path.exists(metadata_path):
        return pd.DataFrame(), (
            f"Metadata file not found: {metadata_path}. Run prepare_thesis_files.py first."
        )

    try:
        if _zf.is_zipfile(metadata_path):
            return pd.DataFrame(), (
                "The metadata file appears to be a compressed archive rather than a CSV. "
                "Please replace it with a valid thesis_metadata file (or .csv)."
            )
    except Exception:
        pass  # is_zipfile can raise on some edge-case files; fall through to read attempt

    df = pd.DataFrame()
    last_error = None
    loaded = False
    try:
        for encoding in ("utf-8-sig", "latin1"):
            for sep in (",", ";"):
                try:
                    candidate_df = pd.read_csv(metadata_path, sep=sep, encoding=encoding)
                    if len(candidate_df.columns) == 1 and ";" in str(candidate_df.columns[0]) and sep == ",":
                        continue
                    df = candidate_df
                    loaded = True
                    break
                except Exception as e:
                    last_error = e
            if loaded:
                break
    except Exception as exc:
        return pd.DataFrame(), f"Error reading metadata: {exc}"

    if not loaded:
        return pd.DataFrame(), f"Could not read metadata file: {last_error}"

    # Post-load transforms -------------------------------------------------------
    # Exclude unresolved records from all dashboard views.
    if "Match_Status" in df.columns:
        df = df[~df["Match_Status"].astype(str).str.strip().str.lower().eq("not found")].copy()

    df = df.fillna("n/a")

    # Normalize year values (remove trailing .0 from float conversions).
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce").astype("Int64").astype(str).replace("<NA>", "n/a")

    # Featured flag — programme-specific curated selection.
    if program == "sbi":
        df["Featured"] = df["Thesis_PDF"].astype(str).str.strip().isin(_featured_sbi)
    elif program == "innovation_sciences":
        df["Featured"] = df["Thesis_PDF"].astype(str).str.strip().isin(_featured_is)
    elif program == "sustainable_development":
        df["Featured"] = df["Thesis_PDF"].astype(str).str.strip().isin(_featured_sd)
    else:
        df["Featured"] = False

    return df, ""


@st.cache_data(show_spinner=False)
def _load_image_b64(path: str) -> str:
    """Return a base64-encoded string for a binary file, or '' if the file does not exist."""
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


@st.cache_data(show_spinner=False)
def _load_sup_profiles_global() -> dict:
    """Load supervisor_profiles.json and embed photo b64 into each entry. Cached for lifetime."""
    _p = Path(__file__).parent / "supervisor_profiles.json"
    if not _p.exists():
        return {}
    try:
        data = json.loads(_p.read_text(encoding="utf-8"))
        _base = os.path.dirname(__file__)
        for entry in data.values():
            _pp = entry.get("photo_path")
            if _pp:
                entry["_photo_b64"] = _load_image_b64(os.path.join(_base, _pp))
        return data
    except Exception:
        return {}


_SUP_PROFILES = _load_sup_profiles_global()


def _sup_photo_b64(name: str) -> str:
    """Return cached base64 photo for a canonical supervisor name, or ''."""
    return _SUP_PROFILES.get(name, {}).get("_photo_b64", "") or ""


@st.cache_data(show_spinner=False)
def _load_html_file(path: str) -> str:
    """Return the text content of a file, or '' if it does not exist."""
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


@st.cache_data(show_spinner=False)
def _build_logo_index(logos_dir: str) -> list:
    """Scan logos_dir and return list of (token_set, joined_slug, filepath) tuples."""
    import re as _rl
    _NOISE = {
        "logo","favicon","brand","svg","png","jpg","jpeg","webp","avif","rgb","seeklogo",
        "wine","pos","bg","voorkant","corelogo","colour","teal","claim","rz",
        "smarter","last","mile","logistics","horizontaal","worldwide","north",
        "bv","nv","ltd","inc","llc","gmbh","ag","plc","sa","the","de","van",
        "het","en","of","for","and","an","in",
    }
    result = []
    if not os.path.exists(logos_dir):
        return result
    for fname in os.listdir(logos_dir):
        if not os.path.isfile(os.path.join(logos_dir, fname)):
            continue
        stem = fname
        # strip all extensions including double ones like .svg.png
        for _ in range(4):
            base, ext = os.path.splitext(stem)
            if not ext:
                break
            stem = base
        joined = _rl.sub(r'[^a-z0-9]', '', stem.lower())
        tokens = frozenset(
            t for t in _rl.sub(r'[^a-z0-9]', ' ', stem.lower()).split()
            if t not in _NOISE and len(t) > 1
        )
        if tokens or joined:
            result.append((tokens, joined, os.path.join(logos_dir, fname)))
    return result


@st.cache_data(show_spinner=False)
def _load_org_logo_b64(logos_dir: str, org_name: str) -> str:
    """Fuzzy-match org_name against messy logo filenames using multi-phase scoring."""
    import re as _rl
    from difflib import SequenceMatcher as _SM
    index = _build_logo_index(logos_dir)
    if not index:
        return ''
    _LEGAL = r'\b(b\.?v\.?|n\.?v\.?|ltd\.?|inc\.?|llc|gmbh|ag|plc|s\.a\.?|rcv|co|kg)\b'
    # Pre-process: collapse dotted acronyms like D.O.R.C. → DORC so token splitting works
    org_name_proc = _rl.sub(r'\b([A-Za-z]\.){2,}', lambda m: m.group(0).replace('.', ''), org_name)
    # Extract parenthesised acronym e.g. "(RVO)", "(MCC)", "(DORC)"
    _acr_m = _rl.search(r'\(([A-Z]{2,8})\)', org_name_proc)
    _acronym = _acr_m.group(1).lower() if _acr_m else ''
    # Remove parenthesised parts before further cleaning
    cleaned = _rl.sub(r'\([^)]*\)', '', org_name_proc.lower())
    cleaned = _rl.sub(_LEGAL, '', cleaned)
    org_tokens = set(
        t for t in _rl.sub(r'[^a-z0-9]', ' ', cleaned).split()
        if len(t) > 1
    )
    org_tokens -= {'the', 'de', 'van', 'het', 'and', 'of', 'for', 'en', 'an', 'on', 'in'}
    org_joined = _rl.sub(r'[^a-z0-9]', '', cleaned)
    # Build initials acronym variants for different filtering levels
    _raw_words = _rl.sub(r'[^a-z0-9\s]', '', org_name_proc.lower()).split()
    _acr_stop = {'the', 'van', 'het', 'and', 'of', 'for', 'an', 'on', 'in',
                 'bv', 'nv', 'ltd', 'inc', 'llc', 'gmbh', 'ag', 'plc', 'sa', 'rcv', 'co', 'kg'}
    _acr_words = [w for w in _raw_words if w and w not in _acr_stop]
    _initials_acr = ''.join(w[0] for w in _acr_words) if len(_acr_words) >= 2 else ''
    # Full initials keeping all words (e.g. HDSR = Hoogheemraadschap De Stichtse Rijnlanden)
    _initials_full = ''.join(w[0] for w in _raw_words if w) if len(_raw_words) >= 2 else ''
    if not org_tokens and not _acronym:
        return ''
    best_path, best_score = '', 0.0
    for file_tokens, file_joined, path in index:
        score = 0.0
        # Phase 1: Jaccard token overlap (union denominator prevents generic tokens from scoring 1.0)
        if file_tokens and org_tokens:
            overlap = len(org_tokens & file_tokens)
            if overlap:
                score = max(score, overlap / len(org_tokens | file_tokens))
        # Phase 2a: org tokens as substrings of file_joined (compound filenames)
        # Require token len >= 4 to avoid 3-letter org acronyms (e.g. "dwa") matching
        # as accidental substrings of unrelated filenames (e.g. "worldwaternet")
        if file_joined and org_tokens:
            sub_hits = sum(1 for t in org_tokens if len(t) >= 4 and t in file_joined)
            if sub_hits:
                score = max(score, sub_hits / max(1, len(org_tokens)) * 0.75)
        # Phase 2b: file_joined as substring of org_joined (acronym files: "dorc", "mcc", "cfp")
        if file_joined and org_joined and len(file_joined) >= 3:
            if file_joined in org_joined:
                coverage = len(file_joined) / max(1, len(org_joined))
                score = max(score, 0.50 + coverage * 0.40)
        # Phase 3: org_joined as substring of file_joined
        if file_joined and org_joined and len(org_joined) > 3:
            if org_joined in file_joined:
                score = max(score, 0.85)
        # Phase 4a: parenthesised acronym match
        if _acronym and file_joined:
            if file_joined == _acronym or _acronym in file_joined:
                score = max(score, 0.82)
        # Phase 4b: initials acronym match (stop-words excluded)
        if _initials_acr and len(_initials_acr) >= 3 and file_joined:
            if file_joined == _initials_acr or _initials_acr in file_joined:
                score = max(score, 0.76)
        # Phase 4c: full initials including stop words like 'de' (Dutch acronyms: HDSR, BVOR)
        if _initials_full and len(_initials_full) >= 3 and _initials_full != _initials_acr and file_joined:
            if file_joined == _initials_full or _initials_full in file_joined:
                score = max(score, 0.74)
        # Phase 5: difflib fuzzy match on slugs (catches typos like greylable → graylabel)
        if file_joined and org_joined and len(file_joined) >= 4 and len(org_joined) >= 4:
            ratio = _SM(None, file_joined, org_joined).ratio()
            if ratio >= 0.75:
                score = max(score, ratio * 0.85)
        if score > best_score:
            best_score, best_path = score, path
    if best_score >= 0.42:
        ext = os.path.splitext(best_path)[1].lower()
        # SVG: pass through as-is (already small text)
        if ext == '.svg':
            b64 = _load_image_b64(best_path)
            return f"data:image/svg+xml;base64,{b64}" if b64 else ''
        # Raster images: resize to 64×64 thumbnail so base64 stays tiny
        try:
            from PIL import Image as _PILImage
            import io as _io
            with _PILImage.open(best_path) as _img:
                # Always go via RGBA so palette-mode images ('P') with a
                # transparent index are handled correctly — skipping RGBA
                # causes the transparent pixels to map to whatever colour
                # sits at the transparent palette slot (often green/black).
                _img = _img.convert('RGBA')
                # Composite on white so transparent areas render cleanly
                # (galaxy nodes with logos already have a white circle fill).
                _white = _PILImage.new('RGBA', _img.size, (255, 255, 255, 255))
                _white.paste(_img, mask=_img.split()[3])
                _img = _white.convert('RGB')
                _img.thumbnail((64, 64), _PILImage.LANCZOS)
                _buf = _io.BytesIO()
                # Always save as PNG — avoids RGBA→JPEG failures and keeps quality
                _img.save(_buf, format='PNG', optimize=True)
                import base64 as _b64
                b64 = _b64.b64encode(_buf.getvalue()).decode()
            return f"data:image/png;base64,{b64}"
        except Exception:
            # Fallback: load raw (may be large but better than nothing)
            b64 = _load_image_b64(best_path)
            if not b64:
                return ''
            mime = {'.webp': 'image/webp', '.avif': 'image/avif',
                    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                    '.png': 'image/png'}.get(ext, 'image/*')
            return f"data:{mime};base64,{b64}"
    return ''


# ensure file paths work regardless of current working directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
PROGRAM = "sbi"

# ── Local PDF file server ──────────────────────────────────────────────────
# Streamlit 1.28+ resolves symlinks in its static-file handler and blocks
# any path that escapes dashboard/static/.  The static/pdfs/* subdirs are
# symlinks into programs/*/pdfs/ so they get a 400.  We side-step this by
# running a tiny CORS-enabled HTTP server in a background thread that serves
# straight from the project root — no symlink involved.
class _PDFHandler(_http_server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=_PROJECT_ROOT, **kwargs)
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()
    def log_message(self, *args):
        pass  # silence access log

@st.cache_resource(show_spinner=False)
def _start_pdf_server() -> int:
    """Start a one-off CORS-enabled HTTP server for serving PDFs.
    Wrapped in cache_resource so it runs exactly once per process lifetime,
    preventing port exhaustion from multiple script reruns."""
    try:
        srv = _socketserver.TCPServer(("127.0.0.1", 0), _PDFHandler)
        _threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv.server_address[1]  # OS-assigned port
    except OSError:
        return 0

_PDF_SERVER_PORT: int = _start_pdf_server()

# Map programme keys (used in URLs/session state) to actual folder names on disk.
_PROGRAMME_FOLDER_MAP = {
    "sbi": "sbi",
    "energy_science": "energy_science",
    "sustainable_development": "sustainable_development",
    "innovation_sciences": "innovation_sciences",
    "water_management": "water_management",
}

# Special meta-programme: aggregates all programmes' theses into one Explorer
# view. Supervisors / Insights stay scoped to a single programme.
_ALL_PROGRAM_KEY = "all"

PROGRAM_DIR = os.path.abspath(
    os.path.join(BASE_DIR, "..", "programs", _PROGRAMME_FOLDER_MAP.get(PROGRAM, PROGRAM))
)
# ----- page configuration --------------------------------------------------
st.set_page_config(page_title="Copernicus Thesis Explorer",
                   page_icon=os.path.join(os.path.dirname(__file__), "Utrecht_University_logo_round.svg"),
                   layout="wide",
                   initial_sidebar_state="collapsed")

# session state for details overlay
if 'selected_details' not in st.session_state:
    st.session_state.selected_details = None

# session state for PDF overlay
if 'selected_pdf' not in st.session_state:
    st.session_state.selected_pdf = None

# session state for pagination
if 'explorer_page' not in st.session_state:
    st.session_state.explorer_page = 0

# session state for saved filter values (preserved when entering/leaving details)
_FILTER_KEYS = [
    "saved_search_query", "saved_year_filter", "saved_sdg_filter",
    "saved_sector_filter", "saved_method_filter", "saved_theory_filter",
    "saved_geo_filter", "saved_scale_filter", "saved_internship_org_filter",
    "saved_master_track_filter", "saved_program_filter", "saved_featured_only",
]
for _fk in _FILTER_KEYS:
    if _fk not in st.session_state:
        if _fk == "saved_search_query" or _fk == "saved_theory_filter":
            st.session_state[_fk] = ""
        elif _fk == "saved_featured_only":
            st.session_state[_fk] = False
        else:
            st.session_state[_fk] = []

# session state for navigation history (back button)
if 'nav_history' not in st.session_state:
    st.session_state.nav_history = []

def _push_nav_history() -> None:
    """Capture current page state onto the navigation history stack (max 10 entries)."""
    _entry = {
        'program': st.session_state.get('program', 'sbi'),
        'page_nav': st.session_state.get('page_nav', 'Explorer'),
        'selected_details': st.session_state.get('selected_details'),
        'selected_pdf': st.session_state.get('selected_pdf'),
        'sup_selected': st.session_state.get('sup_selected'),
        'sup_view': st.session_state.get('sup_view', 'directory'),
    }
    _hist = st.session_state.get('nav_history', [])
    if not _hist or _hist[-1] != _entry:
        st.session_state.nav_history = (_hist + [_entry])[-10:]

# Map of saved_* session keys ↔ short URL param keys for the Explorer.
# Browser back/forward only restores state that lives in the URL, so we
# round-trip every filter through query params.
_FILTER_URL_KEYS = {
    "saved_search_query":          ("q",        "str"),
    "saved_year_filter":           ("years",    "list"),
    "saved_sdg_filter":            ("sdgs",     "list"),
    "saved_sector_filter":         ("sectors",  "list"),
    "saved_method_filter":         ("methods",  "list"),
    "saved_theory_filter":         ("theories", "str"),
    "saved_geo_filter":            ("geos",     "list"),
    "saved_scale_filter":          ("scales",   "list"),
    "saved_internship_org_filter": ("orgs",     "list"),
    "saved_master_track_filter":   ("tracks",   "list"),
    "saved_program_filter":        ("progs",    "list"),
    "saved_featured_only":         ("featured", "bool"),
}

# Maps each saved_* key to the widget key that displays it, so we can seed
# the widget's session-state entry on a hard reload (Streamlit reads from
# the widget key once it exists, ignoring the `default=` argument).
_FILTER_WIDGET_KEYS = {
    "saved_search_query":          "explorer_search_input",
    "saved_year_filter":           "filter_year",
    "saved_sdg_filter":            "filter_sdg",
    "saved_sector_filter":         "filter_sector",
    "saved_method_filter":         "filter_method",
    "saved_theory_filter":         "filter_theory",
    "saved_geo_filter":            "filter_geo",
    "saved_scale_filter":          "filter_scale",
    "saved_internship_org_filter": "filter_internship_org",
    "saved_master_track_filter":   "filter_master_track",
    "saved_program_filter":        "filter_program",
    "saved_featured_only":         "filter_featured",
}

def _sync_explorer_url() -> None:
    """Mirror the current Explorer filter + page state into st.query_params.

    Streamlit assigns to query_params via replaceState (no new history entry),
    so this is silent — the user only sees a history entry when a major
    navigation (detail / pdf / supervisor / nav switch) happens.
    """
    if st.session_state.get('page') != 'dashboard':
        return
    if st.session_state.get('selected_details') or st.session_state.get('selected_pdf'):
        return
    if st.session_state.get('page_nav') != 'Explorer':
        return
    qp = {"program": st.session_state.get('program', 'sbi')}
    for saved_key, (short, kind) in _FILTER_URL_KEYS.items():
        val = st.session_state.get(saved_key)
        if kind == "str" and val:
            qp[short] = str(val)
        elif kind == "list" and val:
            if short == "tracks":
                # Track names can contain commas, so store as a plain
                # (single-select) value rather than a comma-joined list.
                qp[short] = str(val[0])
            else:
                qp[short] = ",".join(str(v) for v in val)
        elif kind == "bool" and val:
            qp[short] = "1"
    page_num = int(st.session_state.get('explorer_page', 0) or 0)
    if page_num > 0:
        qp["page"] = str(page_num)
    # Only rewrite if something changed; otherwise Streamlit re-applies the
    # same URL each rerun, which is wasted work.
    current = {k: st.query_params[k] for k in st.query_params}
    if current != qp:
        st.query_params.clear()
        for k, v in qp.items():
            st.query_params[k] = v
    # Record what we just synced so the next rerun can detect external URL changes.
    st.session_state._last_synced_params = dict(st.query_params)


def _sync_supervisor_url() -> None:
    """Mirror Supervisor directory/finder state into st.query_params."""
    if st.session_state.get('page') != 'dashboard':
        return
    if st.session_state.get('page_nav') != 'Supervisors':
        return
    if st.session_state.get('sup_selected'):
        # Profile view has its own URL shape (sup_selected=...) which is
        # written by the click handler — don't overwrite.
        return
    sup_view = st.session_state.get('sup_view', 'directory')
    qp = {"program": st.session_state.get('program', 'sbi'), "nav": "Supervisors"}
    if sup_view == 'finder':
        qp["sup_view"] = "finder"
        _topic = st.session_state.get('sup_finder_topic', '')
        _dept  = st.session_state.get('sup_finder_dept', '')
        if _topic:
            qp["sup_topic"] = str(_topic)
        if _dept and _dept != "Any":
            qp["sup_dept"] = str(_dept)
        if st.session_state.get('sup_finder_results'):
            qp["sup_results"] = "1"
    else:
        _search = st.session_state.get('sup_search', '')
        if _search:
            qp["sup_search"] = str(_search)
    current = {k: st.query_params[k] for k in st.query_params}
    if current != qp:
        st.query_params.clear()
        for k, v in qp.items():
            st.query_params[k] = v


def _restore_filters_from_url(force: bool = False) -> None:
    """Populate saved_* filter keys (and widget keys) from URL query params.

    Called during init when the URL describes an Explorer grid view (no
    details/pdf/sup_selected). After a hard reload (browser back/forward via
    location.replace), session_state is empty so widget defaults must come
    from the URL — that's why we also seed the widget keys.

    Subtlety: we only seed widget keys *when they don't yet exist* on a
    normal rerun (user changed a filter widget). On a normal rerun, Streamlit
    has already stored the new widget value into session_state[widget_key];
    the URL still holds the previous value because _sync_explorer_url hasn't
    fired yet for this run. Seeding unconditionally would clobber the change.

    When `force=True` (URL changed externally — chip click / page navigation),
    we update widget keys unconditionally so the widgets reflect the new URL.
    """
    for saved_key, (short, kind) in _FILTER_URL_KEYS.items():
        raw = st.query_params.get(short)
        if raw is None:
            # Filter absent from URL → clear saved key (chip removed it)
            if force:
                if kind in ("list",):
                    st.session_state[saved_key] = []
                elif kind == "bool":
                    st.session_state[saved_key] = False
                elif kind == "str":
                    st.session_state[saved_key] = ""
                widget_key = _FILTER_WIDGET_KEYS.get(saved_key)
                if widget_key and widget_key in st.session_state:
                    del st.session_state[widget_key]
            continue
        if kind == "str":
            parsed = str(raw)
        elif kind == "list":
            if short == "tracks":
                # Track names may contain commas — never split; always a
                # single-select value.
                parsed = [str(raw)] if raw else []
            else:
                parsed = [p for p in str(raw).split(",") if p]
        elif kind == "bool":
            parsed = str(raw) == "1"
        else:
            continue
        # saved_* is recomputed from the widget later in the render — safe to
        # set here unconditionally.
        st.session_state[saved_key] = parsed
        widget_key = _FILTER_WIDGET_KEYS.get(saved_key)
        if widget_key and (force or widget_key not in st.session_state):
            st.session_state[widget_key] = parsed
    _page_raw = st.query_params.get("page")
    if _page_raw is not None:
        try:
            st.session_state.explorer_page = max(0, int(_page_raw))
        except (TypeError, ValueError):
            pass
    elif force:
        st.session_state.explorer_page = 0

# session state for homepage navigation
if 'page' not in st.session_state:
    st.session_state.page = "home"
if 'program' not in st.session_state:
    st.session_state.program = "sbi"

# Derive navigation state from URL — this keeps the browser back/forward button working.
# URL params are preserved (not cleared) so each navigation step has its own history entry.
_VALID_PROGRAMS = {"sbi", "energy_science", "sustainable_development", "innovation_sciences", "water_management", _ALL_PROGRAM_KEY}
_program_from_query = st.query_params.get("program")
_details_from_query = st.query_params.get("details")
_pdf_from_query     = st.query_params.get("pdf")

# Logo / back-home link (explicit override — always honoured first)
if st.query_params.get("back_home") == "1":
    st.session_state.page = "home"
    st.session_state.selected_details = None
    st.session_state.selected_pdf = None
    st.query_params.clear()
    st.rerun()

# Thesis details view  — URL: ?program=PROG&details=KEY
elif _details_from_query:
    if _program_from_query and _program_from_query in _VALID_PROGRAMS:
        st.session_state.program = _program_from_query
    st.session_state.page = "dashboard"
    # Only reset PDF state when switching to a *different* thesis (not on every rerun)
    if str(_details_from_query) != str(st.session_state.get("selected_details", "")):
        _push_nav_history()  # record where we came from before entering this detail page
        st.session_state.selected_pdf = None
    st.session_state.selected_details = str(_details_from_query)

# Full-page PDF viewer — URL: ?program=PROG&pdf=FILENAME
elif _pdf_from_query:
    if _program_from_query and _program_from_query in _VALID_PROGRAMS:
        st.session_state.program = _program_from_query
    if str(_pdf_from_query) != str(st.session_state.get("selected_pdf", "")):
        _push_nav_history()  # record where we came from before opening the PDF viewer
    st.session_state.page = "dashboard"
    st.session_state.selected_pdf = str(_pdf_from_query)
    st.session_state.selected_details = None

else:
    # Supervisor card click → open profile (must be before the generic program handler)
    _sup_selected_from_query = st.query_params.get("sup_selected")
    if _sup_selected_from_query:
        if _program_from_query and _program_from_query in _VALID_PROGRAMS:
            st.session_state.program = _program_from_query
        # Only push nav history when we're newly entering this profile (not on
        # every rerun of the same URL).
        if str(_sup_selected_from_query) != str(st.session_state.get("sup_selected", "")):
            _push_nav_history()
        st.session_state.page = "dashboard"
        st.session_state.page_nav = "Supervisors"
        st.session_state.sup_selected = _sup_selected_from_query
        st.session_state.sup_view = 'profile'
        # Keep the URL as-is (?program=…&sup_selected=…) so browser back/
        # forward and reloads land on the same profile.

    elif _program_from_query and _program_from_query in _VALID_PROGRAMS:
        # Programme dashboard — URL: ?program=PROG[&nav=SECTION]
        st.session_state.program = _program_from_query
        st.session_state.page = "dashboard"
        st.session_state.selected_details = None
        st.session_state.selected_pdf = None
        _nav_from_query = st.query_params.get("nav")
        if _nav_from_query in ("Explorer", "Supervisors", "Insights"):
            st.session_state.page_nav = _nav_from_query

        # Restore Explorer filter / pagination state from URL — required so
        # that a browser back/forward (which triggers location.replace) lands
        # the user on the same filtered, paginated grid they left.
        # force=True when URL changed externally (chip/clear click or back-button)
        # so widget keys are updated even if session state was preserved.
        if st.session_state.get("page_nav", "Explorer") == "Explorer":
            _current_params = dict(st.query_params)
            _last_params = st.session_state.get("_last_synced_params")
            _url_changed_externally = (_last_params is None) or (_last_params != _current_params)
            _restore_filters_from_url(force=_url_changed_externally)

        # Restore Supervisor directory / finder state from URL.
        if st.session_state.get("page_nav") == "Supervisors":
            _sup_view_q = st.query_params.get("sup_view")
            if _sup_view_q == "finder":
                st.session_state.sup_view = "finder"
                st.session_state.sup_finder_topic = st.query_params.get("sup_topic", "") or ""
                st.session_state.sup_finder_dept  = st.query_params.get("sup_dept", "Any") or "Any"
                st.session_state.sup_finder_results = st.query_params.get("sup_results") == "1"
            else:
                # Directory view — restore search box only when not currently
                # on a supervisor profile (which is identified by sup_selected).
                if not st.session_state.get("sup_selected"):
                    st.session_state.sup_view = "directory"
                    _sup_search_q = st.query_params.get("sup_search")
                    if _sup_search_q is not None:
                        st.session_state.sup_search = str(_sup_search_q)
                        st.session_state["sup_search_input"] = str(_sup_search_q)

    else:
        # No URL params → home page (handles browser back-button to home)
        st.session_state.page = "home"
        st.session_state.selected_details = None
        st.session_state.selected_pdf = None

THESES_PER_PAGE = 16

# ----- custom CSS -----------------------------------------------------------
# Utrecht University official colours (blue & new yellow) are used below
# to give a more institutional look.  Additional tweaks for cards, headers and
# the sidebar make the app feel more "polished".
# new yellow: PMS 116C (HEX #FFCD00)
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Merriweather:wght@300;400;700&display=swap');
    :root {
        --uu-yellow: #FFCD00;
        --uu-blue: #003660;
    }
    /* page background */
    .stApp {
        background-color: #f4f4f4;
        font-family: 'Merriweather', serif;
    }

    /* ── Persistent top app-bar ─────────────────────────────────────── */
    /* The bar blends with the per-programme tinted page background
       (set in the per-programme tint block) — no opaque white chrome.
       A 1px hairline separates it from content when scrolled. */
    /* Hide Streamlit's built-in top chrome (deploy button, three-dot menu,
       running indicator) — this dashboard is end-user-facing. */
    [data-testid="stHeader"] { display: none !important; }
    [data-testid="stToolbar"] { display: none !important; }
    [data-testid="stDecoration"] { display: none !important; }
    #MainMenu { display: none !important; }
    /* Streamlit 1.55+ defaults the main block-container to padding-top:6rem.
       Kill it on every selector variant so the topbar sits flush to the top. */
    [data-testid="stAppViewContainer"] > section,
    [data-testid="stAppViewContainer"] [data-testid="stMain"],
    [data-testid="stAppViewContainer"] .main {
        padding-top: 0 !important;
    }
    [data-testid="stMainBlockContainer"],
    [data-testid="stAppViewContainer"] .main .block-container,
    .block-container {
        padding-top: 0 !important;
    }
    .topbar {
        position: sticky;
        top: 0;
        z-index: 100;
        padding: 6px 4px 10px 4px;
        margin: 0 -1rem 18px -1rem;
        border-bottom: 1px solid rgba(0,54,96,0.08);
    }
    .topbar-row {
        display: flex;
        align-items: center;
        gap: 18px;
        padding: 0 14px;
        flex-wrap: wrap;
    }
    .topbar-brand {
        display: flex;
        align-items: center;
        gap: 14px;
        text-decoration: none !important;
        color: var(--uu-blue) !important;
        flex-shrink: 0;
    }
    .topbar-brand:hover { color: var(--uu-blue) !important; }
    .topbar-logo {
        width: 56px;
        height: 56px;
        object-fit: contain;
    }
    .topbar-title {
        font-weight: 700;
        font-size: 1.42rem;
        letter-spacing: -0.02em;
        color: var(--uu-blue);
        line-height: 1.15;
    }
    .topbar-nav {
        display: flex;
        gap: 10px;
        margin-left: 22px;
        flex: 1;
        flex-wrap: wrap;
    }
    /* Nav links styled as white card pills to match the existing
       sidebar-nav button aesthetic (white bg, blue border, UU-blue text,
       soft shadow, hover lift). */
    .topnav-link {
        text-decoration: none !important;
        color: var(--uu-blue) !important;
        background: #ffffff;
        border: 1px solid rgba(0,54,96,0.12);
        padding: 9px 20px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.92rem;
        letter-spacing: 0.01em;
        transition: background 0.18s, border-color 0.18s,
                    box-shadow 0.18s, transform 0.18s;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    .topnav-link:hover {
        background: #f4f8fc;
        border-color: rgba(0,54,96,0.25);
        box-shadow: 0 5px 14px rgba(0,0,0,0.10);
        transform: translateY(-1px);
    }
    .topnav-link.active {
        background: var(--uu-yellow);
        color: var(--uu-blue) !important;
        border-color: var(--uu-yellow);
        font-weight: 700;
        box-shadow: 0 4px 12px rgba(255,205,0,0.35);
    }
    .topnav-link.active:hover {
        background: var(--uu-yellow);
        box-shadow: 0 6px 16px rgba(255,205,0,0.45);
    }
    /* Programme switcher — <details>-based dropdown */
    .topbar-switcher-wrap {
        position: relative;
        flex-shrink: 0;
    }
    .topbar-switcher {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 9px 14px;
        border-radius: 12px;
        border: 1px solid rgba(0,54,96,0.12);
        background: #ffffff;
        font-size: 0.88rem;
        color: var(--uu-blue);
        cursor: pointer;
        font-family: inherit;
        font-weight: 600;
        max-width: 260px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        transition: border-color 0.18s, box-shadow 0.18s;
        list-style: none;
        user-select: none;
    }
    .topbar-switcher::-webkit-details-marker,
    .topbar-switcher::marker {
        display: none;
        content: '';
    }
    .topbar-switcher:hover {
        border-color: rgba(0,54,96,0.25);
        box-shadow: 0 5px 14px rgba(0,0,0,0.10);
    }
    .topbar-switcher .chev {
        font-size: 0.8rem;
        opacity: 0.6;
        transition: transform 0.18s;
    }
    .topbar-switcher-wrap[open] .topbar-switcher {
        border-color: rgba(0,54,96,0.25);
        box-shadow: 0 5px 14px rgba(0,0,0,0.10);
    }
    .topbar-switcher-wrap[open] .topbar-switcher .chev {
        transform: rotate(180deg);
    }
    .topbar-switcher-menu {
        position: absolute;
        right: 0;
        top: calc(100% + 6px);
        min-width: 280px;
        background: #ffffff;
        border: 1px solid rgba(0,54,96,0.12);
        border-radius: 12px;
        box-shadow: 0 10px 28px rgba(0,0,0,0.14);
        padding: 6px;
        z-index: 200;
        overflow: hidden;
    }
    .topbar-switcher-item {
        display: block;
        padding: 9px 14px;
        color: var(--uu-blue) !important;
        text-decoration: none !important;
        font-size: 0.88rem;
        font-weight: 500;
        border-radius: 8px;
        transition: background 0.12s;
    }
    .topbar-switcher-item:hover {
        background: rgba(255,205,0,0.18);
    }
    .topbar-switcher-item.active {
        background: var(--uu-yellow);
        font-weight: 700;
    }
    .topbar-crumbs {
        font-size: 0.8rem;
        color: rgba(0,54,96,0.55);
        padding: 10px 16px 0 16px;
        letter-spacing: 0.01em;
    }
    .topbar-crumbs a {
        color: rgba(0,54,96,0.7) !important;
        text-decoration: none !important;
        font-weight: 500;
        transition: color 0.15s;
    }
    .topbar-crumbs a:hover {
        color: var(--uu-blue) !important;
        text-decoration: none !important;
    }
    .topbar-sep {
        margin: 0 8px;
        color: rgba(0,54,96,0.28);
    }
    .topbar-crumb-current {
        color: var(--uu-blue);
        font-weight: 700;
    }

    /* ── Active filter chips ────────────────────────────────────────── */
    .filter-chips {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin: 4px 0 14px 0;
        align-items: center;
    }
    .filter-chip {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 5px 11px;
        background: var(--uu-yellow);
        color: var(--uu-blue);
        border-radius: 999px;
        font-size: 0.82rem;
        font-weight: 600;
        text-decoration: none;
        transition: filter 0.15s, transform 0.1s;
    }
    .filter-chip .x {
        font-weight: 700;
        font-size: 1rem;
        line-height: 1;
        opacity: 0.55;
    }
    .filter-chip:hover {
        filter: brightness(0.95);
        transform: translateY(-1px);
    }
    .filter-chip:hover .x {
        opacity: 1;
    }
    .filter-chip-clear {
        font-size: 0.82rem;
        color: #888;
        text-decoration: underline;
        padding: 5px 6px;
    }
    .filter-chip-clear:hover {
        color: var(--uu-blue);
    }

    /* ── Sidebar navigation items (key-based selectors for reliable styling) ── */
    section[data-testid="stSidebar"] .st-key-sidenav_Explorer,
    section[data-testid="stSidebar"] .st-key-sidenav_Supervisors,
    section[data-testid="stSidebar"] .st-key-sidenav_Insights {
        margin-bottom: 0.24rem !important;
    }
    section[data-testid="stSidebar"] .st-key-sidenav_Explorer .stButton > button,
    section[data-testid="stSidebar"] .st-key-sidenav_Supervisors .stButton > button,
    section[data-testid="stSidebar"] .st-key-sidenav_Insights .stButton > button {
        border-radius: 12px !important;
        padding: 0.56rem 0.92rem !important;
        width: 100% !important;
        text-align: left !important;
        font-size: 0.88rem !important;
        letter-spacing: 0.01em !important;
        transition: background 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease !important;
    }
    /* Inactive nav item — white bg, blue text */
    section[data-testid="stSidebar"] .st-key-sidenav_Explorer .stButton > button[data-testid="baseButton-secondary"],
    section[data-testid="stSidebar"] .st-key-sidenav_Supervisors .stButton > button[data-testid="baseButton-secondary"],
    section[data-testid="stSidebar"] .st-key-sidenav_Insights .stButton > button[data-testid="baseButton-secondary"] {
        background: #ffffff !important;
        border: 1px solid rgba(0,54,96,0.12) !important;
        color: #003660 !important;
        font-weight: 600 !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08) !important;
    }
    section[data-testid="stSidebar"] .st-key-sidenav_Explorer .stButton > button[data-testid="baseButton-secondary"]:hover,
    section[data-testid="stSidebar"] .st-key-sidenav_Supervisors .stButton > button[data-testid="baseButton-secondary"]:hover,
    section[data-testid="stSidebar"] .st-key-sidenav_Insights .stButton > button[data-testid="baseButton-secondary"]:hover {
        background: #f0f5fa !important;
        border-color: rgba(0,54,96,0.25) !important;
        color: #003660 !important;
        box-shadow: 0 5px 14px rgba(0,0,0,0.12) !important;
        transform: translateY(-2px) !important;
    }
    /* Active nav item */
    section[data-testid="stSidebar"] .st-key-sidenav_Explorer .stButton > button[data-testid="baseButton-primary"],
    section[data-testid="stSidebar"] .st-key-sidenav_Supervisors .stButton > button[data-testid="baseButton-primary"],
    section[data-testid="stSidebar"] .st-key-sidenav_Insights .stButton > button[data-testid="baseButton-primary"] {
        background: #ffffff !important;
        border: none !important;
        color: #0a3d5c !important;
        font-weight: 700 !important;
        box-shadow: 0 6px 18px rgba(0,0,0,0.18) !important;
        transform: translateY(-1px) !important;
    }
    section[data-testid="stSidebar"] .st-key-sidenav_Explorer .stButton > button[data-testid="baseButton-primary"]:hover,
    section[data-testid="stSidebar"] .st-key-sidenav_Supervisors .stButton > button[data-testid="baseButton-primary"]:hover,
    section[data-testid="stSidebar"] .st-key-sidenav_Insights .stButton > button[data-testid="baseButton-primary"]:hover {
        background: #f4f8fc !important;
        color: #07314b !important;
        box-shadow: 0 8px 22px rgba(0,0,0,0.22) !important;
        transform: translateY(-2px) !important;
    }
    /* Back to Programs button */
    section[data-testid="stSidebar"] .st-key-sidenav_back_to_programs {
        margin-bottom: 0.8rem !important;
    }
    section[data-testid="stSidebar"] .st-key-sidenav_back_to_programs .stButton > button {
        border-radius: 10px !important;
        padding: 0.44rem 0.8rem !important;
        width: 100% !important;
        text-align: left !important;
        font-size: 0.78rem !important;
        letter-spacing: 0.01em !important;
        background: #FFCD00 !important;
        border: none !important;
        color: #111111 !important;
        font-weight: 700 !important;
        transition: background 0.18s ease, color 0.18s ease !important;
    }
    section[data-testid="stSidebar"] .st-key-sidenav_back_to_programs .stButton > button:hover {
        background: #e6b800 !important;
        color: #111111 !important;
    }
    /* Small nav label above navigation items */
    .sidebar-programme-label {
        font-size: 0.62rem;
        font-weight: 700;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: rgba(255,255,255,0.28);
        padding: 16px 2px 5px 2px;
    }

    /* ── Modern sidebar ── */
    section[data-testid="stSidebar"] {
        background: linear-gradient(175deg, #0a3d5c 0%, #0e5080 100%) !important;
        border-right: 1px solid rgba(255,255,255,0.09) !important;
    }
    section[data-testid="stSidebar"]::-webkit-scrollbar { width: 4px; }
    section[data-testid="stSidebar"]::-webkit-scrollbar-thumb {
        background: rgba(255,255,255,0.12); border-radius: 4px;
    }

    /* Global sidebar text */
    section[data-testid="stSidebar"] * {
        color: rgba(255,255,255,0.75) !important;
    }
    section[data-testid="stSidebar"] .stMarkdown {
        color: rgba(255,255,255,0.75) !important;
    }

    /* ── Navigation radio is no longer used for page nav (moved to main area tab bar) ── */
    section[data-testid="stSidebar"] .stRadio {
        display: none !important;
    }

    /* ── Sidebar section headers (h3 rendered by st.sidebar.header) ── */
    section[data-testid="stSidebar"] h3 {
        color: rgba(255,255,255,0.35) !important;
        font-size: 0.68rem !important;
        letter-spacing: 0.12em !important;
        text-transform: uppercase !important;
        font-weight: 700 !important;
        margin: 1.2rem 0 0.5rem 0 !important;
        padding-left: 2px !important;
    }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2 {
        color: rgba(255,255,255,0.35) !important;
        font-size: 0.68rem !important;
        letter-spacing: 0.12em !important;
        text-transform: uppercase !important;
    }

    /* ── Sidebar nav/filter separator ── */
    section[data-testid="stSidebar"] hr {
        border-color: rgba(255,255,255,0.09) !important;
        margin: 10px 0 !important;
    }

    /* ── Search input ── */
    /* Target the BaseWeb outer wrapper that Streamlit renders */
    section[data-testid="stSidebar"] [data-testid="stTextInput"] [data-baseweb="input"],
    section[data-testid="stSidebar"] [data-testid="stTextInput"] [data-baseweb="base-input"] {
        background: #ffffff !important;
        border: 1px solid rgba(255,255,255,0.5) !important;
        border-radius: 10px !important;
        padding: 0 !important;
    }
    /* The actual <input> element inside */
    section[data-testid="stSidebar"] [data-testid="stTextInput"] input,
    section[data-testid="stSidebar"] [data-baseweb="input"] input,
    section[data-testid="stSidebar"] [data-baseweb="base-input"] input {
        background: transparent !important;
        color: #111111 !important;
        -webkit-text-fill-color: #111111 !important;
        caret-color: #111111 !important;
        padding: 8px 14px !important;
        font-size: 0.88rem !important;
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
    }
    section[data-testid="stSidebar"] [data-testid="stTextInput"] input::placeholder {
        color: #999999 !important;
        -webkit-text-fill-color: #999999 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stTextInput"] [data-baseweb="input"]:focus-within,
    section[data-testid="stSidebar"] [data-testid="stTextInput"] [data-baseweb="base-input"]:focus-within {
        border-color: rgba(255,205,0,0.8) !important;
        box-shadow: 0 0 0 3px rgba(255,205,0,0.2) !important;
        background: #ffffff !important;
    }

    /* ── Multiselect ── */
    section[data-testid="stSidebar"] .stMultiSelect [data-baseweb="select"] > div:first-child {
        background: rgba(255,255,255,0.07) !important;
        border: 1px solid rgba(255,255,255,0.15) !important;
        border-radius: 10px !important;
    }
    section[data-testid="stSidebar"] .stMultiSelect [data-baseweb="select"] > div:first-child:hover {
        border-color: rgba(255,255,255,0.3) !important;
    }
    section[data-testid="stSidebar"] .stMultiSelect input {
        color: #fff !important;
    }
    section[data-testid="stSidebar"] .stMultiSelect [data-baseweb="tag"] {
        background: rgba(255,205,0,0.16) !important;
        border: 1px solid rgba(255,205,0,0.3) !important;
        border-radius: 6px !important;
    }
    section[data-testid="stSidebar"] .stMultiSelect [data-baseweb="tag"] span {
        color: #ffe066 !important;
    }

    /* ── Widget labels (Year, SDG, Sector, etc.) ── */
    section[data-testid="stSidebar"] label[data-testid="stWidgetLabel"] p {
        color: rgba(255,255,255,0.45) !important;
        font-size: 0.72rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.08em !important;
        font-weight: 700 !important;
    }

    /* ── Expander ── */
    section[data-testid="stSidebar"] details {
        border: 1px solid rgba(255,255,255,0.1) !important;
        border-radius: 12px !important;
        background: rgba(255,255,255,0.06) !important;
        margin-top: 6px !important;
        overflow: hidden !important;
    }
    section[data-testid="stSidebar"] details summary {
        color: rgba(255,255,255,0.7) !important;
        font-size: 0.88rem !important;
        font-weight: 600 !important;
        padding: 10px 14px !important;
        background: transparent !important;
    }
    section[data-testid="stSidebar"] details summary:hover {
        background: rgba(255,255,255,0.05) !important;
    }
    section[data-testid="stSidebar"] details[open] summary {
        border-bottom: 1px solid rgba(255,255,255,0.07) !important;
        background: transparent !important;
    }
    /* Expander content: nuke any white backgrounds injected by Streamlit globals */
    section[data-testid="stSidebar"] details > div,
    section[data-testid="stSidebar"] details > div > div,
    section[data-testid="stSidebar"] details > div > div > div,
    section[data-testid="stSidebar"] [data-testid="stExpanderDetails"],
    section[data-testid="stSidebar"] [data-testid="stExpanderDetails"] > div,
    section[data-testid="stSidebar"] [data-testid="stExpanderDetails"] > div > div,
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        background-color: transparent !important;
        background: transparent !important;
    }
    section[data-testid="stSidebar"] .stExpander {
        border: 1px solid rgba(255,255,255,0.1) !important;
        border-radius: 12px !important;
        background: rgba(255,255,255,0.06) !important;
        margin-top: 6px !important;
    }
    section[data-testid="stSidebar"] .stExpander header {
        color: rgba(255,255,255,0.72) !important;
        font-size: 0.88rem !important;
        font-weight: 600 !important;
        background: transparent !important;
    }
    /* Widget labels inside expander */
    section[data-testid="stSidebar"] [data-testid="stExpanderDetails"] label p,
    section[data-testid="stSidebar"] [data-testid="stExpanderDetails"] [data-testid="stWidgetLabel"] p {
        color: rgba(255,255,255,0.72) !important;
    }
    section[data-testid="stSidebar"] [data-testid="stExpanderIcon"] svg {
        color: rgba(255,255,255,0.38) !important;
        fill: rgba(255,255,255,0.38) !important;
    }

    /* ── Checkbox ── */
    section[data-testid="stSidebar"] .stCheckbox label p {
        color: rgba(255,255,255,0.65) !important;
        font-size: 0.87rem !important;
        text-transform: none !important;
        letter-spacing: normal !important;
        font-weight: 400 !important;
    }

    /* ── Caption ── */
    section[data-testid="stSidebar"] .stCaption,
    section[data-testid="stSidebar"] .stCaption p {
        color: rgba(255,255,255,0.3) !important;
        font-size: 0.74rem !important;
    }

    /* ── Sidebar buttons (Minimize / ☰) ── */
    section[data-testid="stSidebar"] .stButton > button {
        background: rgba(255,255,255,0.07) !important;
        border: 1px solid rgba(255,255,255,0.15) !important;
        color: rgba(255,255,255,0.75) !important;
        border-radius: 10px !important;
        font-weight: 500 !important;
        font-size: 0.88rem !important;
        padding: 0.44rem 1rem !important;
        transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease !important;
        width: 100% !important;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(255,255,255,0.14) !important;
        color: #fff !important;
        border-color: rgba(255,255,255,0.28) !important;
    }

    /* metric cards */
    div[data-testid="metric-container"] {
        background-color: #ffffff;
        border: 1px solid var(--uu-yellow);
        border-radius: 5px;
        padding: 8px 10px;
    }

    /* expander header shading */
    .st-expanderHeader {
        font-weight: bold;
    }

    /* make download button stand out */
    button[title="Download file"] {
        background-color: var(--uu-yellow) !important;
        color: var(--uu-blue) !important;
    }

    /* thesis cards */
    .thesis-card-link,
    .thesis-card-link:hover,
    .thesis-card-link:visited,
    .thesis-card-link:active {
        text-decoration: none !important;
        color: inherit !important;
    }
    .thesis-card-link *:not(.thesis-sdg *):not(.thesis-sdg) {
        text-decoration: none !important;
        color: inherit !important;
    }
    .thesis-card-link {
        display: block;
    }
    .sup-card-link,
    .sup-card-link:hover,
    .sup-card-link:visited,
    .sup-card-link:active {
        text-decoration: none !important;
        color: inherit !important;
        display: flex;
        flex-direction: column;
    }
    .sup-card-link * {
        text-decoration: none !important;
        color: inherit !important;
    }
    /* Grid container for the directory — equal-height cards per row */
    .sup-card-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 1rem;
        margin-top: 0.4rem;
    }
    @media (max-width: 860px) {
        .sup-card-grid { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 540px) {
        .sup-card-grid { grid-template-columns: 1fr; }
    }
    .thesis-card {
        background-color: #ffffff;
        border: 1px solid #e6e6e6;
        border-radius: 12px;
        padding: 14px 10px 12px 10px;
        margin-bottom: 18px;
        box-shadow: 0 4px 14px rgba(0,0,0,0.06);
        display: flex;
        flex-direction: column;
        height: 100%;
        min-height: 340px;
        max-height: 340px;
        cursor: pointer;
        transition: transform 0.18s ease, box-shadow 0.18s ease;
        overflow: hidden;
    }
    .thesis-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 10px 24px rgba(0,0,0,0.12);
    }
    /* Ensure Streamlit columns stretch equally so cards line up */
    div[data-testid="stHorizontalBlock"] {
        align-items: stretch;
    }
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
        display: flex;
        flex-direction: column;
    }
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] > div {
        flex: 1;
    }
    .thesis-card-link {
        height: 100%;
    }
    .thesis-cover {
        width: 100%;
        height: 210px;
        border-radius: 8px;
        margin-bottom: 10px;
        background: #eee;
        overflow: hidden;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        position: relative;
    }
    .thesis-cover-badge {
        position: absolute;
        top: 8px;
        right: 8px;
        background-color: var(--uu-yellow);
        color: var(--uu-blue);
        border-radius: 999px;
        padding: 3px 10px;
        font-size: 0.74em;
        font-weight: 700;
        white-space: nowrap;
        box-shadow: 0 2px 6px rgba(0,0,0,0.18);
        pointer-events: none;
        z-index: 2;
    }
    .thesis-cover-image {
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
    }
    .thesis-cover-placeholder {
        color: #666;
        font-style: italic;
        font-size: 0.92em;
    }
    .thesis-title {
        font-size: 1.05em;
        font-weight: 700;
        color: var(--uu-blue);
        margin: 0 0 6px 0;
        line-height: 1.25em;
        max-height: 3.75em;
        overflow: hidden;
        display: -webkit-box;
        -webkit-line-clamp: 3;
        -webkit-box-orient: vertical;
        text-overflow: ellipsis;
        min-height: 1.25em;
    }
    .thesis-meta {
        font-size: 0.92em;
        color: #555;
        margin-bottom: 0;
        min-height: 1.2em;
        max-height: 1.2em;
        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
        margin-top: auto;
    }
    .thesis-sdg {
        margin-bottom: 10px;
        min-height: 34px;
        max-height: 34px;
        overflow: hidden;
    }
    .thesis-sdg div {
        color: #ffffff !important;
    }
    .thesis-tags {
        margin-bottom: 12px;
        min-height: 1.4em;
        max-height: 1.4em;
        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
        color: #555;
        font-size: 0.85em;
    }
    .featured-badge {
        display: inline-block;
        background-color: var(--uu-yellow);
        color: var(--uu-blue);
        border-radius: 999px;
        padding: 2px 8px;
        font-size: 0.78em;
        font-weight: 700;
        margin-left: 6px;
        vertical-align: middle;
        white-space: nowrap;
    }
    .featured-strip {
        margin: 2px 0 8px 0;
    }
    .thesis-card-spacer {
        flex: 1 1 auto;
        min-height: 10px;
    }
    .thesis-card-bottom {
        margin-top: 10px;
        display: flex;
        align-items: flex-end;
        justify-content: flex-end;
    }
    .tag {
        display: inline-block;
        background-color: #f2f2f2;
        color: #333;
        padding: 2px 6px;
        border-radius: 12px;
        margin-right: 4px;
        font-size: 0.85em;
    }
    .keywords-wrap {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 6px;
        margin-bottom: 4px;
    }
    .keyword-pill {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        border: 1px solid #cfcfcf;
        background-color: #fafafa;
        color: #2b2b2b;
        font-size: 0.86em;
        line-height: 1.2;
    }
    .thesis-card h4 {
        margin: 0 0 4px 0;
        font-size: 1.1em;
        color: var(--uu-blue);
    }
    /* Source-programme badge shown on cards in all-programmes mode */
    .thesis-prog-badge {
        display: inline-block;
        margin-top: 8px;
        padding: 3px 9px;
        border-radius: 6px;
        background: rgba(0,54,96,0.08);
        color: var(--uu-blue);
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.02em;
        text-transform: uppercase;
    }

    /* typography tweaks */
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Merriweather', serif;
    }
    p, span, div {
        font-family: 'Merriweather', serif;
    }

    /* pagination bar */
    .pagination-bar {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        margin: 18px 0 14px 0;
        flex-wrap: wrap;
    }
    .pagination-bar .page-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 36px;
        height: 36px;
        padding: 0 10px;
        border-radius: 8px;
        border: 1px solid #ccc;
        background: #fff;
        color: var(--uu-blue);
        font-family: 'Merriweather', serif;
        font-size: 0.92em;
        cursor: pointer;
        transition: all 0.15s ease;
        text-decoration: none;
    }
    .pagination-bar .page-btn:hover {
        background: var(--uu-yellow);
        border-color: var(--uu-yellow);
        color: var(--uu-blue);
    }
    .pagination-bar .page-btn.active {
        background: var(--uu-blue);
        color: #fff;
        border-color: var(--uu-blue);
        font-weight: 700;
        pointer-events: none;
    }
    .pagination-bar .page-btn.disabled {
        opacity: 0.4;
        pointer-events: none;
    }
    .pagination-info {
        text-align: center;
        color: #666;
        font-size: 0.88em;
        margin-bottom: 6px;
    }

    /* ── Thesis details page ── */
    .detail-hero-title {
        font-size: 1.78em;
        font-weight: 700;
        color: var(--uu-blue);
        margin: 0 0 8px 0;
        line-height: 1.3;
    }
    .detail-hero-meta {
        font-size: 0.95em;
        color: #444;
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
        margin-bottom: 8px;
    }
    .detail-hero-meta .sep { color: #bbb; }
    .detail-section-header {
        font-size: 1.0em;
        font-weight: 700;
        color: var(--uu-blue);
        margin-bottom: 10px;
        padding-bottom: 5px;
        border-bottom: 2px solid var(--uu-yellow);
    }
    /* White card styling for the 5 detail section boxes.
       Keys are set on each st.container(border=True) call, producing st-key-* classes.
       This precisely targets only those 5 containers. */
    .st-key-detail_overview,
    .st-key-detail_methodology,
    .st-key-detail_context,
    .st-key-detail_academic,
    .st-key-detail_partnerships {
        background-color: #ffffff !important;
        border: 1px solid #e6e6e6 !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 14px rgba(0,0,0,0.06) !important;
    }
    .detail-label {
        font-size: 0.78em;
        font-weight: 700;
        color: #777;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-top: 8px;
        margin-bottom: 2px;
    }
    .detail-rq {
        font-size: 0.95em;
        font-style: italic;
        color: #333;
        border-left: 3px solid var(--uu-yellow);
        padding: 6px 0 6px 14px;
        margin: 4px 0 10px 0;
        line-height: 1.55;
    }
    .detail-abstract {
        font-size: 0.92em;
        line-height: 1.65;
        color: #333;
        max-height: 280px;
        overflow-y: auto;
        padding-right: 8px;
    }
    .detail-field-value {
        font-size: 0.93em;
        color: #222;
        margin-bottom: 6px;
        line-height: 1.5;
    }
    .detail-org-row {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 6px;
    }
    .detail-org-logo {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        object-fit: contain;
        background: #f5f5f5;
        border: 1px solid #e0e0e0;
        flex-shrink: 0;
        padding: 3px;
    }
    .detail-sdg-slot {
        display: flex;
        justify-content: flex-start;
        align-items: center;
        width: 100%;
        min-height: 40px;
        margin-top: 2px;
        overflow: hidden;
    }
    .detail-sdg-slot .sdg-badge {
        display: flex !important;
        align-items: center;
        justify-content: flex-start;
        width: 100%;
        min-width: 0;
        max-width: 100%;
        box-sizing: border-box;
        white-space: nowrap !important;
        overflow: hidden;
        text-overflow: ellipsis;
        line-height: 1.3;
    }
    .detail-sdg-slot .sdg-badge img {
        flex: 0 0 auto;
    }
    .detail-sdg-slot .sdg-badge .sdg-label {
        display: block;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    /* ── Detail sections: ds-* component system ── */
    .ds-cards-wrap { display: flex; flex-direction: column; gap: 10px; }
    .ds-card {
        background: #fff;
        border-radius: 12px;
        border: 1px solid #eaeaea;
        padding: 18px 20px;
        box-shadow: 0 2px 10px rgba(0,0,0,.05);
    }
    .ds-title {
        font-size: 0.72em;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--uu-blue);
        padding-bottom: 9px;
        margin-bottom: 14px;
        border-bottom: 2px solid var(--uu-yellow);
    }
    .ds-grid   { display: grid; grid-template-columns: 1fr 1fr;       gap: 10px 20px; }
    .ds-grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr;   gap: 10px 14px; }
    .ds-row-pair { display: grid; grid-template-columns: 1fr 1fr;      gap: 10px; }
    .ds-field  { display: flex; flex-direction: column; gap: 3px; }
    .ds-lbl {
        font-size: 0.69em;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #aaa;
    }
    .ds-val  { font-size: 0.9em;  color: #1a1a1a; line-height: 1.5; }
    .ds-na   { font-size: 0.87em; color: #ccc;    font-style: italic; }
    .ds-sup-link {
        color: #1a1a1a !important;
        font-size: 0.9em;
        text-decoration: none !important;
        cursor: pointer;
        line-height: 1.5;
        border-bottom: 1px dotted #bbb;
        padding-bottom: 1px;
    }
    .ds-sup-link:hover { text-decoration: none !important; color: #1a1a1a !important; border-bottom-color: #555; }
    .ds-sup-wrap { display: inline-flex; align-items: center; }
    .ds-sup-photo {
        width: 32px; height: 32px; border-radius: 50%; object-fit: cover;
        flex-shrink: 0; margin-right: 7px;
        border: 1px solid #e0e0e0; vertical-align: middle;
    }
    .ds-rq {
        font-size: 0.92em;
        font-style: italic;
        color: #222;
        border-left: 3px solid var(--uu-yellow);
        padding: 8px 12px;
        margin: 5px 0 14px 0;
        line-height: 1.65;
        background: #fffdf0;
        border-radius: 0 6px 6px 0;
    }
    .ds-divider { height: 1px; background: #f2f2f2; margin: 12px 0; }
    .ds-pill-wrap { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 5px; }
    .ds-kw {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 999px;
        background: #eef3f8;
        border: 1px solid #cfdce8;
        color: var(--uu-blue);
        font-size: 0.80em;
        font-weight: 500;
    }
    .ds-abstract-wrap {
        margin: 6px 0 14px 0;
        border: 1px solid #eee;
        border-radius: 8px;
        overflow: hidden;
    }
    .ds-abstract-toggle {
        padding: 9px 14px;
        font-size: 0.78em;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        color: #666;
        cursor: pointer;
        list-style: none;
        display: flex;
        align-items: center;
        gap: 7px;
        background: #f8f8f8;
        user-select: none;
    }
    .ds-abstract-toggle::-webkit-details-marker { display: none; }
    .ds-abstract-toggle::before {
        content: '▸';
        font-size: 0.85em;
        color: var(--uu-blue);
        transition: transform 0.18s ease;
        display: inline-block;
        flex-shrink: 0;
    }
    details[open] > .ds-abstract-toggle::before { transform: rotate(90deg); }
    .ds-abstract-body {
        padding: 12px 14px;
        font-size: 0.9em;
        line-height: 1.7;
        color: #333;
        max-height: 240px;
        overflow-y: auto;
        border-top: 1px solid #eee;
    }
    .ds-org-row { display: flex; align-items: center; gap: 10px; margin-top: 2px; }
    .ds-org-logo {
        width: 30px;
        height: 30px;
        border-radius: 50%;
        object-fit: contain;
        background: #f5f5f5;
        border: 1px solid #e0e0e0;
        flex-shrink: 0;
        padding: 2px;
    }

    /* ── Homepage styles ── */
    .homepage-title,
    .stMarkdown h1.homepage-title {
        text-align: center;
        color: #ffffff !important;
        font-size: 2.6em;
        margin-top: 1rem;
        margin-bottom: 0.2rem;
    }
    .homepage-subtitle,
    .stMarkdown p.homepage-subtitle {
        text-align: center;
        color: #ffffff !important;
        font-size: 1.15em;
        margin-bottom: 2.5rem;
    }
    /* Programme selector as large icon buttons (no white card wrappers) */
    .programme-orb-link,
    .programme-orb-link:hover,
    .programme-orb-link:visited,
    .programme-orb-link:active {
        text-decoration: none !important;
        color: inherit !important;
        display: flex;
        justify-content: center;
        margin-bottom: 1.1rem;
    }
    .programme-orb {
        width: clamp(180px, 19vw, 260px);
        aspect-ratio: 1 / 1;
        border-radius: 50%;
        position: relative;
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0 auto;
        overflow: hidden;
        box-shadow: 0 10px 24px rgba(0,0,0,0.16), inset 0 0 0 1px rgba(255,255,255,0.45);
        backdrop-filter: blur(1px);
        -webkit-backdrop-filter: blur(1px);
        cursor: pointer;
        transition: transform 0.22s ease, box-shadow 0.22s ease;
        background: radial-gradient(circle at 30% 20%, rgba(255,255,255,0.52), rgba(255,255,255,0.18) 45%, rgba(255,255,255,0.04) 100%), var(--orb-bg, #f5f7fa);
    }
    .programme-orb:hover {
        transform: translateY(-5px) scale(1.02);
        box-shadow: 0 14px 28px rgba(0,0,0,0.2), inset 0 0 0 1px rgba(255,255,255,0.5);
    }
    .programme-orb::after {
        content: "";
        position: absolute;
        inset: 0;
        background: linear-gradient(to top, rgba(255,255,255,0.2), rgba(255,255,255,0.08) 44%, rgba(255,255,255,0.24));
        pointer-events: none;
    }
    .programme-orb svg {
        width: clamp(84px, 8.8vw, 124px);
        height: clamp(84px, 8.8vw, 124px);
        display: block;
        position: relative;
        z-index: 2;
        filter: drop-shadow(0 2px 3px rgba(255,255,255,0.3)) drop-shadow(0 4px 8px rgba(0,0,0,0.12));
    }
    .programme-orb-title {
        position: absolute;
        left: 50%;
        bottom: 13%;
        transform: translateX(-50%);
        width: 82%;
        text-align: center;
        z-index: 3;
        color: var(--uu-blue);
        font-size: clamp(0.86rem, 1.08vw, 1.08rem);
        font-weight: 700;
        line-height: 1.2;
        text-shadow: 0 1px 3px rgba(255,255,255,0.5);
    }
    @media (max-width: 900px) {
        .programme-orb {
            width: min(68vw, 260px);
        }
    }
    @media (max-width: 540px) {
        .programme-orb {
            width: min(78vw, 270px);
        }
    }

    /* ═══════════════════════════════  GLOBAL BUTTON SYSTEM  ═══════════════════════════════ */

    /* ── Base shared across all buttons ── */
    .stButton > button,
    .stDownloadButton > button {
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 0.87rem !important;
        padding: 0.48rem 1.1rem !important;
        letter-spacing: 0.01em !important;
        transition: background 0.18s ease, box-shadow 0.18s ease,
                    transform 0.18s ease, border-color 0.18s ease !important;
        cursor: pointer !important;
    }
    .stButton > button:active,
    .stDownloadButton > button:active {
        transform: translateY(0px) scale(0.98) !important;
        box-shadow: 0 1px 4px rgba(0,0,0,0.10) !important;
    }
    .stButton > button:disabled,
    .stDownloadButton > button:disabled {
        opacity: 0.36 !important;
        box-shadow: none !important;
        transform: none !important;
        cursor: not-allowed !important;
    }

    /* ── Secondary (default) — clean white card with lift ── */
    .stButton > button[data-testid="baseButton-secondary"],
    .stDownloadButton > button[data-testid="baseButton-secondary"] {
        background: #ffffff !important;
        border: 1.5px solid #d6d6d6 !important;
        color: var(--uu-blue) !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.07) !important;
    }
    .stButton > button[data-testid="baseButton-secondary"]:hover,
    .stDownloadButton > button[data-testid="baseButton-secondary"]:hover {
        background: #f7f8fa !important;
        border-color: #b0b8c4 !important;
        box-shadow: 0 5px 14px rgba(0,0,0,0.11) !important;
        transform: translateY(-2px) !important;
    }

    /* ── Primary — UU blue with deep shadow ── */
    .stButton > button[data-testid="baseButton-primary"],
    .stDownloadButton > button[data-testid="baseButton-primary"] {
        background: var(--uu-blue) !important;
        border: none !important;
        color: #ffffff !important;
        box-shadow: 0 4px 14px rgba(0,54,96,0.28) !important;
    }
    .stButton > button[data-testid="baseButton-primary"]:hover,
    .stDownloadButton > button[data-testid="baseButton-primary"]:hover {
        background: #004e8c !important;
        box-shadow: 0 7px 20px rgba(0,54,96,0.36) !important;
        transform: translateY(-2px) !important;
    }

    /* ── Back navigation buttons — match yellow UU brand ── */
    .st-key-back_to_home button,
    [class*="st-key-back_btn_"] button {
        background: var(--uu-yellow) !important;
        border: none !important;
        color: var(--uu-blue) !important;
        font-weight: 700 !important;
        box-shadow: 0 4px 14px rgba(255,205,0,0.35) !important;
        font-size: 0.9rem !important;
        padding: 0.54rem 1rem !important;
    }
    .st-key-back_to_home button:hover,
    [class*="st-key-back_btn_"] button:hover {
        background: #f0c200 !important;
        box-shadow: 0 7px 20px rgba(255,205,0,0.46) !important;
        transform: translateY(-2px) !important;
        border: none !important;
    }

    /* ── PDF viewer iframe — remove browser default border, add modern card look ── */
    iframe[data-testid="stCustomComponentV1"] {
        border: none !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 24px rgba(0,0,0,0.13) !important;
        overflow: hidden !important;
        display: block !important;
    }

    /* ── Details Download PDF button — yellow brand ── */
    .st-key-details_action_buttons .stDownloadButton > button {
        background: var(--uu-yellow) !important;
        border: none !important;
        color: var(--uu-blue) !important;
        font-weight: 700 !important;
        box-shadow: 0 4px 14px rgba(255,205,0,0.35) !important;
        font-size: 0.95rem !important;
        padding: 0.62rem 1.4rem !important;
        border-radius: 8px !important;
        letter-spacing: 0.01em !important;
        transition: background 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease !important;
    }
    .st-key-details_action_buttons .stDownloadButton > button:hover {
        background: #f0c200 !important;
        box-shadow: 0 7px 20px rgba(255,205,0,0.46) !important;
        transform: translateY(-2px) !important;
    }

    /* ── RGF Reset button — compact muted style ── */
    .st-key-rgf2_reset button {
        background: transparent !important;
        border: 1.5px solid #d0d0d0 !important;
        color: #666 !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        padding: 0.36rem 0.85rem !important;
        box-shadow: none !important;
    }
    .st-key-rgf2_reset button:hover {
        border-color: #999 !important;
        color: #333 !important;
        background: #f5f5f5 !important;
        transform: none !important;
        box-shadow: none !important;
    }

    /* ── Pagination buttons — yellow UU brand ── */
    .st-key-first_top button, .st-key-first_bottom button,
    .st-key-prev_top button,  .st-key-prev_bottom button,
    .st-key-next_top button,  .st-key-next_bottom button,
    .st-key-last_top button,  .st-key-last_bottom button {
        background: var(--uu-yellow) !important;
        border: none !important;
        color: var(--uu-blue) !important;
        font-weight: 700 !important;
        box-shadow: 0 4px 14px rgba(255,205,0,0.35) !important;
        font-size: 0.9rem !important;
        padding: 0.54rem 1rem !important;
        border-radius: 8px !important;
        transition: background 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease !important;
    }
    .st-key-first_top button:hover, .st-key-first_bottom button:hover,
    .st-key-prev_top button:hover,  .st-key-prev_bottom button:hover,
    .st-key-next_top button:hover,  .st-key-next_bottom button:hover,
    .st-key-last_top button:hover,  .st-key-last_bottom button:hover {
        background: #f0c200 !important;
        border: none !important;
        box-shadow: 0 7px 20px rgba(255,205,0,0.46) !important;
        transform: translateY(-2px) !important;
    }

    /* ── "View details" in Programme Analytics map ── */
    .st-key-pa_map_selected_view button {
        font-size: 0.83rem !important;
        padding: 0.36rem 0.85rem !important;
    }

    /* ── "Open Thesis" button ── */
    .st-key-details_nopdf_open button {
        background: var(--uu-blue) !important;
        border: none !important;
        color: #fff !important;
        box-shadow: 0 4px 14px rgba(0,54,96,0.28) !important;
        font-size: 0.9rem !important;
        padding: 0.52rem 1.2rem !important;
    }
    .st-key-details_nopdf_open button:hover {
        background: #004e8c !important;
        box-shadow: 0 7px 20px rgba(0,54,96,0.36) !important;
        transform: translateY(-2px) !important;
    }

    /* ── Programme analytics insight cards ── */
    .programme-insight-card {
        background: #ffffff;
        border: 1px solid #dcdcdc;
        border-radius: 12px;
        min-height: 172px;
        padding: 12px 12px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: space-between;
        box-sizing: border-box;
        overflow: hidden;
    }
    .programme-insight-title {
        width: 100%;
        text-align: center;
        font-size: 0.92rem;
        font-weight: 700;
        color: var(--uu-blue);
        line-height: 1.2;
        min-height: 2.4em;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .programme-insight-value {
        width: 100%;
        flex: 1;
        min-height: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        overflow: hidden;
    }
    .programme-insight-value-text {
        font-size: 1.25rem;
        font-weight: 700;
        color: #1f1f1f;
        line-height: 1.25;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .programme-insight-sdg-icon {
        width: 92px;
        height: 92px;
        object-fit: contain;
        display: block;
    }
    .programme-insight-flag {
        font-size: 5rem;
        line-height: 1;
        display: inline-block;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----- helper functions -----------------------------------------------------

def sdg_badge(sdg_text: str) -> str:
    """Return HTML for a coloured SDG badge, including optional icon."""

    number = None
    if sdg_text and sdg_text != "n/a":
        parts = sdg_text.strip().split()
        if parts:
            try:
                number = int(parts[0])
            except ValueError:
                number = None

    color_map = {
        "1": "#E5243B", "2": "#DDA63A", "3": "#4C9F38", "4": "#C5192D",
        "5": "#FF3A21", "6": "#26BDE2", "7": "#FCC30B", "8": "#A21942",
        "9": "#FD6925", "10": "#DD1367", "11": "#FD9D24", "12": "#BF8B2E",
        "13": "#3F7E44", "14": "#0A97D9", "15": "#56C02B", "16": "#00689D",
        "17": "#19486A",
    }
    color = color_map.get(str(number), "#888888")

    icon_html = ""
    if number is not None and 1 <= number <= 17:
        # Load local icon, resize to 24×24 thumbnail so base64 stays tiny (~0.5 KB)
        local_file = os.path.join(PROGRAM_DIR, "sdg_icons", f"Goal-{number:02d}.png")
        icon_b64 = ""
        if os.path.exists(local_file):
            try:
                from PIL import Image as _PILIcon
                import io as _io_icon, base64 as _b64_icon
                with _PILIcon.open(local_file) as _im:
                    _im = _im.convert("RGBA")
                    _im = _im.resize((24, 24), _PILIcon.LANCZOS)
                    _buf = _io_icon.BytesIO()
                    _im.save(_buf, format="PNG", optimize=True)
                    icon_b64 = _b64_icon.b64encode(_buf.getvalue()).decode()
            except Exception:
                icon_b64 = _load_image_b64(local_file)
        if icon_b64:
            icon_html = (
                f"<img src=\"data:image/png;base64,{icon_b64}\" width=24 "
                "style='vertical-align:middle;margin-right:4px;'/>"
            )
        else:
            # fall back to the online repository
            url = f"https://raw.githubusercontent.com/UNSDG/SDG-Icons/master/Icons/Goal-{number:02d}.png"
            icon_html = (
                f"<img src=\"{url}\" width=24 "
                "style='vertical-align:middle;margin-right:4px;'/>"
            )

    label_text = sdg_text.replace(str(number), '').strip() if number is not None else sdg_text

    return (
        f"<div class='sdg-badge' style='background:{color};padding:4px 8px;border-radius:5px;"
        f"color:white;display:inline-flex;'>"
        f"{icon_html}<span class='sdg-label'>{label_text}</span>"  # drop leading number for brevity
        f"</div>"
    )


def _has_value(value) -> bool:
    if pd.isna(value):
        return False
    text = str(value).strip().lower()
    return text not in ("", "n/a", "na", "nan")


def _normalize_name_key(text: str) -> str:
    import re
    import unicodedata

    cleaned = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    cleaned = cleaned.lower().strip()
    cleaned = re.sub(r"[^a-z\s\-]", "", cleaned)
    cleaned = cleaned.replace("-", " ")
    cleaned = " ".join(cleaned.split())
    return cleaned.replace(" ", "")


def _author_surname_keys(author_text: str) -> set[str]:
    """Extract normalized surname-like keys from an author field."""
    import re

    particles = {"van", "de", "den", "der", "ter", "ten", "von", "da", "di", "del", "della", "du", "la", "le"}
    raw_authors = [a.strip() for a in re.split(r";|\s+and\s+|&|/", str(author_text)) if a.strip()]
    keys: set[str] = set()

    for raw in raw_authors:
        if "," in raw:
            surname = raw.split(",", 1)[0].strip()
            if surname:
                keys.add(_normalize_name_key(surname))
            continue

        parts = [p for p in raw.replace("-", " ").split() if p]
        if not parts:
            continue

        last = parts[-1]
        keys.add(_normalize_name_key(last))

        if len(parts) >= 2:
            second_last = parts[-2].lower()
            if second_last in particles:
                keys.add(_normalize_name_key(f"{second_last} {last}"))

        if len(parts) >= 3:
            keys.add(_normalize_name_key(" ".join(parts[-2:])))

    return {k for k in keys if k}


def _author_person_name_parts(author_text: str) -> list[tuple[set[str], set[str]]]:
    """Return per-person (surname_keys, given_name_keys) extracted from an author field."""
    import re

    particles = {"van", "de", "den", "der", "ter", "ten", "von", "da", "di", "del", "della", "du", "la", "le"}
    people = [a.strip() for a in re.split(r";|\s+and\s+|&|/", str(author_text)) if a.strip()]
    result: list[tuple[set[str], set[str]]] = []

    for person in people:
        surname_keys: set[str] = set()
        given_keys: set[str] = set()

        if "," in person:
            surname_part, given_part = person.split(",", 1)
            surname_norm = _normalize_name_key(surname_part)
            if surname_norm:
                surname_keys.add(surname_norm)
            for token in given_part.replace("-", " ").split():
                token_norm = _normalize_name_key(token)
                if token_norm and token_norm not in particles:
                    given_keys.add(token_norm)
        else:
            parts = [p for p in person.replace("-", " ").split() if p]
            if not parts:
                continue

            first_norm = _normalize_name_key(parts[0])
            if first_norm and first_norm not in particles:
                given_keys.add(first_norm)

            last = parts[-1]
            surname_keys.add(_normalize_name_key(last))

            if len(parts) >= 2:
                second_last = parts[-2].lower()
                if second_last in particles:
                    surname_keys.add(_normalize_name_key(f"{second_last} {last}"))
                    given_source = parts[:-2]
                else:
                    given_source = parts[:-1]
            else:
                given_source = []

            for token in given_source:
                token_norm = _normalize_name_key(token)
                if token_norm and token_norm not in particles:
                    given_keys.add(token_norm)

            # Capture two-part surnames where present (e.g., Bocard Colome)
            if len(parts) >= 3:
                surname_keys.add(_normalize_name_key(" ".join(parts[-2:])))

        surname_keys = {k for k in surname_keys if k}
        given_keys = {k for k in given_keys if k}
        if surname_keys:
            result.append((surname_keys, given_keys))

    return result


def _parse_featured_name(name: str) -> tuple[str, set[str]]:
    """Parse coordinator-provided name into (surname_key, given_tokens)."""
    parts = [p.strip() for p in str(name).split(",", 1)]
    if len(parts) == 2:
        surname_raw, given_raw = parts[0], parts[1]
    else:
        tokens = str(name).split()
        surname_raw = tokens[-1] if tokens else ""
        given_raw = " ".join(tokens[:-1])

    surname_key = _normalize_name_key(surname_raw)
    given_tokens = {
        _normalize_name_key(tok)
        for tok in given_raw.replace("-", " ").split()
        if _normalize_name_key(tok)
    }
    return surname_key, given_tokens


def _featured_badge_html(is_featured: bool) -> str:
    return "<span class='featured-badge'>★ Featured</span>" if is_featured else ""


# Google Drive root folder — used as fallback when PDFs are not on disk (e.g. Community Cloud)
_DRIVE_ROOT_FALLBACK = "https://drive.google.com/drive/folders/1Gy0Ez7MtbexaV6y8R5JRMx-lj9o-cCB4"


@st.cache_data(show_spinner=False, max_entries=12)
def _load_pdf_bytes_cached(pdf_path: str) -> bytes | None:
    """Cache PDF bytes by path — used only for the download button."""
    try:
        with open(pdf_path, "rb") as _f:
            return _f.read()
    except (OSError, IOError):
        return None


def _pdf_iframe_html(static_url: str, height: int = 1100) -> str:
    """Inline PDF.js viewer: lazy rendering, HiDPI canvas, auto-fit-to-width, page nav."""
    tb = 44
    vh = height - tb
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0;padding:0;}}
html,body{{width:100%;height:{height}px;overflow:hidden;font-family:Inter,system-ui,sans-serif;}}
#tb{{display:flex;align-items:center;gap:5px;padding:0 12px;height:{tb}px;
     background:#1a2e3d;color:#fff;flex-shrink:0;border-bottom:1px solid rgba(255,255,255,.08);}}
#sw{{display:flex;align-items:center;gap:4px;background:rgba(255,255,255,.12);
     border-radius:6px;padding:3px 9px;min-width:160px;flex:1;max-width:260px;}}
#si{{background:transparent;border:none;outline:none;color:#fff;font-size:13px;flex:1;width:0;}}
#si::placeholder{{color:rgba(255,255,255,.42);}}
#sc{{font-size:11px;color:rgba(255,255,255,.52);white-space:nowrap;}}
.tb2{{background:rgba(255,255,255,.11);border:none;color:#fff;border-radius:4px;
      padding:3px 8px;cursor:pointer;font-size:12px;line-height:1.5;}}
.tb2:hover{{background:rgba(255,255,255,.22);}}
.sep{{width:1px;height:20px;background:rgba(255,255,255,.18);flex-shrink:0;margin:0 2px;}}
#pi{{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.2);color:#fff;
     border-radius:4px;padding:2px 5px;font-size:12px;width:36px;text-align:center;outline:none;}}
#pt{{font-size:12px;color:rgba(255,255,255,.55);white-space:nowrap;}}
#zs{{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.2);color:#fff;
     border-radius:4px;padding:3px 5px;font-size:12px;cursor:pointer;outline:none;}}
#zs option{{background:#003660;}}
#viewer{{height:{vh}px;overflow-y:scroll;overflow-x:auto;display:flex;flex-direction:column;
         align-items:center;gap:10px;padding:16px 12px;background:#525659;}}
.pg{{position:relative;background:#fff;flex-shrink:0;
     box-shadow:0 2px 14px rgba(0,0,0,.38);border-radius:1px;}}
.pg canvas{{display:block;}}
.tl{{position:absolute;top:0;left:0;overflow:hidden;line-height:1;pointer-events:auto;}}
.tl span{{color:transparent;position:absolute;white-space:pre;transform-origin:0 0;cursor:text;}}
.tl span::selection{{background:rgba(0,110,255,.28);}}
.tl .hl{{background:rgba(255,210,0,.55)!important;border-radius:2px;}}
.tl .hl.cur{{background:rgba(255,140,0,.78)!important;}}
.skel{{background:#636669;border-radius:1px;
       background:linear-gradient(90deg,#5a5d60 25%,#6d7073 50%,#5a5d60 75%);
       background-size:400% 100%;animation:sh 1.5s ease infinite;}}
@keyframes sh{{0%{{background-position:100% 0}}100%{{background-position:-100% 0}}}}
#msg{{color:rgba(255,255,255,.7);padding:3rem;font-size:14px;text-align:center;}}
</style></head><body>
<div id="tb">
  <div id="sw">
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,.5)" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
    <input id="si" placeholder="Search (Ctrl+F)" autocomplete="off" spellcheck="false"/>
    <span id="sc"></span>
  </div>
  <button class="tb2" onclick="findPrev()" title="Prev match">↑</button>
  <button class="tb2" onclick="findNext()" title="Next match">↓</button>
  <div class="sep"></div>
  <button class="tb2" id="btnPrev" onclick="stepPage(-1)">‹</button>
  <input id="pi" type="text" value="1" onkeydown="pageKey(event)" onblur="pageBlur()"/>
  <span id="pt">/ –</span>
  <button class="tb2" id="btnNext" onclick="stepPage(1)">›</button>
  <div class="sep"></div>
  <select id="zs" onchange="applyZoom(this.value)">
    <option value="auto" selected>Fit width</option>
    <option value="0.75">75 %</option>
    <option value="1.0">100 %</option>
    <option value="1.25">125 %</option>
    <option value="1.5">150 %</option>
    <option value="2.0">200 %</option>
  </select>
</div>
<div id="viewer"><div id="msg">Loading…</div></div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
<script>
pdfjsLib.GlobalWorkerOptions.workerSrc =
  'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

var origin = (window.parent && window.parent.location)
               ? window.parent.location.origin : window.location.origin;
var rawUrl  = '{static_url}';
var pdfUrl  = (rawUrl.startsWith('data:') || rawUrl.startsWith('http')) ? rawUrl : (origin + rawUrl);
var DPR     = window.devicePixelRatio || 1;

var doc = null, pgEls = [], rendered = {{}};
var curScale = 1.0, zoomVal = 'auto';
var matches = [], mIdx = -1;
var viewer = document.getElementById('viewer');
var si = document.getElementById('si'), scEl = document.getElementById('sc');
var piEl = document.getElementById('pi'), ptEl = document.getElementById('pt');

// ── Load ──────────────────────────────────────────────────────────────────
pdfjsLib.getDocument({{url: pdfUrl, isEvalSupported: false}}).promise
  .then(function(pdf) {{
    doc = pdf;
    var msg = document.getElementById('msg');
    if (msg) msg.remove();
    ptEl.textContent = '/ ' + pdf.numPages;

    return pdf.getPage(1).then(function(p1) {{
      var vw  = viewer.clientWidth - 24;
      var nat = p1.getViewport({{scale: 1}});
      curScale = vw / nat.width;

      for (var i = 1; i <= pdf.numPages; i++) {{
        var ph = document.createElement('div');
        ph.className = 'pg skel';
        ph.dataset.n = i;
        ph.style.width  = Math.round(nat.width  * curScale) + 'px';
        ph.style.height = Math.round(nat.height * curScale) + 'px';
        pgEls[i-1] = ph;
        viewer.appendChild(ph);
      }}
      setupObserver();
    }});
  }})
  .catch(function(e) {{
    var el = document.getElementById('msg') || viewer;
    el.textContent = 'Could not load PDF: ' + (e.message || e);
  }});

// ── Intersection observer (lazy render) ───────────────────────────────────
function setupObserver() {{
  var obs = new IntersectionObserver(function(entries) {{
    entries.forEach(function(e) {{
      if (e.isIntersecting) {{
        var n = parseInt(e.target.dataset.n, 10);
        if (!rendered[n]) renderPage(n);
      }}
    }});
  }}, {{root: viewer, rootMargin: '300px 0px'}});
  pgEls.forEach(function(el) {{ obs.observe(el); }});
}}

// ── Render one page ───────────────────────────────────────────────────────
function renderPage(n) {{
  rendered[n] = true;
  doc.getPage(n).then(function(page) {{
    var vp   = page.getViewport({{scale: curScale}});
    var wrap = pgEls[n-1];
    wrap.classList.remove('skel');
    wrap.style.cssText =
      'position:relative;background:#fff;flex-shrink:0;border-radius:1px;' +
      'box-shadow:0 2px 14px rgba(0,0,0,.38);' +
      'width:' + vp.width + 'px;height:' + vp.height + 'px;';
    wrap.innerHTML = '';

    var cv = document.createElement('canvas');
    cv.width  = Math.round(vp.width  * DPR);
    cv.height = Math.round(vp.height * DPR);
    cv.style.width  = vp.width  + 'px';
    cv.style.height = vp.height + 'px';
    wrap.appendChild(cv);
    var ctx = cv.getContext('2d');
    ctx.scale(DPR, DPR);

    return page.render({{canvasContext: ctx, viewport: vp}}).promise
      .then(function() {{ return page.getTextContent(); }})
      .then(function(tc) {{
        var tl = document.createElement('div');
        tl.className = 'tl';
        tl.style.width  = vp.width  + 'px';
        tl.style.height = vp.height + 'px';
        wrap.appendChild(tl);
        if (typeof pdfjsLib.renderTextLayer === 'function') {{
          var task = pdfjsLib.renderTextLayer({{
            textContentSource: tc, container: tl, viewport: vp, textDivs: []
          }});
          var p = (task && task.promise) ? task.promise
                : (task instanceof Promise ? task : Promise.resolve());
          p.catch(function() {{}});
        }}
      }});
  }});
}}

// ── Zoom ──────────────────────────────────────────────────────────────────
function applyZoom(v) {{
  zoomVal = v;
  if (!doc) return;
  doc.getPage(1).then(function(p1) {{
    var nat = p1.getViewport({{scale: 1}});
    curScale = (v === 'auto')
      ? (viewer.clientWidth - 24) / nat.width
      : parseFloat(v);
    rendered = {{}};
    pgEls    = [];
    viewer.innerHTML = '';
    for (var i = 1; i <= doc.numPages; i++) {{
      var ph = document.createElement('div');
      ph.className = 'pg skel';
      ph.dataset.n = i;
      ph.style.width  = Math.round(nat.width  * curScale) + 'px';
      ph.style.height = Math.round(nat.height * curScale) + 'px';
      pgEls[i-1] = ph;
      viewer.appendChild(ph);
    }}
    setupObserver();
  }});
}}

// ── Page nav ──────────────────────────────────────────────────────────────
viewer.addEventListener('scroll', function() {{
  if (!pgEls.length) return;
  var mid = viewer.scrollTop + viewer.clientHeight * 0.3;
  for (var i = pgEls.length - 1; i >= 0; i--) {{
    if (pgEls[i] && pgEls[i].offsetTop <= mid) {{
      piEl.value = i + 1; break;
    }}
  }}
}}, {{passive: true}});

function stepPage(d) {{
  var n = parseInt(piEl.value, 10) + d;
  if (doc && n >= 1 && n <= doc.numPages) gotoPage(n);
}}
function gotoPage(n) {{
  if (!pgEls[n-1]) return;
  pgEls[n-1].scrollIntoView({{behavior: 'smooth'}});
  piEl.value = n;
}}
function pageKey(e) {{
  if (e.key === 'Enter') {{
    var n = parseInt(piEl.value, 10);
    if (doc && n >= 1 && n <= doc.numPages) gotoPage(n);
    else piEl.value = piEl.dataset.last || '1';
  }}
}}
function pageBlur() {{
  var n = parseInt(piEl.value, 10);
  if (!doc || n < 1 || n > doc.numPages) piEl.value = piEl.dataset.last || '1';
  else piEl.dataset.last = n;
}}

// ── Search ────────────────────────────────────────────────────────────────
document.addEventListener('keydown', function(e) {{
  if ((e.ctrlKey||e.metaKey) && e.key === 'f') {{ e.preventDefault(); si.focus(); si.select(); }}
}});
si.addEventListener('keydown', function(e) {{
  if (e.key === 'Enter') {{ e.shiftKey ? findPrev() : findNext(); e.preventDefault(); }}
  if (e.key === 'Escape') {{ si.value = ''; doSearch(''); si.blur(); }}
}});
si.addEventListener('input', function() {{ doSearch(this.value); }});

function doSearch(q) {{
  viewer.querySelectorAll('.hl,.cur').forEach(function(s) {{ s.classList.remove('hl','cur'); }});
  matches = []; mIdx = -1; scEl.textContent = '';
  if (!q || q.length < 2) return;
  var ql = q.toLowerCase();
  viewer.querySelectorAll('.tl span').forEach(function(s) {{
    if (s.textContent && s.textContent.toLowerCase().includes(ql)) {{
      s.classList.add('hl'); matches.push(s);
    }}
  }});
  if (matches.length) {{ mIdx = 0; selectMatch(0); }}
  else scEl.textContent = 'No match';
}}
function selectMatch(i) {{
  viewer.querySelectorAll('.cur').forEach(function(s) {{ s.classList.remove('cur'); }});
  if (!matches[i]) return;
  matches[i].classList.add('cur');
  matches[i].scrollIntoView({{behavior: 'smooth', block: 'center'}});
  scEl.textContent = (i+1) + ' / ' + matches.length;
}}
function findNext() {{ if (!matches.length) return; mIdx=(mIdx+1)%matches.length; selectMatch(mIdx); }}
function findPrev() {{ if (!matches.length) return; mIdx=(mIdx-1+matches.length)%matches.length; selectMatch(mIdx); }}
</script></body></html>"""


def _get_program_dir_for_row(row) -> str:
    """Return the on-disk programme folder for a single thesis row.

    In all-programmes mode the merged dataframe carries a `_program_key`
    column so per-row assets (PDFs, covers) resolve to the correct
    programme. Falls back to the module-level PROGRAM_DIR when the column
    is absent (single-programme mode).
    """
    try:
        key = str(row.get("_program_key", "") or "").strip()
    except Exception:
        key = ""
    if key and key in _PROGRAMME_FOLDER_MAP:
        return os.path.abspath(
            os.path.join(BASE_DIR, "..", "programs", _PROGRAMME_FOLDER_MAP[key])
        )
    return PROGRAM_DIR


def resolve_cover_and_pdf_paths(row) -> tuple[str, str]:
    pdf_name = str(row.get("Thesis_PDF", "")).strip()
    _row_program_dir = _get_program_dir_for_row(row)
    pdf_path = ""
    if _has_value(pdf_name):
        pdf_path = os.path.join(_row_program_dir, "pdfs", pdf_name)

    cover_candidates = []

    cover_name = str(row.get("Cover_Image", "")).strip()
    if _has_value(cover_name):
        cover_candidates.append(cover_name)

    if _has_value(pdf_name):
        pdf_stem = os.path.splitext(os.path.basename(pdf_name))[0]
        cover_candidates.extend(
            [
                f"{pdf_stem}.png",
                f"{pdf_stem.lower()}.png",
                f"{pdf_stem.replace(' ', '_')}.png",
                f"{pdf_stem.replace(' ', '_').lower()}.png",
            ]
        )

    seen = set()
    for candidate in cover_candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        candidate_path = os.path.join(_row_program_dir, "covers", candidate)
        if os.path.exists(candidate_path):
            return candidate_path, pdf_path

    return "", pdf_path


def render_cover_html(cover_path: str, pdf_path: str = "", featured: bool = False) -> str:
    """Render a fixed-size cover block so all cards align, even without an image."""
    badge = "<span class='thesis-cover-badge'>&#9733; Featured</span>" if featured else ""
    cover_b64 = _load_image_b64(cover_path)
    if cover_b64:
        return (
            "<div class='thesis-cover'>"
            f"<img src='data:image/png;base64,{cover_b64}' class='thesis-cover-image' alt='Thesis cover' />"
            + badge
            + "</div>"
        )

    if pdf_path and os.path.exists(pdf_path):
        return f"<div class='thesis-cover'><span class='thesis-cover-placeholder'>PDF cover available</span>{badge}</div>"

    return f"<div class='thesis-cover'><span class='thesis-cover-placeholder'>No cover</span>{badge}</div>"


def find_row_by_pdf_name(dataframe, pdf_name: str):
    for _, row in dataframe.iterrows():
        row_pdf = str(row.get("Thesis_PDF", ""))
        if pd.notna(row_pdf) and row_pdf not in ("", "n/a", "nan") and row_pdf == pdf_name:
            return row
    return None


def render_keyword_pills(raw_keywords):
    if pd.notna(raw_keywords) and str(raw_keywords).strip().lower() != "n/a":
        keyword_items = [k.strip() for k in str(raw_keywords).split(",") if k.strip() and k.strip().lower() != "n/a"]
        if keyword_items:
            keywords_html = "".join([f"<span class='keyword-pill'>{k}</span>" for k in keyword_items])
            st.markdown(f"<div class='keywords-wrap'>{keywords_html}</div>", unsafe_allow_html=True)
            return
    st.write("n/a")


def _detail_field(label: str, value) -> None:
    """Render a single label + value pair in detail view."""
    st.markdown(f"<div class='detail-label'>{label}</div>", unsafe_allow_html=True)
    text = str(value).strip() if _has_value(value) else "n/a"
    st.markdown(f"<div class='detail-field-value'>{text}</div>", unsafe_allow_html=True)


def render_structured_details_sections(row):
    import html as _html

    def _v(val) -> str:
        safe = _html.escape(str(val).strip()) if _has_value(val) else ""
        return f"<span class='ds-val'>{safe}</span>" if safe else "<span class='ds-na'>—</span>"

    rq           = row.get("Main Research Question", "")
    abstract     = row.get("Abstract/Summary", "")
    keywords     = row.get("Keywords", "")
    mtype        = row.get("Methodology Type", "")
    methods      = row.get("Specific Methods", "")
    theories     = row.get("Theories", "")
    geo          = row.get("Geographical scope", "")
    sdg_raw      = str(row.get("SDG", "")).strip()
    scale        = row.get("Scale", row.get("Research Scale", row.get("Research scale", "")))
    master_track = row.get("Master Track", "")
    supervisor   = row.get("Supervisor", "")
    second_rdr   = row.get("Second reader", row.get("Second Reader", ""))
    intern_org   = row.get("Internship Organization", "")
    intern_str   = str(intern_org).strip() if _has_value(intern_org) else ""
    orgs_studied = row.get("Organizations Studied", "")

    # Research question — escape to prevent broken HTML from < > & in content
    rq_html = (
        f"<div class='ds-rq'>{_html.escape(str(rq).strip())}</div>" if _has_value(rq)
        else "<span class='ds-na'>—</span>"
    )

    # Abstract collapsible — escape content so < > & don't break structure
    if _has_value(abstract):
        abs_html = (
            f"<details class='ds-abstract-wrap'>"
            f"<summary class='ds-abstract-toggle'>Abstract / Summary</summary>"
            f"<div class='ds-abstract-body'>{_html.escape(str(abstract).strip())}</div>"
            f"</details>"
        )
    else:
        abs_html = "<div class='ds-field' style='margin-bottom:10px'><span class='ds-lbl'>Summary</span><span class='ds-na'>—</span></div>"

    # Keywords
    kw_html = "<span class='ds-na'>—</span>"
    if _has_value(keywords):
        kws = [k.strip() for k in str(keywords).split(",") if k.strip() and k.strip().lower() != "n/a"]
        if kws:
            kw_html = "".join(f"<span class='ds-kw'>{_html.escape(k)}</span>" for k in kws)

    # SDG badge
    sdg_html = sdg_badge(sdg_raw) if _has_value(sdg_raw) else "<span class='ds-na'>—</span>"

    # Internship org logo
    if intern_str:
        _logos_dir = os.path.join(BASE_DIR, "company logos")
        logo_b64 = _load_org_logo_b64(_logos_dir, intern_str)
        intern_safe = _html.escape(intern_str)
        intern_html = (
            f"<div class='ds-org-row'><img src='{logo_b64}' class='ds-org-logo' alt='{intern_safe}'/>"
            f"<span class='ds-val'>{intern_safe}</span></div>"
            if logo_b64
            else f"<span class='ds-val'>{intern_safe}</span>"
        )
    else:
        intern_html = "<span class='ds-na'>—</span>"

    # Master Track row (programme-specific)
    master_html = (
        f"<div class='ds-field'><span class='ds-lbl'>Master Track</span>{_v(master_track)}</div>"
        f"<div class='ds-divider'></div>"
        if _has_value(master_track) else ""
    )

    # Supervisor / Second-reader clickable links (with optional photo)
    def _sup_link_html(name_str) -> str:
        if not _has_value(name_str):
            return "<span class='ds-na'>\u2014</span>"
        _enc_p = urllib.parse.quote(PROGRAM, safe='')
        _names = [n.strip() for n in str(name_str).split(',') if n.strip() and n.strip().lower() not in ('n/a', 'nan')]
        if not _names:
            return "<span class='ds-na'>\u2014</span>"
        _parts = []
        for _nm in _names:
            _enc_nm = urllib.parse.quote(_nm, safe='')
            _safe_nm = _html.escape(_nm)
            _b64 = _sup_photo_b64(_nm)
            _photo_tag = (
                f"<img src='data:image/jpeg;base64,{_b64}' class='ds-sup-photo' alt='{_safe_nm}'/>"
                if _b64 else ""
            )
            _parts.append(
                f"<span class='ds-sup-wrap'>{_photo_tag}"
                f"<a href='?program={_enc_p}&sup_selected={_enc_nm}' class='ds-sup-link' target='_self'>{_safe_nm}</a>"
                f"</span>"
            )
        return "<span class='ds-val'>" + "".join(_parts) + "</span>"

    st.markdown(f"""
<div class="ds-cards-wrap">

  <div class="ds-card">
    <div class="ds-title">Research Overview</div>
    <div class="ds-field">
      <span class="ds-lbl">Main Research Question</span>
      {rq_html}
    </div>
    {abs_html}
    <div class="ds-field">
      <span class="ds-lbl">Keywords</span>
      <div class="ds-pill-wrap">{kw_html}</div>
    </div>
  </div>

  <div class="ds-card">
    <div class="ds-title">Methodology &amp; Theory</div>
    <div class="ds-grid-3">
      <div class="ds-field"><span class="ds-lbl">Methodology Type</span>{_v(mtype)}</div>
      <div class="ds-field"><span class="ds-lbl">Specific Methods</span>{_v(methods)}</div>
      <div class="ds-field"><span class="ds-lbl">Theories</span>{_v(theories)}</div>
    </div>
  </div>

  <div class="ds-card">
    <div class="ds-title">Research Context</div>
    <div class="ds-grid">
      <div class="ds-field"><span class="ds-lbl">Geographical Scope</span>{_v(geo)}</div>
      <div class="ds-field"><span class="ds-lbl">Research Scale</span>{_v(scale)}</div>
    </div>
    <div class="ds-divider"></div>
    <div class="ds-field">
      <span class="ds-lbl">SDG</span>
      <div style="margin-top:5px">{sdg_html}</div>
    </div>
  </div>

  <div class="ds-row-pair">
    <div class="ds-card">
      <div class="ds-title">Academic Context</div>
      {master_html}<div class="ds-field"><span class="ds-lbl">Supervisor</span>{_sup_link_html(supervisor)}</div>
      <div class="ds-divider"></div>
      <div class="ds-field"><span class="ds-lbl">Second Reader</span>{_sup_link_html(second_rdr)}</div>
    </div>
    <div class="ds-card">
      <div class="ds-title">Partnerships</div>
      <div class="ds-field">
        <span class="ds-lbl">Internship Organization</span>
        {intern_html}
      </div>
      <div class="ds-divider"></div>
      <div class="ds-field"><span class="ds-lbl">Organizations Studied</span>{_v(orgs_studied)}</div>
    </div>
  </div>

</div>
""", unsafe_allow_html=True)


def _normalized_set(value: str) -> set[str]:
    if pd.isna(value):
        return set()
    parts = [item.strip().lower() for item in str(value).split(",")]
    return {item for item in parts if item and item != "n/a"}


def _normalized_value(value: str) -> str:
    if pd.isna(value):
        return ""
    normalized = str(value).strip().lower()
    if normalized in ("", "n/a", "nan"):
        return ""
    return normalized


def compute_similarity_score(row_a, row_b):
    score = 0.0

    if _normalized_value(row_a.get("SDG", "")) == _normalized_value(row_b.get("SDG", "")) and _normalized_value(row_a.get("SDG", "")):
        score += 3
    if _normalized_value(row_a.get("Methodology Type", "")) == _normalized_value(row_b.get("Methodology Type", "")) and _normalized_value(row_a.get("Methodology Type", "")):
        score += 2
    if _normalized_value(row_a.get("Main sector", "")) == _normalized_value(row_b.get("Main sector", "")) and _normalized_value(row_a.get("Main sector", "")):
        score += 1

    keywords_a = _normalized_set(row_a.get("Keywords", ""))
    keywords_b = _normalized_set(row_b.get("Keywords", ""))
    score += 1.5 * len(keywords_a.intersection(keywords_b))

    theories_a = _normalized_set(row_a.get("Theories", ""))
    theories_b = _normalized_set(row_b.get("Theories", ""))
    score += 1.5 * len(theories_a.intersection(theories_b))

    if _normalized_value(row_a.get("Organizations Studied", "")) == _normalized_value(row_b.get("Organizations Studied", "")) and _normalized_value(row_a.get("Organizations Studied", "")):
        score += 2
    if _normalized_value(row_a.get("Internship Organization", "")) == _normalized_value(row_b.get("Internship Organization", "")) and _normalized_value(row_a.get("Internship Organization", "")):
        score += 2

    return score


def get_related_theses(df, current_row, top_n=4):
    related = []
    current_pdf = _normalized_value(current_row.get("Thesis_PDF", ""))

    for idx, candidate in df.iterrows():
        candidate_pdf = _normalized_value(candidate.get("Thesis_PDF", ""))
        if idx == current_row.name:
            continue
        if current_pdf and candidate_pdf and current_pdf == candidate_pdf:
            continue

        sim_score = compute_similarity_score(current_row, candidate)
        if sim_score > 0:
            related.append((sim_score, candidate))

    related.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in related[:top_n]]


def render_related_thesis_cards(current_row, key_prefix: str):
    st.markdown("### Similar Theses")
    related_rows = get_related_theses(df, current_row, top_n=4)
    if related_rows:
        related_cols = st.columns(4)
        for idx, related_row in enumerate(related_rows):
            with related_cols[idx % 4]:
                with st.container():
                    related_cover_path, related_pdf_path = resolve_cover_and_pdf_paths(related_row)
                    related_pdf = str(related_row.get("Thesis_PDF", "n/a"))
                    related_details_key = related_pdf.replace('.pdf', '') if related_pdf.endswith('.pdf') else ""
                    related_featured_html = _featured_badge_html(bool(related_row.get("Featured", False)))
                    _related_is_featured = bool(related_row.get("Featured", False))

                    if related_details_key:
                        card_link = (
                            f"?program={urllib.parse.quote(PROGRAM, safe='')}&"
                            f"details={urllib.parse.quote(related_details_key, safe='')}"
                        )
                        card_html = (
                            f'<a href="{card_link}" class="thesis-card-link" target="_self">'
                            '<div class="thesis-card">'
                            + render_cover_html(related_cover_path, related_pdf_path, featured=_related_is_featured)
                            + f"<div class='thesis-title'>{related_row['Title']}</div>"
                            + f"<div class='thesis-meta'>{related_row['Author(s)']} &#8226; {related_row['Year']}</div>"
                            + '</div></a>'
                        )
                    else:
                        card_html = (
                            '<div class="thesis-card">'
                            + render_cover_html(related_cover_path, related_pdf_path, featured=_related_is_featured)
                            + f"<div class='thesis-title'>{related_row['Title']}</div>"
                            + f"<div class='thesis-meta'>{related_row['Author(s)']} &#8226; {related_row['Year']}</div>"
                            + '</div>'
                        )
                    st.markdown(card_html, unsafe_allow_html=True)
    else:
        st.info("No related theses found.")


# ----- programme definitions ------------------------------------------------

PROGRAMME_DISPLAY_NAMES = {
    "all": "All Programmes",
    "sbi": "Sustainable Business and Innovation",
    "energy_science": "Energy Science",
    "sustainable_development": "Sustainable Development",
    "innovation_sciences": "Innovation Sciences",
    "water_management": "Water Management for Climate Adaptation",
}

# Display names without the "all" meta-entry — used when iterating only over
# real, single programmes (homepage orbs, programme filter options, etc.).
PROGRAMME_DISPLAY_NAMES_SINGLE = {
    k: v for k, v in PROGRAMME_DISPLAY_NAMES.items() if k != _ALL_PROGRAM_KEY
}

# Short, card-friendly programme labels (used on cards in all-mode and
# anywhere we need a compact source indicator).
PROGRAMME_SHORT_NAMES = {
    "sbi":                     "SBI",
    "energy_science":          "Energy Science",
    "sustainable_development": "Sustainable Dev.",
    "innovation_sciences":     "Innovation Sci.",
    "water_management":        "Water Mgmt.",
}

# Per-programme icon metadata (Heroicons outline, colour-coded)
_PROG_ICON_PATH = {
    # Building Office 2 — organisations driving sustainability
    "sbi": (
        "#1a5276", "#e8f4fd",
        "M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21"
        "M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75"
        "M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21"
        "M3 3h12m-.75 4.5H21m-3.75 3.75h.008v.008h-.008v-.008Z"
        "m0 3h.008v.008h-.008v-.008Zm0 3h.008v.008h-.008v-.008Z"
    ),
    # Bolt — energy transition
    "energy_science": (
        "#c45c00", "#fff3e0",
        "m3.75 13.5 10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75Z"
    ),
    # Globe Alt — global sustainability, earth systems
    "sustainable_development": (
        "#2e7d32", "#edf7ee",
        "M12 21a9.004 9.004 0 0 0 8.716-6.747M12 21a9.004 9.004 0 0 1-8.716-6.747"
        "M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3"
        "m0 0a8.997 8.997 0 0 1 7.843 4.582M12 3a8.997 8.997 0 0 0-7.843 4.582"
        "m15.686 0A11.953 11.953 0 0 1 12 10.5c-2.998 0-5.74-1.1-7.843-2.918"
        "m15.686 0A8.959 8.959 0 0 1 21 12c0 .778-.099 1.533-.284 2.253"
        "m0 0A17.919 17.919 0 0 1 12 16.5c-3.162 0-6.133-.815-8.716-2.247"
        "m0 0A9.015 9.015 0 0 1 3 12c0-1.605.42-3.113 1.157-4.418"
    ),
    # Light Bulb — ideas to innovation
    "innovation_sciences": (
        "#5c3d9e", "#f0eafa",
        "M12 18v-5.25m0 0a6.01 6.01 0 0 0 1.5-.189m-1.5.189a6.01 6.01 0 0 1-1.5-.189"
        "m3.75 7.478a12.06 12.06 0 0 1-4.5 0m3.75 2.383a14.406 14.406 0 0 1-3 0"
        "M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 1 0-7.517 0"
        "c.85.493 1.509 1.333 1.509 2.316V18"
    ),
    # Water droplet — climate-adaptive water management
    "water_management": (
        "#0077b6", "#e0f2fe",
        "M12 2c-5.33 4.55-8 8.48-8 11.8 0 4.98 3.8 8.2 8 8.2s8-3.22 8-8.2"
        "c0-3.32-2.67-7.25-8-11.8z"
    ),
}


def _programme_icon_html(key: str, title: str) -> str:
    """Return a large circular icon button with the programme title overlaid."""
    meta = _PROG_ICON_PATH.get(key)
    if not meta:
        return (
            "<div class='programme-orb' style='--orb-bg:#f0f0f0;'>"
            "<span style='font-size:3rem;position:relative;z-index:2;'>&#127891;</span>"
            f"<span class='programme-orb-title'>{title}</span>"
            "</div>"
        )
    color, bg, path_d = meta
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"'
        f' stroke-width="1.6" stroke="{color}" style="display:block;">'
        f'<path stroke-linecap="round" stroke-linejoin="round" d="{path_d}"/>'
        f'</svg>'
    )
    return (
        f"<div class='programme-orb' style='--orb-bg:{bg};'>"
        f"{svg}"
        f"<span class='programme-orb-title'>{title}</span>"
        "</div>"
    )


def _asset_data_uri(filename: str, mime: str) -> str:
    """Return a base64 data URI for an asset in the current programme assets folder."""
    asset_path = os.path.join(PROGRAM_DIR, "assets", filename)
    if not os.path.exists(asset_path):
        # Fall back to shared SBI assets
        asset_path = os.path.join(BASE_DIR, "..", "programs", "sbi", "assets", filename)
    data_b64 = _load_image_b64(asset_path)
    if not data_b64:
        return ""
    return f"data:{mime};base64,{data_b64}"


def show_homepage():
    """Landing page where users select a programme."""
    # Front-page background image (highest quality: original file bytes embedded as data URL).
    # Check root folder first, then fall back to SBI assets folder.
    bg_root_dir = os.path.join(BASE_DIR, "..")
    bg_assets_dir = os.path.join(BASE_DIR, "..", "programs", "sbi", "assets")
    bg_candidates = [
        (bg_root_dir, "background image.jpg", "image/jpeg"),
        (bg_assets_dir, "forest_background.avif", "image/avif"),
        (bg_assets_dir, "forest_background.png", "image/png"),
        (bg_assets_dir, "forest_background.jpg", "image/jpeg"),
        (bg_assets_dir, "forest_background.jpeg", "image/jpeg"),
        (bg_assets_dir, "forest_background.webp", "image/webp"),
    ]

    bg_style = ""
    for folder, filename, mime in bg_candidates:
        bg_path = os.path.join(folder, filename)
        bg_b64 = _load_image_b64(bg_path)
        if bg_b64:
            bg_style = (
                "<style>"
                " .stApp {"
                f"   background-image: url('data:{mime};base64,{bg_b64}') !important;"
                "   background-size: cover !important;"
                "   background-position: center center !important;"
                "   background-repeat: no-repeat !important;"
                "   background-attachment: fixed !important;"
                " }"
                "</style>"
            )
            break

    if bg_style:
        st.markdown(bg_style, unsafe_allow_html=True)

    # Hide sidebar on homepage for a clean look
    st.markdown(
        "<style>section[data-testid='stSidebar'] {display:none;}</style>",
        unsafe_allow_html=True,
    )

    _logo_path = os.path.join(BASE_DIR, "..", "programs", "sbi", "assets", "uu_logo.png")
    _logo_b64 = _load_image_b64(_logo_path)
    if _logo_b64:
        st.markdown(
            f"<div style='text-align:center;margin-top:2rem;'>"
            f"<img src='data:image/png;base64,{_logo_b64}' style='height:90px;'/>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        "<h1 class='homepage-title'>Copernicus Thesis Explorer</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p class='homepage-subtitle'>Explore Master&#39;s Thesis Research Across Programmes</p>",
        unsafe_allow_html=True,
    )

    # Homepage orbs intentionally exclude the "All Programmes" meta-entry —
    # cross-programme browsing is reachable only via the top-bar switcher.
    programme_keys = list(PROGRAMME_DISPLAY_NAMES_SINGLE.keys())

    # Row 1: first 3 programmes
    _, c1, c2, c3, _ = st.columns([0.65, 1, 1, 1, 0.65], gap="medium")
    for col, key in zip([c1, c2, c3], programme_keys[:3]):
        with col:
            st.markdown(
                f"<a href='?program={key}' class='programme-orb-link' target='_self'>"
                + _programme_icon_html(key, PROGRAMME_DISPLAY_NAMES[key])
                + "</a>",
                unsafe_allow_html=True,
            )

    st.markdown("<div style='margin-top:0.5rem;'></div>", unsafe_allow_html=True)

    # Row 2: remaining 2 programmes, centered
    _, c1, c2, _ = st.columns([1.25, 1, 1, 1.25], gap="medium")
    for col, key in zip([c1, c2], programme_keys[3:]):
        with col:
            st.markdown(
                f"<a href='?program={key}' class='programme-orb-link' target='_self'>"
                + _programme_icon_html(key, PROGRAMME_DISPLAY_NAMES[key])
                + "</a>",
                unsafe_allow_html=True,
            )


# Browser back/forward button support.
# On popstate (back/forward) we force a full reload so Streamlit reads the new URL
# and rebuilds session state from the query params.
# We only pushState on *major* navigation transitions (program / nav section / detail /
# pdf / supervisor profile change). Filter, pagination and search updates stay
# inside the current history entry — they round-trip through the URL via Streamlit's
# native replaceState, so a back press skips straight past them.
_render_html_iframe("""
<script>
(function() {
    var w = window.parent;
    var url = w.location.href;
    // Navigate the parent window by creating an <a> in the parent document
    // and clicking it — bypasses sandbox navigation restrictions while still
    // working cross-browser with allow-same-origin.
    function _stNav(target) {
        try {
            var a = w.document.createElement('a');
            a.href = target;
            a.rel = 'noopener';
            a.style.display = 'none';
            w.document.body.appendChild(a);
            a.click();
            setTimeout(function() { try { w.document.body.removeChild(a); } catch(x) {} }, 200);
        } catch(ex) {
            // last-resort fallback
            try { w.location.href = target; } catch(ex2) {}
        }
    }
    if (!w._stNavInit) {
        w._stNavInit = true;
        w.addEventListener('popstate', function() {
            _stNav(w.location.href);
        });
        // Listen for navigation requests posted from sandboxed component iframes.
        // The listener must be on w (the parent page), not window (this iframe),
        // because postMessage targets window.parent — not the sender's own frame.
        w.addEventListener('message', function(e) {
            if (e.data && e.data.type === 'stHistoryBack') {
                w.history.back();
            }
            if (e.data && e.data.type === 'stNavigateTo' && e.data.url) {
                _stNav(e.data.url);
            }
        });
    }
    function _majorKey(u) {
        try {
            var x = new URL(u);
            return [x.pathname,
                    x.searchParams.get('program') || '',
                    x.searchParams.get('nav') || '',
                    x.searchParams.get('details') || '',
                    x.searchParams.get('pdf') || '',
                    x.searchParams.get('sup_selected') || '',
                    x.searchParams.get('sup_view') || ''].join('|');
        } catch (e) { return u; }
    }
    if (w._stLastNavUrl && _majorKey(w._stLastNavUrl) !== _majorKey(url)) {
        w.history.pushState({url: url}, '', url);
    }
    w._stLastNavUrl = url;
})();
</script>
""", height=0)

# ----- page routing ---------------------------------------------------------
if st.session_state.page == "home":
    show_homepage()
    st.stop()

# From here on, we are in dashboard mode for the selected programme.
PROGRAM = st.session_state.program

if 'back_btn_requested' not in st.session_state:
    st.session_state.back_btn_requested = False

# If the back button was clicked on the previous run, fire the postMessage now
# via a height=0 invisible component, then clear the flag.
if st.session_state.back_btn_requested:
    st.session_state.back_btn_requested = False
    _render_html_iframe(
        "<script>window.parent.postMessage({type:'stHistoryBack'},'*');</script>",
        height=0,
    )

def _render_back_btn(key: str) -> None:
    """Yellow ← Back button that triggers browser history.back()."""
    if st.button("← Back", key=key):
        st.session_state.back_btn_requested = True
        st.rerun()

_CHIP_LABELS = {
    "q":        "Search",
    "years":    "Year",
    "sdgs":     "SDG",
    "sectors":  "Sector",
    "methods":  "Method",
    "theories": "Theory",
    "geos":     "Country",
    "scales":   "Scale",
    "orgs":     "Org",
    "tracks":   "Track",
    "progs":    "Programme",
    "featured": "Featured only",
}


def _explorer_url(omit_list: tuple | None = None,
                  omit_bool: str | None = None,
                  omit_str: str | None = None) -> str:
    """Build an Explorer URL from current filter state, optionally dropping one item.

    omit_list = (short_key, item_value) — drop one item from a multi-list filter.
    omit_bool = short_key — clear that bool filter.
    omit_str  = short_key — clear that string field (e.g. "q" to remove the search query).
    """
    parts = [f"program={PROGRAM}"]
    for saved_key, (short, kind) in _FILTER_URL_KEYS.items():
        val = st.session_state.get(saved_key)
        if not val:
            continue
        if kind == "list":
            items = list(val)
            if omit_list and omit_list[0] == short:
                items = [i for i in items if str(i) != str(omit_list[1])]
            if items:
                joined = ",".join(urllib.parse.quote(str(i), safe="") for i in items)
                parts.append(f"{short}={joined}")
        elif kind == "bool":
            if val and omit_bool != short:
                parts.append(f"{short}=1")
        elif kind == "str":
            if val and omit_str != short:
                parts.append(f"{short}={urllib.parse.quote(str(val), safe='')}")
    return "?" + "&".join(parts)


def _render_filter_chips() -> None:
    """Active-filter chips above the Explorer grid (Amazon/Airbnb pattern)."""
    chips: list[tuple[str, str]] = []
    for saved_key, (short, kind) in _FILTER_URL_KEYS.items():
        val = st.session_state.get(saved_key)
        if not val:
            continue
        label_base = _CHIP_LABELS.get(short, short.title())
        if kind == "list":
            for item in val:
                # Translate programme keys → friendly display names on chips.
                item_label = (
                    PROGRAMME_DISPLAY_NAMES_SINGLE.get(str(item), str(item))
                    if short == "progs" else str(item)
                )
                chips.append((f"{label_base}: {item_label}", _explorer_url(omit_list=(short, item))))
        elif kind == "bool":
            chips.append((label_base, _explorer_url(omit_bool=short)))
        elif kind == "str":
            disp = str(val)
            if len(disp) > 40:
                disp = disp[:38] + "…"
            chips.append((f'{label_base}: "{disp}"', _explorer_url(omit_str=short)))
    if not chips:
        return
    html_parts = []
    for label, url in chips:
        safe_url = url.replace('"', '&quot;')
        safe_label = label.replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
        html_parts.append(
            f'<a class="filter-chip" href="{safe_url}" target="_self" title="Remove filter">'
            f'<span>{safe_label}</span><span class="x">&#xD7;</span></a>'
        )
    _clear_url = f"?program={PROGRAM}"
    html_parts.append(
        f'<a class="filter-chip-clear" href="{_clear_url}" target="_self">Clear all</a>'
    )
    st.markdown(
        f'<div class="filter-chips">{"".join(html_parts)}</div>',
        unsafe_allow_html=True,
    )


def _render_top_bar() -> None:
    """Persistent top app-bar: brand, section nav, programme switcher, breadcrumb.

    Rendered via st.markdown so anchor links work natively without any
    iframe / postMessage boundary — plain <a href="?..."> tags.
    """
    active_section = st.session_state.get('page_nav', 'Explorer')
    selected_details = st.session_state.get('selected_details')
    selected_pdf = st.session_state.get('selected_pdf')
    sup_selected = st.session_state.get('sup_selected')
    sup_view = st.session_state.get('sup_view', 'directory')

    logo_img = (
        f'<img src="data:image/png;base64,{logo_b64}" style="width:48px;height:48px;object-fit:contain;"/>'
        if logo_b64 else ""
    )

    # Nav section links
    nav_parts = []
    for sect in ("Explorer", "Supervisors", "Insights"):
        href = f"?program={PROGRAM}" if sect == "Explorer" else f"?program={PROGRAM}&nav={sect}"
        active_cls = " active" if active_section == sect else ""
        nav_parts.append(f'<a class="topnav-link{active_cls}" href="{href}" target="_self">{sect}</a>')
    nav_html = "".join(nav_parts)

    # Programme switcher dropdown
    _current_label = _display_name if len(_display_name) <= 32 else _display_name[:30] + "…"
    _switcher_items = []
    for p_key, p_name in PROGRAMME_DISPLAY_NAMES.items():
        active_cls = " active" if p_key == PROGRAM else ""
        _switcher_items.append(
            f'<a class="topbar-switcher-item{active_cls}" href="?program={p_key}" target="_self">{p_name}</a>'
        )
    switcher_html = (
        '<details class="topbar-switcher-wrap" id="sw">'
        f'<summary class="topbar-switcher">{_current_label}<span class="chev">▾</span></summary>'
        f'<div class="topbar-switcher-menu">{"".join(_switcher_items)}</div>'
        '</details>'
    )

    # Breadcrumb
    crumbs: list[str] = [
        f'<a href="?back_home=1" target="_self">Home</a>',
        f'<a href="?program={PROGRAM}" target="_self">{_display_name}</a>',
    ]
    if active_section == "Explorer" and (selected_details or selected_pdf):
        crumbs.append(f'<a href="{_explorer_url()}" target="_self">Explorer</a>')
        key = selected_details or str(selected_pdf or "").replace(".pdf", "")
        title = ""
        try:
            for _, row in df.iterrows():
                pdf_val = row.get("Thesis_PDF", "")
                rk = (str(pdf_val).replace('.pdf', '')
                      if pd.notna(pdf_val) and str(pdf_val) not in ("", "n/a") else "")
                if rk and rk == key:
                    title = str(row.get("Title", ""))
                    break
        except Exception:
            pass
        title_short = (title[:60] + "…") if len(title) > 60 else (title or "Thesis")
        crumbs.append(f'<span class="topbar-crumb-current">{title_short}</span>')
    elif active_section == "Supervisors":
        if sup_selected:
            crumbs.append(f'<a href="?program={PROGRAM}&nav=Supervisors" target="_self">Supervisors</a>')
            crumbs.append(f'<span class="topbar-crumb-current">{sup_selected}</span>')
        elif sup_view == 'finder':
            crumbs.append(f'<a href="?program={PROGRAM}&nav=Supervisors" target="_self">Supervisors</a>')
            crumbs.append('<span class="topbar-crumb-current">Find a Supervisor</span>')
        else:
            crumbs.append('<span class="topbar-crumb-current">Supervisors</span>')
    elif active_section == "Insights":
        crumbs.append('<span class="topbar-crumb-current">Insights</span>')
    else:
        crumbs.append('<span class="topbar-crumb-current">Explorer</span>')
    crumb_html = '<span class="topbar-sep">›</span>'.join(crumbs)

    _prog_tint_local = _PROG_BG_TINT.get(PROGRAM, "#f8f9fa")

    st.markdown(f"""
<div class="topbar" style="background:{_prog_tint_local};">
  <div class="topbar-row">
    <a class="topbar-brand" href="?program={PROGRAM}" target="_self">
      {logo_img}
      <span class="topbar-title">{_display_name}</span>
    </a>
    <div class="topbar-nav">{nav_html}</div>
    {switcher_html}
  </div>
  <div class="topbar-crumbs">{crumb_html}</div>
</div>
""", unsafe_allow_html=True)

if PROGRAM == _ALL_PROGRAM_KEY:
    # All-mode: aggregate every programme's metadata into one Explorer dataset.
    # PROGRAM_DIR falls back to SBI so any module-level asset lookups
    # (logos, fallback icons) still resolve. Per-row assets (PDFs, covers)
    # are resolved via _get_program_dir_for_row using the _program_key column.
    PROGRAM_DIR = os.path.abspath(
        os.path.join(BASE_DIR, "..", "programs", _PROGRAMME_FOLDER_MAP["sbi"])
    )
else:
    PROGRAM_DIR = os.path.abspath(
        os.path.join(BASE_DIR, "..", "programs", _PROGRAMME_FOLDER_MAP.get(PROGRAM, PROGRAM))
    )

# ----- load data ------------------------------------------------------------
if PROGRAM == _ALL_PROGRAM_KEY:
    _all_frames: list[pd.DataFrame] = []
    _load_errors: list[str] = []
    for _p_key, _p_folder in _PROGRAMME_FOLDER_MAP.items():
        _p_dir = os.path.abspath(os.path.join(BASE_DIR, "..", "programs", _p_folder))
        _p_metadata = os.path.join(_p_dir, "thesis_metadata_matched.csv")
        _p_mtime = os.path.getmtime(_p_metadata) if os.path.exists(_p_metadata) else 0
        _p_df, _p_err = _load_thesis_data(_p_dir, _p_key, mtime=_p_mtime)
        if _p_err:
            _load_errors.append(f"{_p_key}: {_p_err}")
            continue
        if _p_df.empty:
            continue
        _p_df = _p_df.copy()
        _p_df["_program_key"] = _p_key
        _all_frames.append(_p_df)
    if _all_frames:
        df = pd.concat(_all_frames, ignore_index=True, sort=False).fillna("n/a")
        _load_error = ""
    else:
        df = pd.DataFrame()
        _load_error = "No programme metadata could be loaded."
    if _load_errors:
        st.warning("Some programmes failed to load: " + "; ".join(_load_errors))
    if _load_error:
        st.error(_load_error)
    # In all-mode there's no single per-programme pdf folder; per-row lookups
    # use _get_program_dir_for_row instead. Provide a harmless default.
    pdf_folder = os.path.join(PROGRAM_DIR, "pdfs")
else:
    _metadata_path = os.path.join(PROGRAM_DIR, "thesis_metadata_matched.csv")
    _mtime = os.path.getmtime(_metadata_path) if os.path.exists(_metadata_path) else 0
    df, _load_error = _load_thesis_data(PROGRAM_DIR, PROGRAM, mtime=_mtime)
    if _load_error:
        st.error(_load_error)
    pdf_folder = os.path.join(PROGRAM_DIR, "pdfs")

# ----- explorer page background colour (per-programme palette tint) -------
_PROG_BG_TINT = {
    "sbi":                    "#eef5fa",   # pale steel blue (SD's former tint)
    "energy_science":         "#fff8f0",   # pale warm amber
    "sustainable_development":"#f0f8f1",   # pale green
    "innovation_sciences":    "#f7f3fd",   # pale lavender
    "water_management":       "#f0f9ff",   # pale cyan
    "all":                    "#f5f5f7",   # neutral grey for cross-programme view
}
_prog_tint = _PROG_BG_TINT.get(PROGRAM, "#f8f9fa")
st.markdown(
    "<style>"
    " .stApp, .stApp > .main {"
    f"  background-color: {_prog_tint} !important;"
    "  background-image: none !important;"
    " }"
    # Topbar inherits the programme tint so it visually merges with the
    # page background — no white-chrome strip floating over content.
    " .topbar {"
    f"  background-color: {_prog_tint} !important;"
    " }"
    "</style>",
    unsafe_allow_html=True,
)

# ----- navigation ----------------------------------------------------------

_display_name = PROGRAMME_DISPLAY_NAMES.get(PROGRAM, PROGRAM)

logo_path = os.path.join(PROGRAM_DIR, "assets", "uu_logo.png")
if not os.path.exists(logo_path):
    logo_path = os.path.join(BASE_DIR, "..", "programs", "sbi", "assets", "uu_logo.png")
logo_b64 = _load_image_b64(logo_path)

# ----- page navigation ----------------------------------------------------
if "page_nav" not in st.session_state:
    st.session_state.page_nav = "Explorer"
_VALID_PAGES = ("Explorer", "Supervisors", "Insights")
if st.session_state.get("pending_page_nav") in _VALID_PAGES:
    st.session_state.page_nav = st.session_state.pending_page_nav
    st.session_state.pending_page_nav = None

page = st.session_state.page_nav

# Persistent top app-bar — replaces the old programme-header + sidebar-nav +
# in-page detail-nav row. Renders on every programme-scoped page.
_render_top_bar()

# Sidebar discipline: it now contains *only* the Filter panel, which is only
# meaningful on the Explorer grid. Hide the sidebar everywhere else (detail
# view, PDF reader, Supervisors, Insights). Global nav stays reachable via
# the top bar.
explorer_detail_mode = (
    page == "Explorer"
    and (
        bool(st.session_state.get("selected_details"))
        or bool(st.session_state.get("selected_pdf"))
    )
)

if "details_sidebar_expanded" not in st.session_state:
    st.session_state.details_sidebar_expanded = False

if not explorer_detail_mode:
    st.session_state.details_sidebar_expanded = False

show_explorer_filters = (
    page == "Explorer"
    and not explorer_detail_mode
)

if not show_explorer_filters:
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _is_valid_value(value) -> bool:
    text = str(value).strip().lower()
    return text not in ("", "n/a", "na", "nan")


def _split_multi_values(raw_value) -> list[str]:
    parts = [part.strip() for part in str(raw_value).split(",")]
    return [part for part in parts if _is_valid_value(part)]


def _series_options(series: pd.Series, *, sdg_sort: bool = False) -> list[str]:
    cleaned = [str(v).strip() for v in series.tolist() if _is_valid_value(v)]
    unique_vals = sorted(set(cleaned), key=lambda x: x.lower())
    if not sdg_sort:
        return unique_vals

    import re

    def _sdg_key(item: str):
        match = re.match(r"^\s*(\d+)", item)
        if match:
            return (0, int(match.group(1)), item.lower())
        return (1, float("inf"), item.lower())

    return sorted(unique_vals, key=_sdg_key)


if show_explorer_filters:
    st.sidebar.header("Search & Filters")

    # SDG color map for circle badges in filter
    _SDG_HEX = {
        "1": "#E5243B", "2": "#DDA63A", "3": "#4C9F38", "4": "#C5192D",
        "5": "#FF3A21", "6": "#26BDE2", "7": "#FCC30B", "8": "#A21942",
        "9": "#FD6925", "10": "#DD1367", "11": "#FD9D24", "12": "#BF8B2E",
        "13": "#3F7E44", "14": "#0A97D9", "15": "#56C02B", "16": "#00689D",
        "17": "#19486A",
    }
    def _sdg_format(option: str) -> str:
        """Return SDG option label with a colored circle prefix."""
        import re as _re
        m = _re.match(r"^\s*(\d+)", str(option))
        if m:
            num = m.group(1)
            color = _SDG_HEX.get(num, "#888888")
            # Unicode LARGE CIRCLE rendered in sidebar (plain text, color via CSS override is not possible,
            # but we can use a filled block + tinted approach with a narrow no-break space)
            return f"⬤  {option}"
        return option

    if not df.empty:
        search_query = st.sidebar.text_input(
            "Search",
            value=st.session_state.saved_search_query,
            placeholder="Title, author, keyword, or topic…",
            key="explorer_search_input",
        )

        with st.sidebar.expander("Filter", expanded=False):
            # Master Track filter (only for Sustainable Development) — shown at the top
            _SD_TRACK_CANONICAL = [
                "Energy & Materials",
                "Earth Systems Governance",
                "Environmental Change and Ecosystems",
                "Politics, Ecology and Society",
                "International Development",
            ]
            _SD_TRACK_NORMALISE = {
                "ecosystems and environmental change": "Environmental Change and Ecosystems",
            }
            master_track_options = []
            if PROGRAM == "sustainable_development" and "Master Track" in df.columns:
                master_track_options = [t for t in _SD_TRACK_CANONICAL if t in (
                    _SD_TRACK_NORMALISE.get(str(v).strip().lower(), str(v).strip())
                    for v in df["Master Track"].dropna()
                )]
            if master_track_options:
                master_track_filter = st.multiselect(
                    "Master Track", master_track_options,
                    default=[v for v in st.session_state.saved_master_track_filter if v in master_track_options],
                    key="filter_master_track",
                )
            else:
                master_track_filter = []

            # Programme filter — only meaningful in all-programmes mode.
            if PROGRAM == _ALL_PROGRAM_KEY:
                _program_options = list(PROGRAMME_DISPLAY_NAMES_SINGLE.keys())
                program_filter = st.multiselect(
                    "Programme", _program_options,
                    default=[v for v in st.session_state.saved_program_filter if v in _program_options],
                    format_func=lambda k: PROGRAMME_DISPLAY_NAMES_SINGLE.get(k, k),
                    key="filter_program",
                )
            else:
                program_filter = []

            year_options = _series_options(df["Year"])
            sdg_options = _series_options(df["SDG"], sdg_sort=True)
            sector_options = _series_options(df["Main sector"])
            method_options = [
                "Conceptual & Theoretical",
                "Literature-Based Research",
                "Qualitative Empirical Research",
                "Quantitative Empirical Research",
                "Mixed Methods Research",
                "Modelling & Systems Approaches",
                "Spatial & Environmental Analysis",
                "Participatory & Action-Oriented Research",
            ]
            _country_col_filter = "Country" if "Country" in df.columns else "Geographical scope"
            _country_vals: set[str] = set()
            for _v in df[_country_col_filter].dropna():
                for _part in str(_v).split(";"):
                    _part = _part.strip()
                    if _part and _part.lower() not in ("n/a", "nan", ""):
                        _country_vals.add(_part)
            geo_options = sorted(_country_vals, key=lambda x: x.lower())

            scale_col = "Scale" if "Scale" in df.columns else "Research Scale" if "Research Scale" in df.columns else None
            scale_options = _series_options(df[scale_col]) if scale_col else []

            _org_vals: set[str] = set()
            for _v in df["Internship Organization"].dropna():
                for _part in str(_v).split(";"):
                    _part = _part.strip()
                    if _part and _part.lower() not in ("n/a", "nan", ""):
                        _org_vals.add(_part)
            internship_org_options = sorted(_org_vals, key=lambda x: x.lower())


            year_filter = st.multiselect(
                "Year", year_options,
                default=[v for v in st.session_state.saved_year_filter if v in year_options],
                key="filter_year",
            )
            sdg_filter = st.multiselect(
                "SDG", sdg_options,
                default=[v for v in st.session_state.saved_sdg_filter if v in sdg_options],
                key="filter_sdg",
            )
            # Inject SDG colored circles:
            # - .st-key-filter_sdg [data-baseweb="tag"][title^="N "] targets selected chips inside sidebar
            # - li[role="option"][aria-label^="N "] targets dropdown list items (rendered in portal)
            _sdg_parts = []
            for _n, _hex in _SDG_HEX.items():
                _sdg_parts.append(
                    f".st-key-filter_sdg [data-baseweb=\"tag\"][title^=\"{_n} \"]::before,"
                    f"li[role=\"option\"][aria-label^=\"{_n} \"]::before"
                    f"{{content:\"●\";color:{_hex};margin-right:5px;font-size:0.82em;vertical-align:middle;}}"
                )
            st.markdown(f"<style>{''.join(_sdg_parts)}</style>", unsafe_allow_html=True)

            sector_filter = st.multiselect(
                "Sector", sector_options,
                default=[v for v in st.session_state.saved_sector_filter if v in sector_options],
                key="filter_sector",
            )
            method_filter = st.multiselect(
                "Methodology Type", method_options,
                default=[v for v in st.session_state.saved_method_filter if v in method_options],
                key="filter_method",
            )
            geo_filter = st.multiselect(
                "Country", geo_options,
                default=[v for v in st.session_state.saved_geo_filter if v in geo_options],
                key="filter_geo",
            )
            scale_filter = st.multiselect(
                "Research Scale", scale_options,
                default=[v for v in st.session_state.saved_scale_filter if v in scale_options],
                key="filter_scale",
            )
            internship_org_filter = st.multiselect(
                "Internship Organization", internship_org_options,
                default=[v for v in st.session_state.saved_internship_org_filter if v in internship_org_options],
                key="filter_internship_org",
            )

            featured_only = st.checkbox("Featured theses only", value=st.session_state.saved_featured_only, key="filter_featured")
            st.caption("Selection of exceptional theses recommended by programme coordinators.")

        # Reset button (outside expander, below it)
        def _reset_filters():
            for _k in _FILTER_KEYS:
                if _k in ("saved_search_query", "saved_theory_filter"):
                    st.session_state[_k] = ""
                elif _k == "saved_featured_only":
                    st.session_state[_k] = False
                else:
                    st.session_state[_k] = []
            # Also clear the widget keys so they reset visually
            for _wk in ["filter_year", "filter_sdg", "filter_sector", "filter_method",
                         "filter_theory", "filter_geo", "filter_scale", "filter_internship_org",
                         "filter_master_track", "filter_program",
                         "filter_featured", "explorer_search_input"]:
                if _wk in st.session_state:
                    del st.session_state[_wk]
            st.session_state.explorer_page = 0
            # Strip filter params from the URL so the next render's init pass
            # doesn't re-restore the values we just cleared.
            _sync_explorer_url()

        st.sidebar.button("Reset filters", on_click=_reset_filters, key="reset_filters_btn")

    else:
        search_query = ""
        year_filter = []
        sdg_filter = []
        sector_filter = []
        method_filter = []
        geo_filter = []
        scale_filter = []
        internship_org_filter = []
        master_track_filter = []
        program_filter = []
        search_query = ""
        featured_only = False

    # apply filters
    filtered_df = df.copy()

    if year_filter:
        filtered_df = filtered_df[filtered_df["Year"].isin(year_filter)]
    if sdg_filter:
        filtered_df = filtered_df[filtered_df["SDG"].isin(sdg_filter)]
    if sector_filter:
        filtered_df = filtered_df[filtered_df["Main sector"].isin(sector_filter)]
    if method_filter:
        _sel_methods = {m.strip().lower() for m in method_filter}
        filtered_df = filtered_df[
            filtered_df["Methodology Type"].apply(
                lambda v: bool(_sel_methods.intersection(
                    {part.strip().lower() for part in str(v).split(",")}
                )) if pd.notna(v) else False
            )
        ]
    if geo_filter:
        _sel_countries = {c.strip().lower() for c in geo_filter}
        _country_col_apply = "Country" if "Country" in filtered_df.columns else "Geographical scope"
        filtered_df = filtered_df[
            filtered_df[_country_col_apply].apply(
                lambda v: bool(_sel_countries.intersection(
                    {p.strip().lower() for p in str(v).split(";")} if pd.notna(v) else set()
                )) if pd.notna(v) else False
            )
        ]
    if internship_org_filter:
        _sel_orgs = {o.strip().lower() for o in internship_org_filter}
        filtered_df = filtered_df[
            filtered_df["Internship Organization"].apply(
                lambda v: bool(_sel_orgs.intersection(
                    {p.strip().lower() for p in str(v).split(";")} if pd.notna(v) else set()
                )) if pd.notna(v) else False
            )
        ]

    # Apply Master Track filter for Sustainable Development (normalise raw values before comparing)
    if 'master_track_filter' in locals() and master_track_filter and "Master Track" in filtered_df.columns:
        _sel_tracks = set(master_track_filter)
        filtered_df = filtered_df[
            filtered_df["Master Track"].apply(
                lambda v: _SD_TRACK_NORMALISE.get(str(v).strip().lower(), str(v).strip()) in _sel_tracks
                if pd.notna(v) else False
            )
        ]

    # Apply Programme filter (only relevant in all-programmes mode)
    if program_filter and "_program_key" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["_program_key"].isin(program_filter)]

    if featured_only and "Featured" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Featured"]]

    if scale_filter:
        _scale_column = "Scale" if "Scale" in filtered_df.columns else "Research Scale" if "Research Scale" in filtered_df.columns else None
        if _scale_column:
            filtered_df = filtered_df[filtered_df[_scale_column].isin(scale_filter)]

    if search_query:
        _q = search_query.strip()
        # Build one lowercase text blob per thesis from all searchable fields.
        # Multi-word queries are split into tokens and matched with AND logic so
        # "sustainable tourism" finds any thesis that contains both words anywhere
        # across title, author, keywords, abstract, and research question —
        # rather than requiring the exact phrase to appear verbatim.
        _search_blob = (
            filtered_df["Title"].fillna("") + " " +
            filtered_df["Author(s)"].fillna("") + " " +
            filtered_df["Keywords"].fillna("") + " " +
            filtered_df["Abstract/Summary"].fillna("") + " " +
            filtered_df["Main Research Question"].fillna("") + " " +
            filtered_df["Theories"].fillna("")
        ).str.lower()
        _tokens = [t for t in _q.lower().split() if len(t) >= 2]
        if _tokens:
            _mask = _search_blob.str.contains(_tokens[0], regex=False, na=False)
            for _tok in _tokens[1:]:
                _mask = _mask & _search_blob.str.contains(_tok, regex=False, na=False)
            filtered_df = filtered_df[_mask]

    # show summary of active filters
    active_filters_count = sum(
        bool(value)
        for value in [
            search_query,
            year_filter,
            sdg_filter,
            sector_filter,
            method_filter,
            geo_filter,
            scale_filter,
            internship_org_filter,
            master_track_filter,
            program_filter,
            featured_only,
        ]
    )
    # Persist current filter values so they survive navigating into/out of details view
    st.session_state.saved_search_query = search_query
    st.session_state.saved_year_filter = year_filter
    st.session_state.saved_sdg_filter = sdg_filter
    st.session_state.saved_sector_filter = sector_filter
    st.session_state.saved_method_filter = method_filter
    st.session_state.saved_geo_filter = geo_filter
    st.session_state.saved_scale_filter = scale_filter
    st.session_state.saved_internship_org_filter = internship_org_filter
    st.session_state.saved_master_track_filter = master_track_filter
    st.session_state.saved_program_filter = program_filter
    st.session_state.saved_featured_only = featured_only
    # Mirror filter state into the URL so browser back/forward (which hard-
    # reloads the page) can restore it from query params.
    _sync_explorer_url()
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Matching theses:** {len(filtered_df)}")
    st.sidebar.caption(f"Active filters: {active_filters_count}")
else:
    filtered_df = df.copy()

# ----- page content --------------------------------------------------------

if page == "Explorer":
    # PDF and details viewing modes
    selected_pdf = st.session_state.selected_pdf
    selected_details = st.session_state.selected_details

    if selected_pdf:
        # Full-page PDF reading mode with download support.
        pdf_path = os.path.join(pdf_folder, selected_pdf)
        if os.path.exists(pdf_path):
            matching_row = find_row_by_pdf_name(df, selected_pdf)

            st.markdown("### Thesis Viewer")
            _render_back_btn("back_btn_pdf_reader")

            st.caption("Full-page thesis viewer. Use the viewer controls to navigate and inspect the document in detail.")

            # Embed PDF as base64 data URI — works on Streamlit Cloud where
            # 127.0.0.1 server URLs are unreachable from the user's browser.
            _dl_bytes = _load_pdf_bytes_cached(pdf_path)
            if _dl_bytes:
                _static_url = "data:application/pdf;base64," + base64.b64encode(_dl_bytes).decode()
            else:
                _pdf_rel = os.path.relpath(pdf_path, _PROJECT_ROOT).replace(os.sep, "/")
                _static_url = f"http://127.0.0.1:{_PDF_SERVER_PORT}/{_pdf_rel}"
            _render_html_iframe(_pdf_iframe_html(_static_url, height=1100), height=1108)
            if _dl_bytes:
                st.download_button(
                    label="Download Thesis PDF",
                    data=_dl_bytes,
                    file_name=selected_pdf,
                    mime="application/pdf",
                    key=f"reader_download_{selected_pdf}",
                    help="Download the full thesis as a PDF file.",
                )

            if matching_row is not None:
                with st.expander("Thesis details", expanded=False):
                    st.markdown(
                        f"<div class='detail-hero-title' style='font-size:1.48em;'>{matching_row['Title']}</div>"
                        f"<div class='detail-hero-meta'>"
                        f"<strong>{matching_row['Author(s)']}</strong>"
                        f"<span class='sep'>•</span>{matching_row['Year']}"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    featured_banner = _featured_badge_html(bool(matching_row.get('Featured', False)))
                    if featured_banner:
                        st.markdown(f"<div class='featured-strip'>{featured_banner}</div>", unsafe_allow_html=True)
                    st.markdown("")
                    render_structured_details_sections(matching_row)
            else:
                st.error("The requested thesis metadata could not be found.")

            if matching_row is not None:
                render_related_thesis_cards(matching_row, "reader_related_view")
        else:
            st.warning(
                f"PDF not available in this deployment. "
                f"[Browse all theses on Google Drive]({_DRIVE_ROOT_FALLBACK})"
            )
            _render_back_btn("back_btn_pdf_err")

    elif selected_details:
        # Focused details viewing mode: hide the grid and show detailed metadata.
        # Find the matching thesis from the full dataset (not filtered, so details work even if filters change)
        matching_row = None
        for _, row in df.iterrows():
            pdf_val = row.get("Thesis_PDF", "")
            row_key = str(pdf_val).replace('.pdf', '') if pd.notna(pdf_val) and str(pdf_val) not in ("", "n/a") else ""
            if row_key and row_key == selected_details:
                matching_row = row
                break

        if matching_row is not None:
            pdf_name = str(matching_row.get("Thesis_PDF", "n/a"))
            pdf_path = os.path.join(PROGRAM_DIR, "pdfs", pdf_name)
            has_pdf = pdf_name not in ("n/a", "", "nan") and os.path.exists(pdf_path)

            if has_pdf:
                _render_back_btn("back_btn_details_pdf")

                # ── Hero header ──
                st.markdown(
                    f"<div class='detail-hero-title'>{matching_row['Title']}</div>"
                    f"<div class='detail-hero-meta'>"
                    f"<strong>{matching_row['Author(s)']}</strong>"
                    f"<span class='sep'>•</span>{matching_row['Year']}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                featured_banner = _featured_badge_html(bool(matching_row.get('Featured', False)))
                if featured_banner:
                    st.markdown(f"<div class='featured-strip'>{featured_banner}</div>", unsafe_allow_html=True)
                st.markdown("")

                # ── Two-column layout: PDF | Metadata ──
                col_pdf, col_meta = st.columns([5, 4], gap="large")

                with col_pdf:
                    # Embed PDF as base64 data URI — works on Streamlit Cloud where
                    # 127.0.0.1 server URLs are unreachable from the user's browser.
                    _det_dl_bytes_preview = _load_pdf_bytes_cached(pdf_path)
                    if _det_dl_bytes_preview:
                        _det_static_url = "data:application/pdf;base64," + base64.b64encode(_det_dl_bytes_preview).decode()
                    else:
                        _det_pdf_rel = os.path.relpath(pdf_path, _PROJECT_ROOT).replace(os.sep, "/")
                        _det_static_url = f"http://127.0.0.1:{_PDF_SERVER_PORT}/{_det_pdf_rel}"
                    _render_html_iframe(_pdf_iframe_html(_det_static_url, height=850), height=858)

                    download_icon_uri = _asset_data_uri("pdf_download_icon.png", "image/png")
                    download_label = (
                        f"![download]({download_icon_uri}) Download PDF"
                        if download_icon_uri
                        else "Download PDF"
                    )

                    # Download button uses cached bytes (read once per session)
                    _det_dl_bytes = _load_pdf_bytes_cached(pdf_path)
                    with st.container(key="details_action_buttons"):
                        if _det_dl_bytes:
                            st.download_button(
                                label=download_label,
                                data=_det_dl_bytes,
                                file_name=pdf_name,
                                mime="application/pdf",
                                key=f"details_download_{pdf_name}",
                                width='stretch',
                            )

                with col_meta:
                    render_structured_details_sections(matching_row)

                render_related_thesis_cards(matching_row, "details_reader_related_view")
            else:
                _render_back_btn("back_btn_details_no_pdf")

                # ── Hero header ──
                cover_path, _ = resolve_cover_and_pdf_paths(matching_row)
                hero_c1, hero_c2 = st.columns([1, 4], gap="medium")
                with hero_c1:
                    if cover_path and os.path.exists(cover_path):
                        st.image(cover_path, width=220)
                    else:
                        st.markdown(
                            "<div style='width:200px;height:140px;background:#eee;border-radius:8px;"
                            "display:flex;align-items:center;justify-content:center;"
                            "color:#666;font-style:italic;'>No cover available</div>",
                            unsafe_allow_html=True,
                        )
                with hero_c2:
                    st.markdown(
                        f"<div class='detail-hero-title'>{matching_row['Title']}</div>"
                        f"<div class='detail-hero-meta'>"
                        f"<strong>{matching_row['Author(s)']}</strong>"
                        f"<span class='sep'>•</span>{matching_row['Year']}"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    featured_banner = _featured_badge_html(bool(matching_row.get('Featured', False)))
                    if featured_banner:
                        st.markdown(f"<div class='featured-strip'>{featured_banner}</div>", unsafe_allow_html=True)
                    if pdf_name not in ("n/a", "", "nan"):
                        if st.button("📖 Open Thesis", key="details_nopdf_open"):
                            st.session_state.selected_pdf = pdf_name
                            st.session_state.selected_details = None
                            st.query_params.clear()
                            st.query_params["program"] = PROGRAM
                            st.query_params["pdf"] = pdf_name
                            st.rerun()
                        st.markdown(
                            f"[Browse all theses on Google Drive]({_DRIVE_ROOT_FALLBACK})",
                            unsafe_allow_html=False,
                        )
                    else:
                        st.caption("PDF not available")

                st.markdown("")
                render_structured_details_sections(matching_row)
                render_related_thesis_cards(matching_row, "details_no_pdf_related_view")

        else:
            st.error("The requested thesis details could not be found.")
            _render_back_btn("back_btn_details_not_found")

    else:
        explorer_df = filtered_df.copy()
        # Featured theses first, then newest year first within each group.
        explorer_df["_year_sort"] = pd.to_numeric(explorer_df["Year"], errors="coerce")
        explorer_df["_featured_sort"] = explorer_df["Featured"].astype(bool) if "Featured" in explorer_df.columns else False
        explorer_df = explorer_df.sort_values(
            by=["_featured_sort", "_year_sort"],
            ascending=[False, False],
            na_position="last",
        )

        # Reset page when filters change the result count
        import math
        total_theses = len(explorer_df)
        total_pages = max(1, math.ceil(total_theses / THESES_PER_PAGE))
        current_page = st.session_state.explorer_page
        if current_page >= total_pages:
            current_page = total_pages - 1
            st.session_state.explorer_page = current_page
        # Mirror pagination into the URL so back/forward restores the page.
        _sync_explorer_url()

        # Active filter chips — shows the user exactly which filters are
        # restricting their view, with a one-click way to remove each.
        _render_filter_chips()

        if filtered_df.empty:
            st.info("No theses match the current filters.")
        else:
            # -- Global research map (first page only) --
            if current_page == 0:
                try:
                    import pydeck as _epdk
                    import numpy as _enp

                    _emap_src = filtered_df.copy()

                    # Expand multi-location theses: each thesis with All_Latitudes
                    # containing '|' gets one row per location so all appear on the map.
                    _emap_rows = []
                    for _, _erow in _emap_src.iterrows():
                        _all_lats = str(_erow.get("All_Latitudes", "")).strip()
                        _all_lons = str(_erow.get("All_Longitudes", "")).strip()
                        if "|" in _all_lats and "|" in _all_lons:
                            _lat_parts = [p.strip() for p in _all_lats.split("|")]
                            _lon_parts = [p.strip() for p in _all_lons.split("|")]
                            for _pla, _plo in zip(_lat_parts, _lon_parts):
                                try:
                                    _new_row = _erow.copy()
                                    _new_row["Latitude"]  = float(_pla)
                                    _new_row["Longitude"] = float(_plo)
                                    _emap_rows.append(_new_row)
                                except (ValueError, TypeError):
                                    pass
                        else:
                            _emap_rows.append(_erow)
                    _emap_df = pd.DataFrame(_emap_rows).reset_index(drop=True)

                    _emap_df["_lat"] = pd.to_numeric(_emap_df.get("Latitude", pd.Series(dtype=float)), errors="coerce")
                    _emap_df["_lon"] = pd.to_numeric(_emap_df.get("Longitude", pd.Series(dtype=float)), errors="coerce")
                    _emap_df = _emap_df.dropna(subset=["_lat", "_lon"])
                    _emap_df = _emap_df[
                        _emap_df["_lat"].between(-90, 90) &
                        _emap_df["_lon"].between(-180, 180)
                    ].copy()

                    if not _emap_df.empty:
                        # Jitter overlapping points
                        _cc = ["_lat", "_lon"]
                        _emap_df["_cnt"] = _emap_df.groupby(_cc)["Title"].transform("size")
                        _emap_df["_rank"] = _emap_df.groupby(_cc).cumcount()
                        _ang  = _emap_df["_rank"] * 2.3999632297
                        _spr  = 0.015 * _enp.sqrt(_emap_df["_rank"] / _emap_df["_cnt"].clip(lower=1))
                        _spr  = _spr.where(_emap_df["_cnt"] > 1, 0.0)
                        _lr   = _enp.deg2rad(_emap_df["_lat"].clip(-89.9, 89.9))
                        _lsc  = _enp.clip(_enp.cos(_lr), 0.2, None)
                        _emap_df["_plot_lat"] = _emap_df["_lat"] + _spr * _enp.sin(_ang)
                        _emap_df["_plot_lon"] = _emap_df["_lon"] + (_spr * _enp.cos(_ang) / _lsc)
                        # SDG colour coding
                        _sdg_rgb = {
                            1:[229,36,59], 2:[221,166,58], 3:[76,159,56], 4:[197,25,45],
                            5:[255,58,33], 6:[38,189,226], 7:[252,195,11], 8:[162,25,66],
                            9:[253,105,37], 10:[221,19,103], 11:[253,157,36], 12:[191,139,46],
                            13:[63,126,68], 14:[10,151,217], 15:[86,192,43], 16:[0,104,157],
                            17:[25,72,106],
                        }
                        _sdg_nums = pd.to_numeric(
                            _emap_df["SDG"].astype(str).str.extract(r"^(\d+)")[0], errors="coerce"
                        )
                        _emap_df["_color"] = [
                            _sdg_rgb.get(int(n), [140,140,140]) + [220] if _enp.isfinite(n) else [140,140,140,180]
                            for n in _sdg_nums
                        ]

                        _emap_df["_details_key"] = _emap_df["Thesis_PDF"].astype(str).str.replace(".pdf", "", regex=False)

                        _emap_event = st.pydeck_chart(
                            _epdk.Deck(
                                layers=[_epdk.Layer(
                                    "ScatterplotLayer",
                                    id="explorer-map-points",
                                    data=_emap_df,
                                    get_position=["_plot_lon", "_plot_lat"],
                                    get_fill_color="_color",
                                    get_radius=7,
                                    radius_units="pixels",
                                    radius_min_pixels=3,
                                    radius_max_pixels=14,
                                    opacity=0.9,
                                    pickable=True,
                                    auto_highlight=True,
                                    stroked=True,
                                    get_line_color=[255, 255, 255, 180],
                                    line_width_min_pixels=1,
                                )],
                                initial_view_state=_epdk.ViewState(latitude=20, longitude=10, zoom=0.9),
                                tooltip={
                                    "html": "<b>{Title}</b><br/><span style='color:#888'>{Author(s)} · {Year} · SDG {SDG}</span><br/><span style='color:#aaa;font-size:11px'>Click to open details</span>",
                                    "style": {
                                        "backgroundColor": "#fff",
                                        "color": "#222",
                                        "fontSize": "12px",
                                        "border": "1px solid #e0e0e0",
                                        "borderRadius": "8px",
                                        "padding": "8px 10px",
                                        "maxWidth": "260px",
                                    },
                                },
                                map_provider="carto",
                                map_style="light",
                            ),
                            width="stretch",
                            height=340,
                            on_select="rerun",
                            selection_mode="single-object",
                            key="explorer_research_map",
                        )
                        st.caption(f"{len(_emap_df)} of {total_theses} theses mapped by geographical study location. Click a dot to open the thesis.")

                        # Handle click → navigate to details
                        _sel_pts = (
                            _emap_event.get("selection", {})
                            .get("objects", {})
                            .get("explorer-map-points", [])
                            if isinstance(_emap_event, dict) else []
                        )
                        if _sel_pts:
                            _sel_key = str(_sel_pts[0].get("_details_key", ""))
                            if _sel_key and _sel_key not in ("n/a", "nan", ""):
                                st.session_state.selected_details = _sel_key
                                st.session_state.selected_pdf = None
                                st.query_params.clear()
                                st.query_params["program"] = PROGRAM
                                st.query_params["details"] = _sel_key
                                st.rerun()
                except ImportError:
                    pass

            # -- Master Track quick-filter cards (Sustainable Development only) --
            # Pure HTML <a> cards with orb icons — same navigation pattern as
            # the Explorer/Supervisors/Insights topnav links (URL param toggle).
            if PROGRAM == "sustainable_development":
                # Each track: canonical name, accent colour, light bg, inner SVG markup
                _SD_TRACKS_META = [
                    {
                        "name": "Energy & Materials",
                        "color": "#ea580c",
                        "bg": "#fff7ed",
                        # Lightning bolt (Heroicons outline BoltIcon)
                        "svg_inner": '<path stroke-linecap="round" stroke-linejoin="round" d="m3.75 13.5 10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75Z"/>',
                    },
                    {
                        "name": "Earth Systems Governance",
                        "color": "#1d4ed8",
                        "bg": "#eff6ff",
                        # Globe with meridian curves + latitude lines
                        "svg_inner": (
                            '<circle cx="12" cy="12" r="9" stroke-linecap="round" stroke-linejoin="round"/>'
                            '<path stroke-linecap="round" stroke-linejoin="round" d="'
                            'M12 3c-2.4 3.6-2.4 14.4 0 18'
                            'M12 3c2.4 3.6 2.4 14.4 0 18'
                            'M3 12h18M4.5 7.5h15M4.5 16.5h15'
                            '"/>'
                        ),
                    },
                    {
                        "name": "Environmental Change and Ecosystems",
                        "color": "#0891b2",
                        "bg": "#e0f7fa",
                        # ArrowPath (cycling arrows — ecological cycles / change)
                        "svg_inner": (
                            '<path stroke-linecap="round" stroke-linejoin="round" d="'
                            'M19.5 12c0-1.232-.046-2.453-.138-3.662a4.006 4.006 0 0 0-3.7-3.7'
                            ' 48.678 48.678 0 0 0-7.324 0 4.006 4.006 0 0 0-3.7 3.7'
                            'c-.017.22-.032.441-.046.662'
                            'M19.5 12l3-3m-3 3-3-3'
                            'm-12 3c0 1.232.046 2.453.138 3.662a4.006 4.006 0 0 0 3.7 3.7'
                            ' 48.656 48.656 0 0 0 7.324 0 4.006 4.006 0 0 0 3.7-3.7'
                            'c.017-.22.032-.441.046-.662'
                            'M4.5 12l3 3m-3-3-3 3'
                            '"/>'
                        ),
                    },
                    {
                        "name": "Politics, Ecology and Society",
                        "color": "#7c3aed",
                        "bg": "#f5f3ff",
                        # UserGroup (community / society)
                        "svg_inner": (
                            '<path stroke-linecap="round" stroke-linejoin="round" d="'
                            'M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952'
                            ' 4.125 4.125 0 0 0-7.533-2.493'
                            'M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07'
                            'M15 19.128v.106A12.318 12.318 0 0 1 8.624 21'
                            'c-2.331 0-4.512-.645-6.374-1.766l-.001-.109'
                            'a6.375 6.375 0 0 1 11.964-3.07'
                            'M12 6.375a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0Z'
                            'm8.25 2.25a2.625 2.625 0 1 1-5.25 0 2.625 2.625 0 0 1 5.25 0Z'
                            '"/>'
                        ),
                    },
                ]
                _cur_track_filter = list(st.session_state.get("saved_master_track_filter", []))
                _cur_params = dict(st.query_params)

                _track_css = """<style>
.track-filter-row {
    display: flex;
    gap: 10px;
    margin: 20px 0 18px;
}
.track-filter-card {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 9px;
    padding: 14px 8px 12px;
    border-radius: 14px;
    background: transparent;
    border: 2px solid transparent;
    box-shadow: none;
    cursor: pointer;
    text-decoration: none !important;
    transition: transform 0.18s ease, background 0.18s ease, border-color 0.18s ease;
    min-width: 0;
}
.track-filter-card:hover {
    transform: translateY(-2px);
    background: rgba(255,255,255,0.60);
    border-color: rgba(0,54,96,0.10);
    text-decoration: none !important;
}
.track-filter-card.active {
    border-color: var(--tc);
    background: var(--tc-bg);
}
.track-filter-card.active:hover {
    background: var(--tc-bg);
}
.track-icon-orb {
    width: 52px;
    height: 52px;
    border-radius: 50%;
    background: var(--tc-bg);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: background 0.18s ease, transform 0.18s ease;
}
.track-filter-card:hover .track-icon-orb {
    transform: scale(1.06);
}
.track-filter-card.active .track-icon-orb {
    background: var(--tc);
}
.track-icon-orb svg {
    width: 26px;
    height: 26px;
    display: block;
    filter: drop-shadow(0 1px 2px rgba(0,0,0,0.08));
}
.track-icon-orb svg path, .track-icon-orb svg circle {
    stroke: var(--tc);
    transition: stroke 0.18s ease;
}
.track-filter-card.active .track-icon-orb svg path,
.track-filter-card.active .track-icon-orb svg circle {
    stroke: #ffffff;
}
.track-label {
    font-size: 0.76rem;
    font-weight: 600;
    text-align: center;
    line-height: 1.3;
    color: var(--uu-blue, #003660);
    letter-spacing: 0.01em;
}
.track-filter-card.active .track-label {
    color: var(--tc);
}
</style>"""
                _cards_html = ['<div class="track-filter-row">']
                for _t in _SD_TRACKS_META:
                    _tname  = _t["name"]
                    _tcolor = _t["color"]
                    _tbg    = _t["bg"]
                    _is_active = _tname in _cur_track_filter
                    _active_cls = " active" if _is_active else ""
                    # Build URL — toggle this track in the `tracks` param
                    _link_params = dict(_cur_params)
                    if _is_active:
                        _link_params.pop("tracks", None)
                    else:
                        _link_params["tracks"] = _tname
                    _link_params.pop("page", None)
                    _href = "?" + urllib.parse.urlencode(_link_params, quote_via=urllib.parse.quote)
                    _svg = (
                        '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"'
                        ' stroke-width="1.6" stroke="currentColor">'
                        + _t["svg_inner"]
                        + '</svg>'
                    )
                    _cards_html.append(
                        f'<a class="track-filter-card{_active_cls}" href="{_href}" target="_self"'
                        f' style="--tc:{_tcolor};--tc-bg:{_tbg};">'
                        f'<div class="track-icon-orb">{_svg}</div>'
                        f'<span class="track-label">{_tname}</span>'
                        f'</a>'
                    )
                _cards_html.append('</div>')
                st.markdown(_track_css + "".join(_cards_html), unsafe_allow_html=True)

            # -- pagination info + top navigation --
            start_idx = current_page * THESES_PER_PAGE
            end_idx = min(start_idx + THESES_PER_PAGE, total_theses)

            st.markdown(
                f"<div class='pagination-info'>Showing {start_idx + 1}&ndash;{end_idx} of {total_theses} theses &nbsp;|&nbsp; Page {current_page + 1} of {total_pages}</div>",
                unsafe_allow_html=True,
            )

            def set_explorer_page(new_page: int):
                new_page = max(0, min(new_page, total_pages - 1))
                st.session_state.explorer_page = new_page
                # Mirror to URL immediately so the upcoming rerun's init pass
                # reads the new page from query_params (otherwise the init
                # restore would clobber session_state back to the old page).
                _sync_explorer_url()

            # Top pagination controls
            def render_pagination(position):
                nav_cols = st.columns([1, 1, 1, 1])
                with nav_cols[0]:
                    if st.button("\u00ab First", key=f"first_{position}", disabled=(current_page == 0)):
                        set_explorer_page(0)
                        st.rerun()
                with nav_cols[1]:
                    if st.button("\u2190 Prev", key=f"prev_{position}", disabled=(current_page == 0)):
                        set_explorer_page(current_page - 1)
                        st.rerun()
                with nav_cols[2]:
                    if st.button("Next \u2192", key=f"next_{position}", disabled=(current_page >= total_pages - 1)):
                        set_explorer_page(current_page + 1)
                        st.rerun()
                with nav_cols[3]:
                    if st.button("Last \u00bb", key=f"last_{position}", disabled=(current_page >= total_pages - 1)):
                        set_explorer_page(total_pages - 1)
                        st.rerun()

            # -- paginated card grid (4 per row) --
            page_df = explorer_df.iloc[start_idx:end_idx]
            for i in range(0, len(page_df), 4):
                rows_chunk = page_df.iloc[i:i+4]
                cols = st.columns(4)
                for j, (_, row) in enumerate(rows_chunk.iterrows()):
                    with cols[j]:
                        with st.container():
                            cover_path, resolved_pdf_path = resolve_cover_and_pdf_paths(row)
                            pdf_name = str(row.get("Thesis_PDF", "n/a"))
                            _row_prog_dir = _get_program_dir_for_row(row)
                            pdf_path = (os.path.join(_row_prog_dir, "pdfs", pdf_name)
                                        if pdf_name not in ("n/a", "", "nan") else "")
                            details_key = pdf_name.replace('.pdf', '') if pdf_name.endswith('.pdf') else pdf_name
                            featured_html = _featured_badge_html(bool(row.get("Featured", False)))
                            _is_featured = bool(row.get("Featured", False))

                            # In all-mode the click navigates to the source
                            # programme's URL so the detail page loads with the
                            # correct PDF / assets.
                            _row_prog_key = str(row.get("_program_key", "") or "").strip() or PROGRAM
                            card_link = (
                                f"?program={urllib.parse.quote(_row_prog_key, safe='')}&"
                                f"details={urllib.parse.quote(details_key, safe='')}"
                            )
                            _prog_badge_html = ""
                            if PROGRAM == _ALL_PROGRAM_KEY and _row_prog_key in PROGRAMME_SHORT_NAMES:
                                _prog_badge_html = (
                                    f"<div class='thesis-prog-badge'>"
                                    f"{PROGRAMME_SHORT_NAMES[_row_prog_key]}</div>"
                                )
                            card_html = (
                                f'<a href="{card_link}" class="thesis-card-link" target="_self">'
                                '<div class="thesis-card">'
                                + render_cover_html(cover_path, resolved_pdf_path or pdf_path, featured=_is_featured)
                                + f"<div class='thesis-title'>{row['Title']}</div>"
                                + f"<div class='thesis-meta'>{row['Author(s)']} &#8226; {row['Year']}</div>"
                                + _prog_badge_html
                                + '</div></a>'
                            )
                            st.markdown(card_html, unsafe_allow_html=True)

            st.markdown("---")

            # -- bottom pagination --
            render_pagination("bottom")

elif page == "Programme Analytics":
    st.markdown("### Programme Analytics")

    def _normalize_method_text(value: str) -> str:
        import re
        import unicodedata

        text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
        text = text.lower().strip()
        text = text.replace("&", " and ")
        text = text.replace("/", " ")
        text = text.replace("-", " ")
        text = re.sub(r"[^a-z0-9\s]", " ", text)

        replacements = {
            "qual ": "qualitative ",
            "quant ": "quantitative ",
            "methodologies": "methodology",
            "methods": "method",
            "studies": "study",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)

        return " ".join(text.split())

    def _pretty_method_label(value: str) -> str:
        cleaned = str(value).strip()
        if not cleaned:
            return "n/a"
        return cleaned[0].upper() + cleaned[1:]

    @st.cache_data(show_spinner=False)
    def build_methodology_map(series: pd.Series) -> dict[str, str]:
        from difflib import SequenceMatcher

        cleaned = series[series.notna()].astype(str).str.strip()
        cleaned = cleaned[~cleaned.str.lower().isin(["", "n/a", "na", "nan"])]
        if cleaned.empty:
            return {}

        raw_counts = cleaned.value_counts()
        norm_to_raws: dict[str, dict[str, int]] = {}
        for raw, count in raw_counts.items():
            norm = _normalize_method_text(raw)
            if not norm:
                continue
            norm_to_raws.setdefault(norm, {})
            norm_to_raws[norm][raw] = norm_to_raws[norm].get(raw, 0) + int(count)

        generic_tokens = {"method", "methodology", "research", "study", "approach", "empirical"}

        def likely_same_method(a: str, b: str) -> bool:
            if a == b:
                return True
            if a in b or b in a:
                return True
            a_tokens = {t for t in a.split() if t not in generic_tokens}
            b_tokens = {t for t in b.split() if t not in generic_tokens}
            if a_tokens and b_tokens:
                overlap = len(a_tokens.intersection(b_tokens)) / max(len(a_tokens), len(b_tokens))
                if overlap >= 0.8:
                    return True
            return SequenceMatcher(None, a, b).ratio() >= 0.92

        sorted_norms = sorted(
            norm_to_raws.keys(),
            key=lambda key: sum(norm_to_raws[key].values()),
            reverse=True,
        )

        clusters: list[dict[str, object]] = []
        for norm in sorted_norms:
            attached = False
            for cluster in clusters:
                representative = str(cluster["rep"])
                if likely_same_method(norm, representative):
                    cluster["members"].append(norm)
                    attached = True
                    break
            if not attached:
                clusters.append({"rep": norm, "members": [norm]})

        method_map: dict[str, str] = {}
        for cluster in clusters:
            member_norms = cluster["members"]
            all_variants: dict[str, int] = {}
            for member in member_norms:
                for raw, count in norm_to_raws[member].items():
                    all_variants[raw] = all_variants.get(raw, 0) + count

            best_raw = max(all_variants.items(), key=lambda item: item[1])[0]
            best_norm = _normalize_method_text(best_raw)

            if "mixed" in best_norm and ("method" in best_norm or "qualitative" in best_norm or "quantitative" in best_norm):
                canonical = "Mixed methods"
            elif "qualitative" in best_norm and "empirical" in best_norm:
                canonical = "Qualitative empirical research"
            elif "quantitative" in best_norm and "empirical" in best_norm:
                canonical = "Quantitative empirical research"
            else:
                canonical = _pretty_method_label(best_raw)

            for member in member_norms:
                for raw in norm_to_raws[member].keys():
                    method_map[raw] = canonical

        return method_map

    method_map = build_methodology_map(df["Methodology Type"])

    def canonical_methodology(value: str) -> str:
        if pd.isna(value):
            return "n/a"
        raw = str(value).strip()
        if not raw:
            return "n/a"
        if raw.lower() in ("n/a", "na", "nan"):
            return "n/a"
        return method_map.get(raw, _pretty_method_label(raw))

    def top_non_na(series):
        cleaned = series[series.notna()].astype(str).str.strip()
        cleaned = cleaned[cleaned.str.lower() != "n/a"]
        cleaned = cleaned[cleaned != ""]
        counts = cleaned.value_counts()
        return counts.index[0] if not counts.empty else "n/a"

    def _extract_sdg_number(sdg_text: str) -> int | None:
        import re

        match = re.match(r"^\s*(\d+)", str(sdg_text))
        if not match:
            return None
        try:
            number = int(match.group(1))
            return number if 1 <= number <= 17 else None
        except ValueError:
            return None

    def _country_flag_emoji(name: str) -> str:
        lookup = {
            "Netherlands": "🇳🇱",
            "Germany": "🇩🇪",
            "Norway": "🇳🇴",
            "Chile": "🇨🇱",
            "United States": "🇺🇸",
            "China": "🇨🇳",
            "Tanzania": "🇹🇿",
            "Poland": "🇵🇱",
            "India": "🇮🇳",
            "Turkey": "🇹🇷",
            "Belgium": "🇧🇪",
            "Finland": "🇫🇮",
            "Denmark": "🇩🇰",
            "Brazil": "🇧🇷",
            "Jordan": "🇯🇴",
            "Burkina Faso": "🇧🇫",
            "European Union": "🇪🇺",
            "EU": "🇪🇺",
        }
        return lookup.get(str(name).strip(), "🌍")

    total_theses = len(df)
    most_common_sdg = top_non_na(df["SDG"])
    most_common_sector = top_non_na(df["Main sector"])
    most_common_method = top_non_na(df["Methodology Type"].map(canonical_methodology))

    country_col = (
        "Country"
        if "Country" in df.columns
        else "Geographical location standardized"
        if "Geographical location standardized" in df.columns
        else "Geographical scope"
    )
    most_common_country = top_non_na(df[country_col])
    most_common_sdg_number = _extract_sdg_number(most_common_sdg)

    def _insight_card(title: str, value_html: str) -> None:
        st.markdown(
            f"<div class='programme-insight-card'>"
            f"<div class='programme-insight-title'>{title}</div>"
            f"<div class='programme-insight-value'>{value_html}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    top_sdg_html = "<span class='programme-insight-value-text'>n/a</span>"
    if most_common_sdg_number is not None:
        sdg_icon_path = os.path.join(PROGRAM_DIR, "sdg_icons", f"Goal-{most_common_sdg_number:02d}.png")
        sdg_b64 = _load_image_b64(sdg_icon_path)
        if sdg_b64:
            top_sdg_html = (
                f"<img src='data:image/png;base64,{sdg_b64}' class='programme-insight-sdg-icon' alt='Top SDG icon'/>"
            )
        else:
            top_sdg_html = f"<span class='programme-insight-value-text'>SDG {most_common_sdg_number}</span>"

    top_country_flag = _country_flag_emoji(most_common_country)
    top_country_html = f"<span class='programme-insight-flag'>{top_country_flag}</span>"

    st.markdown("## Programme Insights")
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        _insight_card("Total Theses", f"<span class='programme-insight-value-text'>{total_theses}</span>")

    with col2:
        _insight_card("Top SDG", top_sdg_html)

    with col3:
        _insight_card("Top Sector", f"<span class='programme-insight-value-text'>{most_common_sector}</span>")

    with col4:
        _insight_card("Top Method", f"<span class='programme-insight-value-text'>{most_common_method}</span>")

    with col5:
        _insight_card("Top Country", top_country_html)

    df_sunburst = df.copy()
    df_sunburst["SDG"] = df_sunburst["SDG"].astype(str).str.strip()
    df_sunburst["Main sector"] = df_sunburst["Main sector"].astype(str).str.strip()
    df_sunburst["Methodology Type"] = df_sunburst["Methodology Type"].map(canonical_methodology)
    df_sunburst = df_sunburst[
        df_sunburst["SDG"].str.lower().ne("n/a")
        & df_sunburst["Main sector"].str.lower().ne("n/a")
        & df_sunburst["Methodology Type"].str.lower().ne("n/a")
        & df_sunburst["SDG"].ne("")
        & df_sunburst["Main sector"].ne("")
        & df_sunburst["Methodology Type"].ne("")
    ]

    st.markdown("---")
    st.markdown("## Research Structure")
    st.markdown(
        f"This visualization shows how {_display_name} theses are structured across **SDGs, sectors, and methodologies**."
    )
    st.caption("Click on segments to explore deeper levels of the research landscape.")

    if df_sunburst.empty:
        st.info("Not enough structured data to display research structure.")
    else:
        df_sunburst = df_sunburst.copy()
        df_sunburst["_sdg_num"] = (
            df_sunburst["SDG"].astype(str).str.extract(r"^(\d+)")[0].fillna("Unknown")
        )
        sdg_color_map = {
            "1": "#E5243B",
            "2": "#DDA63A",
            "3": "#4C9F38",
            "4": "#C5192D",
            "5": "#FF3A21",
            "6": "#26BDE2",
            "7": "#FCC30B",
            "8": "#A21942",
            "9": "#FD6925",
            "10": "#DD1367",
            "11": "#FD9D24",
            "12": "#BF8B2E",
            "13": "#3F7E44",
            "14": "#0A97D9",
            "15": "#56C02B",
            "16": "#00689D",
            "17": "#19486A",
            "Unknown": "#BDBDBD",
        }

        fig = px.sunburst(
            df_sunburst,
            path=["SDG", "Main sector", "Methodology Type"],
            color="_sdg_num",
            color_discrete_map=sdg_color_map,
        )
        fig.update_layout(
            margin=dict(t=10, l=0, r=0, b=0),
            height=620,
            paper_bgcolor="white",
            plot_bgcolor="white",
        )
        fig.update_traces(
            textinfo="label+percent entry",
            insidetextorientation="radial",
        )
        with st.container():
            st.plotly_chart(fig, width='stretch')

    st.markdown("---")
    st.markdown("## Research Topic Explorer")
    st.markdown("Explore the **keyword universe** of research topics. Hover to preview related theses, click to dive deeper.")

    import re
    import numpy as np

    @st.cache_data(show_spinner=False)
    def _compute_keyword_data(df: pd.DataFrame) -> tuple:
        """Normalise, deduplicate and canonicalise all thesis keywords.

        Returns (kw_df, keyword_lookup_df):
          - kw_df: top-30 keywords with columns [keyword_norm, count, keyword]
          - keyword_lookup_df: per-row keyword index with columns
            [row_index, keyword_norm, keyword_canonical]
        """
        from collections import Counter
        from difflib import SequenceMatcher
        import re as _re

        def normalize_keyword(keyword: str) -> str:
            k = str(keyword).lower().strip()
            k = k.replace("&", " and ").replace("/", " ").replace("-", " ")
            k = _re.sub(r"[^a-z0-9\s]", " ", k)
            k = " ".join(k.split())
            replacements = {
                "behaviours": "behavior",
                "behaviour": "behavior",
                "organizations": "organization",
                "organisations": "organization",
                "smes": "sme",
                "stakeholders": "stakeholder",
                "business models": "business model",
            }
            k = replacements.get(k, k)
            if len(k) > 4 and k.endswith("ies"):
                k = k[:-3] + "y"
            elif len(k) > 4 and k.endswith("s") and not k.endswith("ss"):
                k = k[:-1]
            return k.strip()

        def pretty_keyword(keyword: str) -> str:
            if not keyword:
                return ""
            return keyword[0].upper() + keyword[1:]

        def similar_keyword(a: str, b: str) -> bool:
            if a == b:
                return True
            if a.replace(" ", "") == b.replace(" ", ""):
                return True
            if SequenceMatcher(None, a, b).ratio() >= 0.93:
                return True
            a_tokens = set(a.split())
            b_tokens = set(b.split())
            if not a_tokens or not b_tokens:
                return False
            overlap = len(a_tokens.intersection(b_tokens)) / max(len(a_tokens), len(b_tokens))
            return overlap >= 0.85 and abs(len(a) - len(b)) <= 10

        norm_keyword_counts: Counter = Counter()
        row_keyword_norm_pairs = []

        if "Keywords" in df.columns:
            for row_idx, entry in df["Keywords"].items():
                if str(entry).strip().lower() in ("", "n/a", "na", "nan"):
                    continue
                row_norm_keywords = []
                for raw_keyword in str(entry).split(","):
                    normalized = normalize_keyword(raw_keyword)
                    if normalized and normalized not in ("n/a", "na", "nan"):
                        row_norm_keywords.append(normalized)
                        norm_keyword_counts[normalized] += 1
                for unique_kw in set(row_norm_keywords):
                    row_keyword_norm_pairs.append({"row_index": row_idx, "keyword_norm": unique_kw})

        canonical_map: dict = {}
        canonical_counts: Counter = Counter()
        canonical_keys: list = []

        for norm_kw, freq in norm_keyword_counts.most_common():
            matched = None
            for canonical_kw in canonical_keys:
                if similar_keyword(norm_kw, canonical_kw):
                    matched = canonical_kw
                    break
            if matched is None:
                matched = norm_kw
                canonical_keys.append(matched)
            canonical_map[norm_kw] = matched
            canonical_counts[matched] += freq

        top_keywords = canonical_counts.most_common(30)
        kw_df = pd.DataFrame(top_keywords, columns=["keyword_norm", "count"])
        if not kw_df.empty:
            kw_df["keyword"] = kw_df["keyword_norm"].apply(pretty_keyword)

        keyword_lookup_df = pd.DataFrame(row_keyword_norm_pairs)
        if not keyword_lookup_df.empty:
            keyword_lookup_df["keyword_canonical"] = keyword_lookup_df["keyword_norm"].map(canonical_map)

        return kw_df, keyword_lookup_df

    kw_df, keyword_lookup_df = _compute_keyword_data(df)

    def get_topic_df(keyword_canonical: str) -> pd.DataFrame:
        if keyword_lookup_df.empty:
            return pd.DataFrame(columns=df.columns)
        row_indexes = keyword_lookup_df[keyword_lookup_df["keyword_canonical"] == keyword_canonical]["row_index"].unique()
        if len(row_indexes) == 0:
            return pd.DataFrame(columns=df.columns)
        return df.loc[row_indexes].copy()

    if kw_df.empty:
        st.info("No keyword data available to build the topic explorer.")
    else:
        import json as _json

        _sdg_hex = {
            1: "#E5243B", 2: "#DDA63A", 3: "#4C9F38", 4: "#C5192D",
            5: "#FF3A21", 6: "#26BDE2", 7: "#FCC30B", 8: "#A21942",
            9: "#FD6925", 10: "#DD1367", 11: "#FD9D24", 12: "#BF8B2E",
            13: "#3F7E44", 14: "#0A97D9", 15: "#56C02B", 16: "#00689D",
            17: "#19486A",
        }

        def _lighten_hex(hx: str, amount: float = 0.35) -> str:
            hx = hx.lstrip("#")
            rv, gv, bv = int(hx[:2], 16), int(hx[2:4], 16), int(hx[4:6], 16)
            rv = min(255, int(rv + (255 - rv) * amount))
            gv = min(255, int(gv + (255 - gv) * amount))
            bv = min(255, int(bv + (255 - bv) * amount))
            return f"#{rv:02x}{gv:02x}{bv:02x}"

        keyword_data = []
        for _, kw_row in kw_df.iterrows():
            topic_theses = get_topic_df(kw_row["keyword_norm"])
            theses = []
            sdg_counter: dict[str, int] = {}
            for _, t in topic_theses.iterrows():
                sdg_raw = str(t.get("SDG", ""))
                theses.append({
                    "title": str(t.get("Title", "")),
                    "author": str(t.get("Author(s)", "")),
                    "year": str(t.get("Year", "")),
                    "sdg": sdg_raw,
                    "sector": str(t.get("Main sector", "")),
                })
                m = re.match(r"(\d+)", sdg_raw)
                if m:
                    sdg_counter[m.group(1)] = sdg_counter.get(m.group(1), 0) + 1
            primary_sdg_num = int(max(sdg_counter, key=sdg_counter.get)) if sdg_counter else None
            base_color = _sdg_hex.get(primary_sdg_num, "#003660") if primary_sdg_num else "#003660"
            keyword_data.append({
                "keyword": kw_row["keyword"],
                "count": int(kw_row["count"]),
                "color": base_color,
                "colorLight": _lighten_hex(base_color),
                "theses": theses,
            })

        # co-occurrence links among top-30 keywords
        top_kw_set = set(kw_df["keyword_norm"].tolist())
        co_occur_list: list[dict] = []
        if not keyword_lookup_df.empty:
            thesis_kws = keyword_lookup_df.groupby("row_index")["keyword_canonical"].apply(set).to_dict()
            co_counts: dict[tuple, int] = {}
            for kw_set in thesis_kws.values():
                relevant = sorted(kw_set.intersection(top_kw_set))
                for i_a, a in enumerate(relevant):
                    for b in relevant[i_a + 1:]:
                        co_counts[(a, b)] = co_counts.get((a, b), 0) + 1
            n2p = dict(zip(kw_df["keyword_norm"], kw_df["keyword"]))
            co_occur_list = [
                {"source": n2p.get(a, a), "target": n2p.get(b, b), "count": c}
                for (a, b), c in co_counts.items() if c >= 2
            ]

        data_json = _json.dumps({"keywords": keyword_data, "links": co_occur_list}, ensure_ascii=False)

        _te_css = (
            "* { box-sizing: border-box; margin: 0; padding: 0; }"
            "body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; overflow: hidden; }"
            "#te-container {"
            "  position: relative; width: 100%; height: 700px;"
            "  background: linear-gradient(135deg, #0B1929 0%, #0F2337 50%, #132D46 100%);"
            "  border-radius: 16px; overflow: hidden;"
            "}"
            "#te-container::before {"
            "  content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0;"
            "  background-image: radial-gradient(circle at 1px 1px, rgba(255,255,255,0.03) 1px, transparent 0);"
            "  background-size: 40px 40px; pointer-events: none; z-index: 0;"
            "}"
            "#te-search {"
            "  position: absolute; top: 16px; left: 0; right: 0; text-align: center; z-index: 10;"
            "}"
            "#te-search input {"
            "  width: 260px; padding: 10px 18px;"
            "  border: 1px solid rgba(255,255,255,0.12); border-radius: 24px;"
            "  background: rgba(255,255,255,0.06); color: #fff; font-size: 13px;"
            "  outline: none; backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);"
            "  transition: all 0.3s ease;"
            "}"
            "#te-search input:focus {"
            "  border-color: rgba(255,205,0,0.4); box-shadow: 0 0 24px rgba(255,205,0,0.1); width: 320px;"
            "}"
            "#te-search input::placeholder { color: rgba(255,255,255,0.35); }"
            "#te-hint {"
            "  position: absolute; bottom: 14px; left: 0; right: 0; text-align: center;"
            "  color: rgba(255,255,255,0.25); font-size: 11px; z-index: 10;"
            "  pointer-events: none; transition: opacity 0.3s;"
            "}"
            ".te-bubble {"
            "  position: absolute; border-radius: 50%;"
            "  display: flex; align-items: center; justify-content: center;"
            "  cursor: pointer; text-align: center; user-select: none; z-index: 2;"
            "  opacity: 0; transform: scale(0);"
            "  animation: bubbleIn 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;"
            "  transition: box-shadow 0.3s, filter 0.3s;"
            "}"
            "@keyframes bubbleIn { to { opacity: 1; transform: scale(1); } }"
            ".te-bubble:hover { z-index: 5 !important; filter: brightness(1.15); }"
            ".te-bubble.selected { z-index: 6 !important; filter: brightness(1.2); }"
            ".te-bubble.dimmed { opacity: 0.12 !important; pointer-events: none; }"
            ".te-bubble-label {"
            "  color: #fff; font-weight: 600; line-height: 1.15;"
            "  text-shadow: 0 1px 4px rgba(0,0,0,0.5); pointer-events: none;"
            "  padding: 6px; overflow: hidden;"
            "  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;"
            "  max-width: 90%;"
            "}"
            ".te-bubble-count {"
            "  position: absolute; top: -4px; right: -2px;"
            "  background: rgba(255,205,0,0.92); color: #0B1929;"
            "  border-radius: 10px; font-size: 9px; font-weight: 700;"
            "  padding: 2px 6px; min-width: 16px; text-align: center;"
            "  opacity: 0; transform: scale(0.7);"
            "  transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);"
            "}"
            ".te-bubble:hover .te-bubble-count,"
            ".te-bubble.selected .te-bubble-count { opacity: 1; transform: scale(1); }"
            "#te-lines {"
            "  position: absolute; top: 0; left: 0; width: 100%; height: 100%;"
            "  pointer-events: none; z-index: 1;"
            "}"
            "#te-lines line { stroke-dasharray: 4 4; animation: dashMove 1s linear infinite; }"
            "@keyframes dashMove { to { stroke-dashoffset: -8; } }"
            "#te-tooltip {"
            "  position: absolute; z-index: 30;"
            "  background: rgba(11, 25, 41, 0.97);"
            "  border: 1px solid rgba(255,255,255,0.1); border-radius: 12px;"
            "  padding: 16px; min-width: 250px; max-width: 340px;"
            "  pointer-events: none; opacity: 0; transform: translateY(4px);"
            "  transition: opacity 0.2s, transform 0.2s;"
            "  backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);"
            "  box-shadow: 0 8px 32px rgba(0,0,0,0.5);"
            "}"
            "#te-tooltip.visible { opacity: 1; transform: translateY(0); }"
            ".tt-keyword { color: #fff; font-size: 15px; font-weight: 700; margin-bottom: 2px; }"
            ".tt-count { color: rgba(255,205,0,0.9); font-size: 12px; font-weight: 600; margin-bottom: 10px; }"
            ".tt-divider { height: 1px; background: rgba(255,255,255,0.08); margin: 8px 0; }"
            ".tt-thesis {"
            "  color: rgba(255,255,255,0.65); font-size: 12px; padding: 4px 0;"
            "  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; line-height: 1.4;"
            "}"
            ".tt-thesis::before { content: '\\2192  '; color: rgba(255,205,0,0.5); }"
            ".tt-more { color: rgba(255,205,0,0.6); font-size: 11px; margin-top: 6px; font-style: italic; }"
            "#te-detail {"
            "  position: absolute; bottom: 0; left: 0; right: 0;"
            "  background: linear-gradient(to top, rgba(11,25,41,0.99), rgba(15,35,55,0.97));"
            "  border-top: 1px solid rgba(255,255,255,0.1);"
            "  border-radius: 16px 16px 0 0; padding: 24px 28px;"
            "  transform: translateY(100%);"
            "  transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);"
            "  overflow-y: auto; max-height: 60%; z-index: 20;"
            "  backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);"
            "}"
            "#te-detail.open { transform: translateY(0); }"
            "#te-detail-close {"
            "  position: absolute; top: 14px; right: 18px;"
            "  background: rgba(255,255,255,0.08); border: none;"
            "  color: rgba(255,255,255,0.5); font-size: 18px;"
            "  width: 32px; height: 32px; border-radius: 50%;"
            "  cursor: pointer; display: flex; align-items: center; justify-content: center;"
            "  transition: all 0.2s;"
            "}"
            "#te-detail-close:hover { background: rgba(255,255,255,0.15); color: #fff; }"
            ".detail-header { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }"
            ".detail-header h3 { color: #fff; font-size: 18px; font-weight: 700; }"
            ".detail-count-badge {"
            "  background: rgba(255,205,0,0.15); color: #FFCD00;"
            "  padding: 4px 14px; border-radius: 12px; font-size: 12px; font-weight: 600;"
            "}"
            ".detail-related { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; }"
            ".detail-related-label { color: rgba(255,255,255,0.35); font-size: 11px; margin-right: 4px; }"
            ".detail-related-pill {"
            "  background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.6);"
            "  padding: 4px 12px; border-radius: 12px; font-size: 11px;"
            "  cursor: pointer; transition: all 0.2s; border: 1px solid rgba(255,255,255,0.06);"
            "}"
            ".detail-related-pill:hover {"
            "  background: rgba(255,205,0,0.12); color: #FFCD00; border-color: rgba(255,205,0,0.2);"
            "}"
            ".te-thesis-grid {"
            "  display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 10px;"
            "}"
            ".te-thesis-card {"
            "  background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.06);"
            "  border-radius: 10px; padding: 14px; transition: all 0.2s;"
            "}"
            ".te-thesis-card:hover {"
            "  background: rgba(255,255,255,0.07); border-color: rgba(255,205,0,0.15);"
            "  transform: translateY(-1px);"
            "}"
            ".te-thesis-title {"
            "  color: #fff; font-size: 12.5px; font-weight: 600; line-height: 1.35; margin-bottom: 6px;"
            "  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;"
            "}"
            ".te-thesis-meta { color: rgba(255,255,255,0.4); font-size: 11px; margin-bottom: 4px; }"
            ".te-thesis-sdg {"
            "  display: inline-block; padding: 2px 8px; border-radius: 6px;"
            "  font-size: 10px; font-weight: 600; margin-top: 4px;"
            "}"
        )

        _te_body = (
            '<div id="te-container">'
            '<div id="te-search"><input type="text" id="te-search-input" placeholder="Search keywords..." autocomplete="off" /></div>'
            '<svg id="te-lines"></svg>'
            '<div id="te-bubbles"></div>'
            '<div id="te-tooltip"></div>'
            '<div id="te-detail"></div>'
            '<div id="te-hint">Hover to preview \u00b7 Click to explore \u00b7 Search to filter</div>'
            '</div>'
        )

        _te_js = (
            'var SDG_HEX={1:"#E5243B",2:"#DDA63A",3:"#4C9F38",4:"#C5192D",5:"#FF3A21",6:"#26BDE2",7:"#FCC30B",8:"#A21942",9:"#FD6925",10:"#DD1367",11:"#FD9D24",12:"#BF8B2E",13:"#3F7E44",14:"#0A97D9",15:"#56C02B",16:"#00689D",17:"#19486A"};'
            'var container=document.getElementById("te-container");'
            'var bubblesEl=document.getElementById("te-bubbles");'
            'var linesEl=document.getElementById("te-lines");'
            'var tooltip=document.getElementById("te-tooltip");'
            'var detail=document.getElementById("te-detail");'
            'var hint=document.getElementById("te-hint");'
            'var searchInput=document.getElementById("te-search-input");'
            'var W=container.clientWidth,H=container.clientHeight;'
            'var linkMap={};'
            'DATA.links.forEach(function(l){'
            '  if(!linkMap[l.source])linkMap[l.source]=[];'
            '  if(!linkMap[l.target])linkMap[l.target]=[];'
            '  linkMap[l.source].push({name:l.target,count:l.count});'
            '  linkMap[l.target].push({name:l.source,count:l.count});'
            '});'
            'var maxC=Math.max.apply(null,DATA.keywords.map(function(k){return k.count}));'
            'var minC=Math.min.apply(null,DATA.keywords.map(function(k){return k.count}));'
            'var nodes=DATA.keywords.map(function(kw,i){'
            '  var t=maxC>minC?(kw.count-minC)/(maxC-minC):0.5;'
            '  var r=26+Math.sqrt(t)*36;'
            '  return {keyword:kw.keyword,count:kw.count,color:kw.color,colorLight:kw.colorLight,theses:kw.theses,r:r,x:0,y:0,vx:0,vy:0,i:i,el:null};'
            '});'
            'nodes.forEach(function(n,i){'
            '  var angle=i*2.399963;'
            '  var rad=50+Math.sqrt(i/Math.max(1,nodes.length-1))*Math.min(W,H)*0.32;'
            '  n.x=W/2+rad*Math.cos(angle);n.y=H/2+rad*Math.sin(angle);'
            '});'
            'for(var iter=0;iter<350;iter++){'
            '  for(var ni=0;ni<nodes.length;ni++){nodes[ni].vx+=(W/2-nodes[ni].x)*0.004;nodes[ni].vy+=(H/2-nodes[ni].y)*0.004;}'
            '  for(var i=0;i<nodes.length;i++){'
            '    for(var j=i+1;j<nodes.length;j++){'
            '      var dx=nodes[j].x-nodes[i].x,dy=nodes[j].y-nodes[i].y;'
            '      var dist=Math.sqrt(dx*dx+dy*dy)||1;'
            '      var minD=nodes[i].r+nodes[j].r+5;'
            '      if(dist<minD){var f=(minD-dist)/dist*0.3;nodes[i].vx-=dx*f;nodes[i].vy-=dy*f;nodes[j].vx+=dx*f;nodes[j].vy+=dy*f;}'
            '    }'
            '  }'
            '  for(var ni2=0;ni2<nodes.length;ni2++){'
            '    nodes[ni2].vx*=0.82;nodes[ni2].vy*=0.82;'
            '    nodes[ni2].x+=nodes[ni2].vx;nodes[ni2].y+=nodes[ni2].vy;'
            '    nodes[ni2].x=Math.max(nodes[ni2].r+8,Math.min(W-nodes[ni2].r-8,nodes[ni2].x));'
            '    nodes[ni2].y=Math.max(nodes[ni2].r+55,Math.min(H-nodes[ni2].r-8,nodes[ni2].y));'
            '  }'
            '}'
            'function esc(text){var d=document.createElement("div");d.textContent=String(text||"");return d.innerHTML;}'
            'nodes.forEach(function(n,idx){'
            '  var el=document.createElement("div");el.className="te-bubble";'
            '  var fontSize=Math.max(8,Math.min(14,n.r*0.26));'
            '  el.style.cssText="left:"+(n.x-n.r)+"px;top:"+(n.y-n.r)+"px;width:"+(n.r*2)+"px;height:"+(n.r*2)+"px;"'
            '    +"background:radial-gradient(circle at 35% 30%,"+n.colorLight+","+n.color+");"'
            '    +"box-shadow:0 4px 20px "+n.color+"55,inset 0 -4px 10px rgba(0,0,0,0.25);"'
            '    +"animation-delay:"+(idx*0.035)+"s;";'
            '  el.innerHTML=\'<span class="te-bubble-label" style="font-size:\'+fontSize+\'px">\'+esc(n.keyword)+\'</span>\'+'
            '    \'<span class="te-bubble-count">\'+n.count+\'</span>\';'
            '  el.addEventListener("mouseenter",function(){onBubbleEnter(n,el);});'
            '  el.addEventListener("mouseleave",function(){onBubbleLeave();});'
            '  el.addEventListener("click",function(){onBubbleClick(n);});'
            '  bubblesEl.appendChild(el);n.el=el;'
            '});'
            'function onBubbleEnter(node,el){'
            '  showLinks(node);'
            '  var html=\'<div class="tt-keyword">\'+esc(node.keyword)+\'</div>\';'
            '  html+=\'<div class="tt-count">\'+node.count+\' thesis mentions</div>\';'
            '  html+=\'<div class="tt-divider"></div>\';'
            '  var maxShow=4;'
            '  for(var i=0;i<Math.min(maxShow,node.theses.length);i++){'
            '    html+=\'<div class="tt-thesis">\'+esc(node.theses[i].title)+\'</div>\';'
            '  }'
            '  if(node.theses.length>maxShow){'
            '    html+=\'<div class="tt-more">+ \'+(node.theses.length-maxShow)+\' more \\u2014 click to explore</div>\';'
            '  }'
            '  tooltip.innerHTML=html;'
            '  var bRect=el.getBoundingClientRect(),cRect=container.getBoundingClientRect();'
            '  var left=bRect.right-cRect.left+12,top=bRect.top-cRect.top-10;'
            '  if(left+350>W)left=bRect.left-cRect.left-350;'
            '  if(left<10)left=10;if(top+250>H)top=H-260;if(top<10)top=10;'
            '  tooltip.style.left=left+"px";tooltip.style.top=top+"px";'
            '  tooltip.classList.add("visible");'
            '}'
            'function onBubbleLeave(){tooltip.classList.remove("visible");clearLinks();}'
            'function showLinks(node){'
            '  clearLinks();'
            '  var connected=linkMap[node.keyword]||[];'
            '  connected.forEach(function(link){'
            '    var target=null;for(var i=0;i<nodes.length;i++){if(nodes[i].keyword===link.name){target=nodes[i];break;}}'
            '    if(!target)return;'
            '    var line=document.createElementNS("http://www.w3.org/2000/svg","line");'
            '    line.setAttribute("x1",node.x);line.setAttribute("y1",node.y);'
            '    line.setAttribute("x2",target.x);line.setAttribute("y2",target.y);'
            '    line.setAttribute("stroke","rgba(255,205,0,0.25)");line.setAttribute("stroke-width","1.5");'
            '    linesEl.appendChild(line);'
            '    target.el.style.boxShadow="0 0 25px "+target.color+"88,0 0 50px "+target.color+"44";'
            '  });'
            '  node.el.style.boxShadow="0 0 30px "+node.color+"aa,0 0 60px "+node.color+"66";'
            '}'
            'function clearLinks(){'
            '  linesEl.innerHTML="";'
            '  nodes.forEach(function(n){n.el.style.boxShadow="0 4px 20px "+n.color+"55,inset 0 -4px 10px rgba(0,0,0,0.25)";});'
            '}'
            'var selectedNode=null;'
            'function onBubbleClick(node){'
            '  tooltip.classList.remove("visible");clearLinks();'
            '  document.querySelectorAll(".te-bubble.selected").forEach(function(el){el.classList.remove("selected");});'
            '  node.el.classList.add("selected");selectedNode=node;hint.style.opacity="0";'
            '  var connected=linkMap[node.keyword]||[];'
            '  connected.sort(function(a,b){return b.count-a.count;});'
            '  var html=\'<button id="te-detail-close">\\u2715</button>\';'
            '  html+=\'<div class="detail-header"><h3>\'+esc(node.keyword)+\'</h3>\';'
            '  html+=\'<span class="detail-count-badge">\'+node.theses.length+\' theses</span></div>\';'
            '  if(connected.length>0){'
            '    html+=\'<div class="detail-related"><span class="detail-related-label">Co-occurring keywords:</span>\';'
            '    connected.slice(0,8).forEach(function(c){'
            '      var tidx=-1;for(var i=0;i<nodes.length;i++){if(nodes[i].keyword===c.name){tidx=i;break;}}'
            '      if(tidx>=0)html+=\'<span class="detail-related-pill" data-idx="\'+tidx+\'">\'+esc(c.name)+\' (\'+c.count+\')</span>\';'
            '    });'
            '    html+="</div>";'
            '  }'
            '  html+=\'<div class="te-thesis-grid">\';'
            '  node.theses.forEach(function(t){'
            '    var sdgMatch=t.sdg?t.sdg.match(/^(\\d+)/):null;'
            '    var sdgNum=sdgMatch?parseInt(sdgMatch[1]):null;'
            '    var sdgColor=sdgNum&&SDG_HEX[sdgNum]?SDG_HEX[sdgNum]:"#666";'
            '    html+=\'<div class="te-thesis-card">\';'
            '    html+=\'<div class="te-thesis-title">\'+esc(t.title)+\'</div>\';'
            '    html+=\'<div class="te-thesis-meta">\'+esc(t.author)+\' \\u00b7 \'+esc(t.year)+\'</div>\';'
            '    if(t.sdg&&t.sdg!=="nan"&&t.sdg!=="n/a"&&t.sdg.trim()){'
            '      html+=\'<span class="te-thesis-sdg" style="background:\'+sdgColor+\'22;color:\'+sdgColor+\'">SDG \'+esc(t.sdg)+\'</span>\';'
            '    }'
            '    html+="</div>";'
            '  });'
            '  html+="</div>";'
            '  detail.innerHTML=html;detail.classList.add("open");'
            '}'
            'detail.addEventListener("click",function(e){'
            '  if(e.target.closest("#te-detail-close")){'
            '    detail.classList.remove("open");'
            '    document.querySelectorAll(".te-bubble.selected").forEach(function(el){el.classList.remove("selected");});'
            '    selectedNode=null;hint.style.opacity="1";return;'
            '  }'
            '  var pill=e.target.closest(".detail-related-pill");'
            '  if(pill){var idx=parseInt(pill.getAttribute("data-idx"));'
            '    if(!isNaN(idx)&&idx>=0&&idx<nodes.length)onBubbleClick(nodes[idx]);'
            '  }'
            '});'
            'searchInput.addEventListener("input",function(e){'
            '  var q=e.target.value.toLowerCase().trim();'
            '  nodes.forEach(function(n){'
            '    if(!q||n.keyword.toLowerCase().indexOf(q)!==-1){n.el.classList.remove("dimmed");}else{n.el.classList.add("dimmed");}'
            '  });'
            '});'
        )

        full_html = "<style>" + _te_css + "</style>" + _te_body + "<script>var DATA=" + data_json + ";" + _te_js + "</script>"
        _render_html_iframe(full_html, height=720)


    st.markdown("## Knowledge Network")
    with st.container():
        network_path = os.path.join(PROGRAM_DIR, "network", "network.html")

        if os.path.exists(network_path):
            st.caption("Interactive thesis network embedded in Programme Analytics.")

            html_content = _load_html_file(network_path)

            _render_html_iframe(html_content, height=800)
        else:
            st.info("Knowledge network is not yet available for this programme.")

    st.markdown("### SDG distribution")
    fig1 = px.bar(df["SDG"].value_counts(), labels={'index':'SDG','value':'Count'})
    st.plotly_chart(fig1, width='stretch')
    st.markdown("### Sector distribution")
    fig2 = px.bar(df["Main sector"].value_counts(), labels={'index':'Sector','value':'Count'})
    st.plotly_chart(fig2, width='stretch')
    st.markdown("### Methodology types")
    fig3 = px.bar(df["Methodology Type"].value_counts(), labels={'index':'Methodology','value':'Count'})
    st.plotly_chart(fig3, width='stretch')
    st.markdown("### Theories used")
    fig4 = px.bar(df["Theories"].value_counts(), labels={'index':'Theory','value':'Count'})
    st.plotly_chart(fig4, width='stretch')

elif page == "Insights" and PROGRAM == _ALL_PROGRAM_KEY:
    # Insights is computed per-programme; gracefully redirect users in all-mode.
    st.markdown(
        "<div style='padding:32px 8px;'>"
        "<h3 style='color:var(--uu-blue);margin-bottom:8px;'>Insights are per-programme</h3>"
        "<p style='color:rgba(0,54,96,0.7);max-width:640px;'>"
        "The Insights view aggregates one programme at a time. "
        "Pick a programme below to dive into its analytics."
        "</p>"
        "<div style='display:flex;flex-wrap:wrap;gap:10px;margin-top:14px;'>"
        + "".join(
            f"<a href='?program={k}&nav=Insights' target='_top' class='topnav-link'>{n}</a>"
            for k, n in PROGRAMME_DISPLAY_NAMES_SINGLE.items()
        )
        + "</div></div>",
        unsafe_allow_html=True,
    )

elif page == "Insights":
    import re as _ins_re
    import json as _ins_json
    import math as _ins_math
    import base64 as _ins_b64
    from collections import Counter as _ins_Counter

    # ── helpers ───────────────────────────────────────────────────────────
    _INS_SDG_HEX = {
        1:"#E5243B",2:"#DDA63A",3:"#4C9F38",4:"#C5192D",5:"#FF3A21",
        6:"#26BDE2",7:"#FCC30B",8:"#A21942",9:"#FD6925",10:"#DD1367",
        11:"#FD9D24",12:"#BF8B2E",13:"#3F7E44",14:"#0A97D9",15:"#56C02B",
        16:"#00689D",17:"#19486A",
    }
    _INS_SDG_NAMES = {
        1:"No Poverty",2:"Zero Hunger",3:"Good Health",4:"Quality Education",
        5:"Gender Equality",6:"Clean Water",7:"Affordable Energy",8:"Decent Work",
        9:"Industry & Innovation",10:"Reduced Inequalities",
        11:"Sustainable Cities",12:"Responsible Consumption",13:"Climate Action",
        14:"Life Below Water",15:"Life on Land",16:"Peace & Justice",
        17:"Partnerships",
    }
    # Brief plain-language descriptions of each UN Sustainable Development Goal.
    # Shown in the per-SDG detail modal so users understand what the goal covers
    # before they explore the linked theses.
    _INS_SDG_DESCRIPTIONS = {
        1:  "End poverty in all its forms everywhere — including extreme poverty, by ensuring social protection, equal economic rights, and resilience for the poor and vulnerable.",
        2:  "End hunger, achieve food security and improved nutrition, and promote sustainable agriculture that doubles productivity for small-scale food producers.",
        3:  "Ensure healthy lives and promote well-being for all at all ages — reducing maternal and child mortality, fighting epidemics, and providing universal health coverage.",
        4:  "Ensure inclusive and equitable quality education and promote lifelong learning opportunities, including technical, vocational and tertiary education for everyone.",
        5:  "Achieve gender equality and empower all women and girls, ending discrimination, violence, harmful practices, and unequal participation in leadership.",
        6:  "Ensure availability and sustainable management of water and sanitation for all — covering access, water quality, efficiency, and integrated water-resources management.",
        7:  "Ensure access to affordable, reliable, sustainable and modern energy for all, expanding renewable sources and doubling the global rate of energy efficiency improvement.",
        8:  "Promote sustained, inclusive and sustainable economic growth, full and productive employment, and decent work for all — while decoupling growth from environmental degradation.",
        9:  "Build resilient infrastructure, promote inclusive and sustainable industrialization, and foster innovation — including upgrading industries and expanding research and development.",
        10: "Reduce inequality within and among countries by empowering social, economic and political inclusion regardless of age, sex, disability, race, ethnicity, origin, religion, or status.",
        11: "Make cities and human settlements inclusive, safe, resilient and sustainable — improving housing, transport, urban planning, cultural heritage, and air quality.",
        12: "Ensure sustainable consumption and production patterns — efficient use of resources, sustainable management of chemicals and waste, and corporate sustainability reporting.",
        13: "Take urgent action to combat climate change and its impacts — integrating climate measures into policy, strengthening resilience, and supporting climate finance.",
        14: "Conserve and sustainably use the oceans, seas and marine resources — reducing marine pollution, protecting ecosystems, and ending overfishing and destructive fishing practices.",
        15: "Protect, restore and promote sustainable use of terrestrial ecosystems — managing forests, combating desertification, halting biodiversity loss, and stopping land degradation.",
        16: "Promote peaceful and inclusive societies for sustainable development, provide access to justice for all, and build effective, accountable and inclusive institutions at all levels.",
        17: "Strengthen the means of implementation and revitalize the global partnership for sustainable development — through finance, technology, capacity building, trade, and policy coherence.",
    }
    _INS_METHOD_HEX = {
        "Qualitative Empirical Research":  "#003660",
        "Mixed Methods Research":          "#FFCD00",
        "Quantitative Empirical Research": "#0a97d9",
        "Literature-Based Research":       "#4C9F38",
        "Modelling & Systems Approaches":  "#FD6925",
        "Spatial & Environmental Analysis":"#DD1367",
        "Conceptual & Theoretical":        "#9B59B6",
        "Participatory & Action-Oriented Research":"#BF8B2E",
    }
    _INS_SECTOR_HEX = {
        "Energy & Climate":              "#FCC30B",
        "Circular Economy & Production": "#4C9F38",
        "Governance & Policy":           "#003660",
        "Ecology & Biodiversity":        "#56C02B",
        "Urban & Regional Development":  "#FD6925",
        "Social Justice & Equity":       "#DD1367",
        "Water Management":              "#26BDE2",
        "Health & Medicine":             "#E5243B",
        "Food & Agriculture":            "#DDA63A",
        "Transport & Mobility":          "#9B59B6",
    }

    # ── org domain map for Clearbit logo API ─────────────────────────────
    _ORG_DOMAIN = {
        "TNO": "tno.nl",
        "Shell": "shell.com",
        "Arcadis": "arcadis.com",
        "Eneco": "eneco.nl",
        "Heineken N.V.": "heineken.com",
        "PricewaterhouseCoopers": "pwc.com",
        "Fairphone B.V.": "fairphone.com",
        "ENGIE": "engie.com",
        "Royal HaskoningDHV": "royalhaskoningdhv.com",
        "Deltares": "deltares.nl",
        "Alliander": "alliander.com",
        "Stedin": "stedin.net",
        "KWR Water Research Institute": "kwrwater.nl",
        "Rijkswaterstaat": "rijkswaterstaat.nl",
        "Unilever": "unilever.com",
        "PBL Netherlands Environmental Assessment Agency": "pbl.nl",
        "Utrecht University": "uu.nl",
        "Jacobs Douwe Egberts": "jdecoffee.com",
        "Gemeente Utrecht": "utrecht.nl",
        "KLM Engineering & Maintenance": "klm.com",
        "Circle Economy": "circle-economy.com",
        "SINTEF": "sintef.no",
        "Dialogic": "dialogic.nl",
        "Tata Steel Nederland": "tatasteeleurope.com",
        "Guidehouse": "guidehouse.com",
        "European Commission's RIPEET project": "ec.europa.eu",
        "Sociaal-Economische Raad": "ser.nl",
        "Ministry of Infrastructure and Water Management": "government.nl",
        "Ministry of the Interior and Kingdom Relations": "government.nl",
        "Rijksdienst voor Ondernemend Nederland (RVO)": "rvo.nl",
        "Global Center on Adaptation": "gca.org",
        "WASTE": "wasteconsultants.nl",
        "Fashion for Good": "fashionforgood.com",
        "Hoogheemraadschap De Stichtse Rijnlanden": "hdsr.nl",
        "Commown": "commown.coop",
        "Impact Hub Amsterdam": "amsterdam.impacthub.net",
        "Rotterdam The Hague Airport": "rotterdamthehagueairport.nl",
        "Copper8": "copper8.com",
        "KIM Netherlands Institute for Transport Policy Analysis": "kimnet.nl",
        "Natuur en Milieufederatie Utrecht": "natuurenmilieuutrecht.nl",
        "Nederlandse Publieke Omroep": "npo.nl",
        "Rabo Partnerships": "rabobank.com",
        "FairClimateFund": "fairclimatefund.org",
        "BirdLife Netherlands": "vogelbescherming.nl",
        "Gray Label": "graylabel.com",
        "Groendus": "groendus.nl",
        "Energie Samen": "energiesamen.nl",
        "Heerema Marine Contractors": "heerema.com",
        "FlexiDAO": "flexidao.com",
        "Mercator Research Institute on Global Commons and Climate Change (MCC)": "mcc-berlin.net",
        "Trouw Nutrition": "trouwnutrition.com",
    }

    # ── compute insights data ─────────────────────────────────────────────

    @st.cache_data(show_spinner=False)
    def _compute_insights(df: pd.DataFrame, program: str):
        # SDG universe — for each SDG number we capture richer per-thesis info
        # AND aggregate counters (sectors, methods, theories, supervisors,
        # year trend, co-occurring SDGs) so the click-through modal can
        # surface meaningful context, not just a flat thesis list.
        sdg_counts = _ins_Counter()
        sdg_theses: dict = {}
        sdg_sectors: dict[int, _ins_Counter] = {}
        sdg_methods: dict[int, _ins_Counter] = {}
        sdg_theories: dict[int, _ins_Counter] = {}
        sdg_supervisors: dict[int, _ins_Counter] = {}
        sdg_countries: dict[int, _ins_Counter] = {}
        sdg_year_counts: dict[int, _ins_Counter] = {}
        sdg_cooccur: dict[int, _ins_Counter] = {}

        def _clean(value) -> str:
            text = str(value).strip()
            return "" if text.lower() in ("", "n/a", "nan") else text

        def _split_multi(value) -> list[str]:
            txt = str(value)
            parts: list[str] = []
            for chunk in txt.replace(";", ",").split(","):
                c = chunk.strip()
                if c and c.lower() not in ("n/a", "nan"):
                    parts.append(c)
            return parts

        def _all_sdg_nums(value) -> list[int]:
            return [int(m) for m in _ins_re.findall(r'\d+', str(value)) if 1 <= int(m) <= 17]

        for _, row in df.iterrows():
            sdg_nums = _all_sdg_nums(row.get("SDG", ""))
            if not sdg_nums:
                continue
            primary = sdg_nums[0]
            sdg_counts[primary] += 1

            title = _clean(row.get("Title", ""))
            author = _clean(row.get("Author(s)", ""))
            year = _clean(row.get("Year", ""))
            pdf = _clean(row.get("Thesis_PDF", ""))
            sector = _clean(row.get("Main sector", ""))
            supervisor = _clean(row.get("Supervisor", ""))
            second_reader = _clean(row.get("Second reader", row.get("Second Reader", "")))
            methods = _split_multi(row.get("Methodology Type", ""))
            theories = _split_multi(row.get("Theories", ""))
            countries = _split_multi(row.get("Country", row.get("Geographical scope", "")))
            featured = bool(row.get("Featured", False))

            sdg_theses.setdefault(primary, []).append({
                "title": title,
                "author": author,
                "year": year,
                "pdf": pdf,
                "sector": sector,
                "supervisor": supervisor,
                "methods": methods,
                "featured": featured,
            })

            # Aggregate against the primary SDG (counts) and all listed SDGs
            # (co-occurrence so users can see which goals travel together).
            for n in set(sdg_nums):
                if sector:
                    sdg_sectors.setdefault(n, _ins_Counter())[sector] += 1
                for m in methods:
                    sdg_methods.setdefault(n, _ins_Counter())[m] += 1
                for t in theories:
                    sdg_theories.setdefault(n, _ins_Counter())[t] += 1
                if supervisor:
                    sdg_supervisors.setdefault(n, _ins_Counter())[supervisor] += 1
                if second_reader and second_reader != supervisor:
                    sdg_supervisors.setdefault(n, _ins_Counter())[second_reader] += 1
                for c in countries:
                    sdg_countries.setdefault(n, _ins_Counter())[c] += 1
                if year:
                    sdg_year_counts.setdefault(n, _ins_Counter())[year] += 1
                for other in sdg_nums:
                    if other != n:
                        sdg_cooccur.setdefault(n, _ins_Counter())[other] += 1

        def _top_items(counter: _ins_Counter, k: int = 6) -> list[list]:
            return [[name, int(cnt)] for name, cnt in counter.most_common(k)]

        sdg_aggregates: dict[int, dict] = {}
        for n in range(1, 18):
            sdg_aggregates[n] = {
                "top_sectors":     _top_items(sdg_sectors.get(n, _ins_Counter()), 6),
                "top_methods":     _top_items(sdg_methods.get(n, _ins_Counter()), 6),
                "top_theories":    _top_items(sdg_theories.get(n, _ins_Counter()), 6),
                "top_supervisors": _top_items(sdg_supervisors.get(n, _ins_Counter()), 6),
                "top_countries":   _top_items(sdg_countries.get(n, _ins_Counter()), 5),
                "year_counts":     {str(y): int(c) for y, c in sdg_year_counts.get(n, _ins_Counter()).items()},
                "co_sdgs":         _top_items(sdg_cooccur.get(n, _ins_Counter()), 5),
            }

        # Internship org universe
        org_theses: dict = {}
        for _, row in df.iterrows():
            org = str(row.get("Internship Organization", "")).strip()
            if org and org.lower() not in ("n/a", "nan", ""):
                for o in org.split(";"):
                    o = o.strip()
                    if o and o.lower() not in ("n/a", "nan", ""):
                        org_theses.setdefault(o, []).append({
                            "title": str(row.get("Title", "")),
                            "author": str(row.get("Author(s)", "")),
                            "year": str(row.get("Year", "")),
                            "sdg": str(row.get("SDG", "")),
                            "sector": str(row.get("Main sector", "")),
                            "pdf": str(row.get("Thesis_PDF", "")),
                        })

        # Country counts + theses
        country_counts = _ins_Counter()
        country_theses: dict = {}
        for _, row in df.iterrows():
            for c in str(row.get("Country", "")).split(";"):
                c = c.strip()
                if c and c.lower() not in ("n/a", "nan", ""):
                    country_counts[c] += 1
                    country_theses.setdefault(c, []).append({
                        "title": str(row.get("Title", "")),
                        "author": str(row.get("Author(s)", "")),
                        "year": str(row.get("Year", "")),
                        "pdf": str(row.get("Thesis_PDF", "")),
                        "countries": [x.strip() for x in str(row.get("Country", "")).split(";") if x.strip() and x.strip().lower() not in ("n/a", "nan", "")],
                    })

        # Methodology counts
        method_counts = _ins_Counter()
        for v in df["Methodology Type"].dropna():
            for m in str(v).split(","):
                m = m.strip()
                if m and m.lower() not in ("n/a", "nan", ""):
                    method_counts[m] += 1

        # Sector per year
        df2 = df.copy()
        df2["_year"] = pd.to_numeric(df2["Year"], errors="coerce")
        years = sorted(df2["_year"].dropna().unique().astype(int))
        sectors = [s for s in df2["Main sector"].dropna().unique()
                   if str(s).lower() not in ("n/a", "nan", "")]
        sector_year = {}
        for s in sectors:
            counts = []
            for y in years:
                mask = (df2["_year"] == y) & (df2["Main sector"] == s)
                counts.append(int(mask.sum()))
            sector_year[s] = counts

        return {
            "sdg_counts": dict(sdg_counts),
            "sdg_theses": sdg_theses,
            "sdg_aggregates": sdg_aggregates,
            "org_theses": org_theses,
            "country_counts": dict(country_counts),
            "country_theses": country_theses,
            "method_counts": dict(method_counts),
            "sector_year": sector_year,
            "years": [int(y) for y in years],
        }

    _ins_data = _compute_insights(df, PROGRAM)

    # ── page CSS ──────────────────────────────────────────────────────────
    st.markdown("""<style>
    /* ── Insights hero ── */
    .ins-hero {
        background: linear-gradient(135deg, #001f3a 0%, #003660 60%, #0a5c8a 100%);
        border-radius: 24px; padding: 3rem 3rem 2.5rem;
        margin-bottom: 2.8rem; position: relative; overflow: hidden;
    }
    .ins-hero::before {
        content: ''; position: absolute; inset: 0;
        background: radial-gradient(ellipse at 80% 50%, rgba(255,205,0,0.08) 0%, transparent 60%);
        pointer-events: none;
    }
    .ins-hero-eyebrow {
        font-size: 0.68rem; font-weight: 800; letter-spacing: 0.18em;
        text-transform: uppercase; color: #FFCD00; margin-bottom: 0.7rem;
    }
    .ins-hero-title {
        font-size: 2.6rem; font-weight: 800; color: #fff;
        line-height: 1.15; margin: 0 0 0.8rem; letter-spacing: -0.02em;
    }
    .ins-hero-sub {
        font-size: 1rem; color: rgba(255,255,255,0.65); max-width: 640px;
        line-height: 1.6; margin: 0;
    }
    .ins-stat-row {
        display: flex; gap: 2.2rem; margin-top: 2rem; flex-wrap: wrap;
    }
    .ins-stat {
        display: flex; flex-direction: column; gap: 0.1rem;
    }
    .ins-stat-num {
        font-size: 2rem; font-weight: 800; color: #FFCD00; line-height: 1;
    }
    .ins-stat-label {
        font-size: 0.72rem; color: rgba(255,255,255,0.5);
        text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600;
    }

    /* ── Section wrappers ── */
    .ins-section {
        margin-bottom: 3.5rem;
    }
    .ins-section-header {
        display: flex; align-items: flex-end; gap: 1rem; margin-bottom: 1.6rem;
    }
    .ins-section-number {
        font-size: 3.5rem; font-weight: 900; color: rgba(0,54,96,0.07);
        line-height: 1; font-family: 'Merriweather', serif; user-select: none;
        letter-spacing: -0.04em;
    }
    .ins-section-text {}
    .ins-section-title {
        font-size: 1.45rem; font-weight: 800; color: #0a2540; margin: 0;
        letter-spacing: -0.02em;
    }
    .ins-section-desc {
        font-size: 0.83rem; color: #6b7a8d; margin: 0.2rem 0 0;
        font-weight: 400;
    }
    </style>""", unsafe_allow_html=True)

    # ── Hero ─────────────────────────────────────────────────────────────
    _n_orgs = len(_ins_data["org_theses"])
    _n_countries = len(_ins_data["country_counts"])
    _n_sdgs = len(_ins_data["sdg_counts"])
    _years_range = (
        f"{min(_ins_data['years'])}–{max(_ins_data['years'])}"
        if _ins_data["years"] else "—"
    )
    st.markdown(f"""
    <div class="ins-hero">
      <div class="ins-hero-eyebrow">Programme Insights</div>
      <div class="ins-hero-title">{_display_name}<br/>by the numbers</div>
      <div class="ins-hero-sub">
        Explore the research landscape of the {_display_name} programme —
        from the global goals that drive research to the organisations shaping it.
      </div>
      <div class="ins-stat-row">
        <div class="ins-stat">
          <span class="ins-stat-num">{len(df)}</span>
          <span class="ins-stat-label">Theses</span>
        </div>
        <div class="ins-stat">
          <span class="ins-stat-num">{_n_sdgs}</span>
          <span class="ins-stat-label">SDGs covered</span>
        </div>
        <div class="ins-stat">
          <span class="ins-stat-num">{_n_countries}</span>
          <span class="ins-stat-label">Countries</span>
        </div>
        <div class="ins-stat">
          <span class="ins-stat-num">{_n_orgs}</span>
          <span class="ins-stat-label">Partner orgs</span>
        </div>
        <div class="ins-stat">
          <span class="ins-stat-num">{_years_range}</span>
          <span class="ins-stat-label">Cohorts</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 1 — SDG UNIVERSE
    # ══════════════════════════════════════════════════════════════════════
    st.markdown("""
    <div class="ins-section">
      <div class="ins-section-header">
        <div class="ins-section-number">01</div>
        <div class="ins-section-text">
          <div class="ins-section-title">SDG Universe</div>
          <div class="ins-section-desc">Which Sustainable Development Goals does the research address? Click any goal to explore linked theses.</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Build SDG data payload. Theses are capped at 40 per SDG to keep the
    # JSON payload reasonable while still exposing the full list to the modal.
    _sdg_payload = []
    for _sdg_n in range(1, 18):
        _cnt = _ins_data["sdg_counts"].get(_sdg_n, 0)
        _icon_path = os.path.join(PROGRAM_DIR, "sdg_icons", f"Goal-{_sdg_n:02d}.png")
        _icon_b64 = _load_image_b64(_icon_path)
        _theses = _ins_data["sdg_theses"].get(_sdg_n, [])[:40]
        _agg = _ins_data.get("sdg_aggregates", {}).get(_sdg_n, {})
        # Build a compact "SDG n — Name" lookup for the co-occurring SDG chips.
        _co_named = [
            {"n": int(o_n), "count": int(o_c),
             "name": _INS_SDG_NAMES.get(int(o_n), ""),
             "color": _INS_SDG_HEX.get(int(o_n), "#888")}
            for o_n, o_c in _agg.get("co_sdgs", [])
        ]
        _sdg_payload.append({
            "n":            _sdg_n,
            "count":        _cnt,
            "name":         _INS_SDG_NAMES.get(_sdg_n, ""),
            "color":        _INS_SDG_HEX.get(_sdg_n, "#888"),
            "icon":         _icon_b64,
            "desc":         _INS_SDG_DESCRIPTIONS.get(_sdg_n, ""),
            "theses":       _theses,
            "top_sectors":  _agg.get("top_sectors", []),
            "top_methods":  _agg.get("top_methods", []),
            "top_theories": _agg.get("top_theories", []),
            "top_supervisors": _agg.get("top_supervisors", []),
            "top_countries":   _agg.get("top_countries", []),
            "year_counts":  _agg.get("year_counts", {}),
            "co_sdgs":      _co_named,
            "featured_count": sum(1 for t in _theses if t.get("featured")),
        })

    _sdg_json = _ins_json.dumps(_sdg_payload, ensure_ascii=False)
    _sdg_enc_prog = __import__("urllib.parse", fromlist=["quote"]).quote(PROGRAM, safe="")

    _sdg_html = f"""
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:'Inter',-apple-system,sans-serif;background:transparent;overflow-x:hidden;}}
#whl-wrap{{display:flex;justify-content:center;padding:8px 0 4px;position:relative;}}
.seg-g{{transition:transform 0.22s cubic-bezier(.34,1.56,.64,1),opacity 0.3s;}}
#sdg-overlay{{
  display:none;position:absolute;inset:0;
  background:rgba(255,255,255,0.55);backdrop-filter:blur(2px);
  border-radius:20px;z-index:10;
}}
#sdg-overlay.open{{display:block;}}
#sdg-detail{{
  display:none;position:absolute;
  top:50%;left:50%;transform:translate(-50%,-50%) scale(0.94);
  width:min(880px,94%);max-height:min(86vh,820px);
  border-radius:20px;background:#fff;border:1px solid #e2e8f0;
  box-shadow:0 14px 50px rgba(0,54,96,0.22);overflow:hidden;
  z-index:11;
  transition:transform 0.22s cubic-bezier(.34,1.56,.64,1),opacity 0.22s;
  opacity:0;
}}
#sdg-detail.open{{
  display:flex;flex-direction:column;
  transform:translate(-50%,-50%) scale(1);opacity:1;
}}
#sdg-di{{padding:0;overflow-y:auto;flex:1;}}
/* Header band — coloured by the SDG; sits flush with modal top */
.sdg-hd{{display:flex;gap:18px;align-items:flex-start;padding:22px 26px 18px;color:#fff;position:relative;}}
.sdg-hd .sdg-close{{position:absolute;top:14px;right:14px;background:rgba(255,255,255,0.18);border:none;color:#fff;cursor:pointer;font-size:1.05rem;width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;transition:background 0.15s;}}
.sdg-hd .sdg-close:hover{{background:rgba(255,255,255,0.32);}}
.sdg-hd-icon{{width:78px;height:78px;border-radius:14px;background:rgba(255,255,255,0.15);overflow:hidden;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:2rem;font-weight:900;}}
.sdg-hd-icon img{{width:100%;height:100%;object-fit:cover;}}
.sdg-hd-text{{flex:1;min-width:0;padding-right:32px;}}
.sdg-hd-eyebrow{{font-size:0.74rem;font-weight:700;letter-spacing:0.14em;text-transform:uppercase;opacity:0.82;}}
.sdg-hd-title{{font-size:1.45rem;font-weight:800;margin-top:2px;letter-spacing:-0.01em;}}
.sdg-hd-desc{{font-size:0.86rem;line-height:1.5;margin-top:8px;opacity:0.95;max-width:580px;}}
/* Stats strip */
.sdg-stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:0;border-bottom:1px solid #eef2f7;background:#fbfcfd;}}
.sdg-stat{{padding:14px 16px;border-right:1px solid #eef2f7;text-align:center;}}
.sdg-stat:last-child{{border-right:none;}}
.sdg-stat-v{{font-size:1.35rem;font-weight:800;color:#0a2540;line-height:1.1;}}
.sdg-stat-l{{font-size:0.7rem;font-weight:600;color:#6b7a8d;text-transform:uppercase;letter-spacing:0.08em;margin-top:4px;}}
/* Body sections */
.sdg-body{{padding:20px 26px 26px;}}
.sdg-sec{{margin-top:18px;}}
.sdg-sec:first-child{{margin-top:0;}}
.sdg-sec-h{{display:flex;align-items:center;gap:8px;font-size:0.78rem;font-weight:700;color:#6b7a8d;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;}}
.sdg-sec-h .sdg-sec-h-dot{{width:6px;height:6px;border-radius:50%;background:#cbd5e0;}}
/* Year mini-chart */
.sdg-yr-row{{display:flex;align-items:flex-end;gap:6px;height:78px;padding-bottom:18px;border-bottom:1px dashed #e2e8f0;position:relative;}}
.sdg-yr-col{{flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;min-width:0;position:relative;}}
.sdg-yr-bar{{width:100%;max-width:40px;border-radius:5px 5px 0 0;transition:filter 0.15s;}}
.sdg-yr-col:hover .sdg-yr-bar{{filter:brightness(1.15);}}
.sdg-yr-cnt{{position:absolute;bottom:calc(100% + 4px);font-size:0.65rem;font-weight:700;color:#6b7a8d;opacity:0;transition:opacity 0.15s;}}
.sdg-yr-col:hover .sdg-yr-cnt{{opacity:1;}}
.sdg-yr-lbl{{font-size:0.7rem;font-weight:600;color:#6b7a8d;position:absolute;top:calc(100% + 4px);}}
/* Chip rows */
.sdg-chips{{display:flex;flex-wrap:wrap;gap:6px;}}
.sdg-chip{{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;background:#f1f5fa;color:#0a2540;border-radius:999px;font-size:0.78rem;font-weight:600;}}
.sdg-chip .c{{background:#003660;color:#fff;border-radius:999px;padding:0 6px;font-size:0.7rem;font-weight:700;min-width:18px;text-align:center;}}
.sdg-chip-co{{padding:4px 9px;color:#fff;font-weight:700;}}
/* Two-column layout for top-categories on wider modals */
.sdg-grid2{{display:grid;grid-template-columns:1fr 1fr;gap:18px;}}
@media (max-width:680px){{.sdg-grid2{{grid-template-columns:1fr;}} .sdg-stats{{grid-template-columns:repeat(2,1fr);}}}}
/* Supervisor list */
.sdg-sup-list{{display:flex;flex-direction:column;gap:6px;}}
.sdg-sup-row{{display:flex;align-items:center;justify-content:space-between;padding:7px 10px;background:#f8fafc;border-radius:8px;font-size:0.82rem;}}
.sdg-sup-row .nm{{color:#0a2540;font-weight:600;}}
.sdg-sup-row .ct{{color:#6b7a8d;font-weight:700;}}
/* Theses list */
.sd-t{{padding:10px 12px;border-bottom:1px solid #f0f4f9;display:flex;gap:12px;align-items:flex-start;text-decoration:none;color:inherit;}}
.sd-t:last-child{{border-bottom:none;}}
.sd-t[href]:hover{{background:#f5f8ff;cursor:pointer;}}
.sd-t .sd-yr{{flex-shrink:0;width:40px;background:#eef2f7;color:#0a2540;font-weight:800;font-size:0.78rem;text-align:center;padding:3px 0;border-radius:6px;line-height:1.4;}}
.sd-t-body{{flex:1;min-width:0;}}
.sd-title{{font-size:0.88rem;font-weight:700;color:#0a2540;line-height:1.35;}}
.sd-meta{{font-size:0.74rem;color:#6b7a8d;margin-top:3px;}}
.sd-meta-tag{{display:inline-block;background:#fff7cc;color:#7a5d00;border-radius:4px;padding:1px 6px;font-size:0.66rem;font-weight:700;margin-left:6px;vertical-align:1px;}}
.sd-empty{{padding:18px;text-align:center;color:#9aa5b4;font-size:0.82rem;}}
</style>
<div id="whl-wrap">
  <svg id="whl" viewBox="0 0 480 480" width="960" height="960"></svg>
  <div id="sdg-overlay"></div>
  <div id="sdg-detail"><div id="sdg-di"></div></div>
</div>
<script>
var DATA={_sdg_json};
var PROG="{_sdg_enc_prog}";
var NS='http://www.w3.org/2000/svg';
var svg=document.getElementById('whl');
var detail=document.getElementById('sdg-detail');
var overlay=document.getElementById('sdg-overlay');
var di=document.getElementById('sdg-di');
var CX=240,CY=240,R_OUT=218,R_IN=86,STEP=360/17,GAP=1.8;
var R_MID=(R_OUT+R_IN)/2;
var activeN=null;
var segs=[];
function rad(d){{return d*Math.PI/180;}}
function pt(r,d){{return [CX+r*Math.cos(rad(d)),CY+r*Math.sin(rad(d))]}}
function arc(ro,ri,a1,a2){{
  var p1=pt(ro,a1),p2=pt(ro,a2),p3=pt(ri,a2),p4=pt(ri,a1),lg=(a2-a1>180)?1:0;
  return 'M'+p1[0].toFixed(2)+' '+p1[1].toFixed(2)
    +' A'+ro+' '+ro+' 0 '+lg+' 1 '+p2[0].toFixed(2)+' '+p2[1].toFixed(2)
    +' L'+p3[0].toFixed(2)+' '+p3[1].toFixed(2)
    +' A'+ri+' '+ri+' 0 '+lg+' 0 '+p4[0].toFixed(2)+' '+p4[1].toFixed(2)+'Z';
}}
function mk(t){{return document.createElementNS(NS,t);}}
function esc(s){{return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}
var defs=mk('defs');
defs.innerHTML='<filter id="cs"><feDropShadow dx="0" dy="2" stdDeviation="5" flood-color="rgba(0,54,96,0.18)"/></filter>';
svg.appendChild(defs);
var hub=mk('circle');
hub.setAttribute('cx',CX);hub.setAttribute('cy',CY);hub.setAttribute('r',R_IN-3);
hub.setAttribute('fill','#fff');hub.setAttribute('filter','url(#cs)');
svg.appendChild(hub);
DATA.forEach(function(d,i){{
  var a1=-90+i*STEP+GAP/2,a2=-90+(i+1)*STEP-GAP/2,am=(a1+a2)/2;
  var mp=pt(R_MID,am),rAM=rad(am);
  var dx=Math.cos(rAM)*10,dy=Math.sin(rAM)*10;
  var g=mk('g');
  g.style.opacity='0';
  g.style.transition='opacity 0.35s ease,transform 0.22s cubic-bezier(.34,1.56,.64,1)';
  if(d.count>0)g.style.cursor='pointer';
  var ph=mk('path');
  ph.setAttribute('d',arc(R_OUT,R_IN,a1,a2));
  ph.setAttribute('fill',d.color);
  ph.setAttribute('stroke','#fff');ph.setAttribute('stroke-width','2');
  g.appendChild(ph);
  var IS=36,IR=6,cid='ic'+i;
  var cp=mk('clipPath');cp.setAttribute('id',cid);
  var cr=mk('rect');
  cr.setAttribute('x',mp[0]-IS/2);cr.setAttribute('y',mp[1]-IS/2);
  cr.setAttribute('width',IS);cr.setAttribute('height',IS);cr.setAttribute('rx',IR);
  cp.appendChild(cr);defs.appendChild(cp);
  if(d.icon){{
    var img=mk('image');
    img.setAttribute('href','data:image/png;base64,'+d.icon);
    img.setAttribute('x',mp[0]-IS/2);img.setAttribute('y',mp[1]-IS/2);
    img.setAttribute('width',IS);img.setAttribute('height',IS);
    img.setAttribute('clip-path','url(#'+cid+')');
    img.setAttribute('preserveAspectRatio','xMidYMid slice');
    g.appendChild(img);
  }}
  if(d.count>0){{
    var bp=pt(R_OUT-15,am);
    var bc=mk('circle');
    bc.setAttribute('cx',bp[0]);bc.setAttribute('cy',bp[1]);
    bc.setAttribute('r',11);bc.setAttribute('fill','rgba(0,0,0,0.3)');
    g.appendChild(bc);
    var bt=mk('text');
    bt.setAttribute('x',bp[0]);bt.setAttribute('y',bp[1]+3.5);
    bt.setAttribute('text-anchor','middle');bt.setAttribute('font-size','9.5');
    bt.setAttribute('font-weight','800');bt.setAttribute('fill','#fff');
    bt.setAttribute('font-family','Inter,sans-serif');
    bt.textContent=d.count;
    g.appendChild(bt);
    g.addEventListener('mouseenter',function(){{if(activeN!==d.n)g.style.transform='translate('+dx+'px,'+dy+'px)';}});
    g.addEventListener('mouseleave',function(){{if(activeN!==d.n)g.style.transform='';}});
    g.addEventListener('click',function(){{openSDG(d,g,dx,dy);}});
  }}
  svg.appendChild(g);
  segs.push({{el:g,count:d.count,dx:dx,dy:dy}});
  (function(el,cnt){{setTimeout(function(){{el.style.opacity=cnt===0?'0.28':'1';}},60+i*50);}})(g,d.count);
}});
var hub2=mk('circle');
hub2.setAttribute('cx',CX);hub2.setAttribute('cy',CY);hub2.setAttribute('r',R_IN-3);
hub2.setAttribute('fill','#fff');svg.appendChild(hub2);
var tot=DATA.reduce(function(s,d){{return s+d.count;}},0);
var nSDG=DATA.filter(function(d){{return d.count>0;}}).length;
var tN=mk('text');tN.setAttribute('x',CX);tN.setAttribute('y',CY-6);
tN.setAttribute('text-anchor','middle');tN.setAttribute('font-size','30');
tN.setAttribute('font-weight','900');tN.setAttribute('fill','#003660');
tN.setAttribute('font-family','Inter,sans-serif');tN.textContent=tot;svg.appendChild(tN);
var tL=mk('text');tL.setAttribute('x',CX);tL.setAttribute('y',CY+13);
tL.setAttribute('text-anchor','middle');tL.setAttribute('font-size','9');
tL.setAttribute('font-weight','700');tL.setAttribute('fill','#6b7a8d');
tL.setAttribute('letter-spacing','0.09em');tL.setAttribute('font-family','Inter,sans-serif');
tL.textContent='THESES';svg.appendChild(tL);
var tS=mk('text');tS.setAttribute('x',CX);tS.setAttribute('y',CY+30);
tS.setAttribute('text-anchor','middle');tS.setAttribute('font-size','9');
tS.setAttribute('fill','#9aa5b4');tS.setAttribute('font-family','Inter,sans-serif');
tS.textContent=nSDG+' of 17 SDGs';svg.appendChild(tS);
function chipRow(items, opts){{
  // items: [[name, count], ...]. opts: {{prefix, fallback}}
  opts = opts || {{}};
  if(!items || !items.length) return '<div class="sdg-chips"><span style="color:#9aa5b4;font-size:0.78rem;">' + (opts.fallback || 'No data') + '</span></div>';
  return '<div class="sdg-chips">' + items.map(function(it){{
    return '<span class="sdg-chip">' + esc(it[0]) + '<span class="c">' + it[1] + '</span></span>';
  }}).join('') + '</div>';
}}
function supList(items){{
  if(!items || !items.length) return '<div style="color:#9aa5b4;font-size:0.82rem;">No supervisor data</div>';
  return '<div class="sdg-sup-list">' + items.map(function(it){{
    return '<div class="sdg-sup-row"><span class="nm">' + esc(it[0]) + '</span><span class="ct">' + it[1] + ' thesis' + (it[1]!==1?'es':'') + '</span></div>';
  }}).join('') + '</div>';
}}
function coRow(items){{
  if(!items || !items.length) return '<div style="color:#9aa5b4;font-size:0.78rem;">No overlap with other SDGs.</div>';
  return '<div class="sdg-chips">' + items.map(function(it){{
    return '<span class="sdg-chip sdg-chip-co" style="background:' + it.color + ';">SDG ' + it.n + ' \u00b7 ' + esc(it.name) + '<span class="c" style="background:rgba(0,0,0,0.22);color:#fff;">' + it.count + '</span></span>';
  }}).join('') + '</div>';
}}
function yearChart(yc, color){{
  var keys = Object.keys(yc).filter(function(k){{return /^[0-9]+$/.test(k);}}).map(Number).sort(function(a,b){{return a-b;}});
  if(!keys.length) return '<div style="color:#9aa5b4;font-size:0.78rem;">No year data.</div>';
  var maxV = 0; keys.forEach(function(k){{if(yc[String(k)]>maxV)maxV=yc[String(k)];}});
  if(maxV<=0) maxV = 1;
  return '<div class="sdg-yr-row">' + keys.map(function(k){{
    var v = yc[String(k)] || 0;
    var h = Math.max(4, Math.round(v/maxV*60));
    return '<div class="sdg-yr-col">'
      + '<span class="sdg-yr-cnt">' + v + '</span>'
      + '<div class="sdg-yr-bar" style="height:' + h + 'px;background:' + color + ';"></div>'
      + '<span class="sdg-yr-lbl">' + k + '</span>'
      + '</div>';
  }}).join('') + '</div>';
}}
function openSDG(d,g,dx,dy){{
  if(activeN===d.n){{closeDetail();return;}}
  activeN=d.n;
  segs.forEach(function(s){{s.el.style.transform='';s.el.style.opacity=s.count===0?'0.28':'0.2';}});
  g.style.transform='translate('+dx+'px,'+dy+'px)';
  g.style.opacity='1';

  // \u2500\u2500 Header (coloured band) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
  var ih = d.icon
    ? '<img src="data:image/png;base64,' + d.icon + '" alt="SDG ' + d.n + '" />'
    : '<span>' + d.n + '</span>';
  var header = '<div class="sdg-hd" style="background:' + d.color + ';">'
    + '<button class="sdg-close" onclick="closeDetail()" aria-label="Close">&#10005;</button>'
    + '<div class="sdg-hd-icon">' + ih + '</div>'
    + '<div class="sdg-hd-text">'
    +   '<div class="sdg-hd-eyebrow">UN Sustainable Development Goal ' + d.n + '</div>'
    +   '<div class="sdg-hd-title">' + esc(d.name) + '</div>'
    +   '<div class="sdg-hd-desc">' + esc(d.desc || '') + '</div>'
    + '</div></div>';

  // \u2500\u2500 Stats strip \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
  var supCount = (d.top_supervisors || []).length;
  var yearKeys = Object.keys(d.year_counts || {{}}).map(Number).filter(function(k){{return !isNaN(k);}}).sort(function(a,b){{return a-b;}});
  var yearSpan = yearKeys.length
    ? (yearKeys[0] === yearKeys[yearKeys.length-1] ? String(yearKeys[0]) : yearKeys[0] + '\u2013' + yearKeys[yearKeys.length-1])
    : '\u2014';
  var topSector = (d.top_sectors && d.top_sectors.length) ? d.top_sectors[0][0] : '\u2014';
  var topSectorShort = topSector.length > 22 ? topSector.slice(0,20) + '\u2026' : topSector;
  var stats = '<div class="sdg-stats">'
    + '<div class="sdg-stat"><div class="sdg-stat-v">' + d.count + '</div><div class="sdg-stat-l">Theses</div></div>'
    + '<div class="sdg-stat"><div class="sdg-stat-v">' + supCount + '</div><div class="sdg-stat-l">Supervisors</div></div>'
    + '<div class="sdg-stat"><div class="sdg-stat-v" style="font-size:1rem;line-height:1.6;">' + yearSpan + '</div><div class="sdg-stat-l">Time Span</div></div>'
    + '<div class="sdg-stat"><div class="sdg-stat-v" style="font-size:0.95rem;line-height:1.45;">' + esc(topSectorShort) + '</div><div class="sdg-stat-l">Top Sector</div></div>'
    + '</div>';

  // \u2500\u2500 Body sections \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
  var hasData = d.count > 0;
  var body = '<div class="sdg-body">';

  if(hasData){{
    body += '<div class="sdg-sec">'
      +   '<div class="sdg-sec-h"><span class="sdg-sec-h-dot"></span>Theses per year</div>'
      +   yearChart(d.year_counts || {{}}, d.color)
      + '</div>';
    body += '<div class="sdg-sec sdg-grid2">'
      +   '<div><div class="sdg-sec-h"><span class="sdg-sec-h-dot"></span>Top sectors</div>' + chipRow(d.top_sectors, {{fallback:'No sector data'}}) + '</div>'
      +   '<div><div class="sdg-sec-h"><span class="sdg-sec-h-dot"></span>Top methodologies</div>' + chipRow(d.top_methods, {{fallback:'No methodology data'}}) + '</div>'
      + '</div>';
    if((d.top_theories && d.top_theories.length) || (d.top_countries && d.top_countries.length)){{
      body += '<div class="sdg-sec sdg-grid2">'
        +   '<div><div class="sdg-sec-h"><span class="sdg-sec-h-dot"></span>Top theories</div>' + chipRow(d.top_theories, {{fallback:'No theory data'}}) + '</div>'
        +   '<div><div class="sdg-sec-h"><span class="sdg-sec-h-dot"></span>Top countries</div>' + chipRow(d.top_countries, {{fallback:'No country data'}}) + '</div>'
        + '</div>';
    }}
    body += '<div class="sdg-sec">'
      +   '<div class="sdg-sec-h"><span class="sdg-sec-h-dot"></span>Most active supervisors</div>'
      +   supList(d.top_supervisors)
      + '</div>';
    body += '<div class="sdg-sec">'
      +   '<div class="sdg-sec-h"><span class="sdg-sec-h-dot"></span>Connected goals</div>'
      +   coRow(d.co_sdgs)
      + '</div>';

    // \u2500\u2500 Theses list \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    var th = '';
    (d.theses || []).forEach(function(t){{
      var pdfKey = t.pdf ? t.pdf.replace(/\.pdf$/i,'') : '';
      var href = pdfKey && pdfKey !== 'nan' ? '?program=' + PROG + '&details=' + encodeURIComponent(pdfKey) : '#';
      var metaBits = [];
      if(t.author) metaBits.push(esc(t.author));
      if(t.year) metaBits.push(esc(t.year));
      if(t.sector) metaBits.push(esc(t.sector));
      if(t.supervisor) metaBits.push('Sup. ' + esc(t.supervisor));
      var featTag = t.featured ? '<span class="sd-meta-tag">FEATURED</span>' : '';
      th += '<a class="sd-t"' + (href!=='#'?' href="#" data-navurl="'+href+'"':'') + '>'
        + '<div class="sd-yr">' + (t.year || '\u2014') + '</div>'
        + '<div class="sd-t-body">'
        +   '<div class="sd-title">' + esc(t.title) + featTag + '</div>'
        +   '<div class="sd-meta">' + metaBits.join(' \u00b7 ') + '</div>'
        + '</div></a>';
    }});
    body += '<div class="sdg-sec">'
      +   '<div class="sdg-sec-h"><span class="sdg-sec-h-dot"></span>Theses (' + (d.theses || []).length + ')</div>'
      +   '<div style="border:1px solid #eef2f7;border-radius:10px;overflow:hidden;">'
      +     (th || '<div class="sd-empty">No theses to show.</div>')
      +   '</div>'
      + '</div>';
  }} else {{
    body += '<div class="sd-empty">No theses currently address SDG ' + d.n + ' in this programme.</div>';
  }}

  body += '</div>';

  di.innerHTML = header + stats + body;
  di.scrollTop = 0;
  detail.classList.add('open');
  overlay.classList.add('open');
}}
function closeDetail(){{
  activeN=null;
  detail.classList.remove('open');
  overlay.classList.remove('open');
  segs.forEach(function(s){{s.el.style.transform='';s.el.style.opacity=s.count===0?'0.28':'1';}});
}}
overlay.addEventListener('click',closeDetail);
// Delegated click handler for thesis links — uses postMessage to navigate
// parent window, bypassing sandbox restrictions on direct location assignment.
document.addEventListener('click',function(e){{
  var a=e.target.closest('[data-navurl]');
  if(!a)return;
  var url=a.getAttribute('data-navurl');
  if(!url)return;
  e.preventDefault();
  window.parent.postMessage({{type:'stNavigateTo',url:url}},'*');
}});
</script>
"""

    _render_html_iframe(_sdg_html, height=1060)

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 2 — PARTNER ORGANISATION GALAXY
    # ══════════════════════════════════════════════════════════════════════
    if _ins_data["org_theses"]:
        st.markdown("""
        <div class="ins-section">
          <div class="ins-section-header">
            <div class="ins-section-number">02</div>
            <div class="ins-section-text">
              <div class="ins-section-title">Partner Organisation Galaxy</div>
              <div class="ins-section-desc">Each node is a partner organisation, clustered by research sector. Hover to identify, click to explore linked theses.</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        _ORG_LOGOS_DIR = os.path.join(BASE_DIR, "company logos")

        # Derive primary sector for each org from most common thesis sector
        def _derive_sector(theses_list):
            from collections import Counter as _C
            ctr = _C(
                t.get("sector", "") for t in theses_list
                if t.get("sector", "").strip().lower() not in ("", "n/a", "nan")
            )
            return ctr.most_common(1)[0][0] if ctr else "Other"

        _org_items_raw = sorted(_ins_data["org_theses"].items(), key=lambda x: -len(x[1]))
        _org_payload = []
        for _org_name, _org_thlist in _org_items_raw:
            _psector = _derive_sector(_org_thlist)
            _logo_b64 = _load_org_logo_b64(_ORG_LOGOS_DIR, _org_name)
            _initials = "".join(w[0].upper() for w in _org_name.split()[:2] if w)
            _sec_color = _INS_SECTOR_HEX.get(_psector, "#7a8fa8")
            _org_payload.append({
                "name": _org_name,
                "count": len(_org_thlist),
                "sector": _psector,
                "sColor": _sec_color,
                "logo": _logo_b64,
                "initials": _initials,
                "theses": _org_thlist[:10],
            })

        # Unique sectors
        _org_sectors_ordered = list(dict.fromkeys(
            d["sector"] for d in sorted(_org_payload, key=lambda x: -x["count"])
        ))

        _org_json = _ins_json.dumps(_org_payload, ensure_ascii=False)
        _org_sectors_json = _ins_json.dumps(_org_sectors_ordered, ensure_ascii=False)
        _n_orgs_total = len(_org_payload)

        # UU logo for galaxy center
        _uu_logo_path = os.path.join(BASE_DIR, "Utrecht_University_logo_round.svg")
        _uu_logo_uri = _load_org_logo_b64.__wrapped__(
            os.path.join(BASE_DIR, "company logos"), "Utrecht University"
        ) if False else (
            f"data:image/svg+xml;base64,{_load_image_b64(_uu_logo_path)}"
            if os.path.exists(_uu_logo_path) else ""
        )

        _org_html = f"""
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
html,body{{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  background:transparent;overflow:hidden;-webkit-font-smoothing:antialiased;}}
/* ── Galaxy ── */
#galaxy-wrap{{
  position:relative;width:100%;height:1100px;overflow:hidden;
  background:transparent;
}}
#galaxy-svg{{position:absolute;inset:0;width:100%;height:100%;}}
/* Tooltip */
#gt{{
  position:absolute;pointer-events:none;display:none;
  background:rgba(255,255,255,0.96);backdrop-filter:blur(8px);
  border:1px solid rgba(0,0,0,0.1);border-radius:12px;
  padding:9px 13px;color:#1a2535;font-size:0.8rem;line-height:1.4;
  max-width:200px;z-index:20;box-shadow:0 4px 16px rgba(0,0,0,0.1);
}}
#gt-name{{font-weight:800;margin-bottom:2px;}}
#gt-sec{{font-size:0.7rem;opacity:0.6;}}
#gt-cnt{{font-size:0.72rem;color:#003660;margin-top:2px;font-weight:700;}}
/* Side panel */
#op{{
  position:absolute;top:0;right:-380px;width:360px;height:100%;
  background:rgba(255,255,255,0.98);backdrop-filter:blur(12px);
  border-left:1px solid rgba(0,0,0,0.1);
  overflow-y:auto;z-index:30;
  transition:right 0.38s cubic-bezier(.4,0,.2,1);
  padding:0;box-shadow:-4px 0 24px rgba(0,0,0,0.08);
}}
#op.open{{right:0;}}
#op-inner{{padding:1.2rem 1.3rem 2rem;}}
.op-close{{
  position:sticky;top:0;display:flex;justify-content:flex-end;
  padding:0.7rem 0.8rem 0;background:rgba(255,255,255,0.98);
  margin:-1.2rem -1.3rem 0.8rem;
}}
.op-close button{{
  background:none;border:none;color:rgba(0,0,0,0.3);cursor:pointer;
  font-size:1.1rem;padding:0.3rem;border-radius:8px;
}}
.op-close button:hover{{color:#1a2535;background:rgba(0,0,0,0.05);}}
.op-hdr{{display:flex;align-items:center;gap:0.9rem;margin-bottom:1rem;}}
.op-logo-wrap{{
  width:56px;height:56px;border-radius:12px;overflow:hidden;
  background:rgba(255,255,255,0.07);display:flex;align-items:center;
  justify-content:center;flex-shrink:0;border:1px solid rgba(255,255,255,0.1);
}}
.op-logo{{max-width:50px;max-height:50px;object-fit:contain;}}
.op-ini{{font-size:1.2rem;font-weight:900;color:#fff;}}
.op-name{{font-size:1rem;font-weight:800;color:#0a2540;line-height:1.3;}}
.op-meta{{display:flex;align-items:center;gap:6px;margin-top:4px;}}
.op-sec-dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0;}}
.op-sec-label{{font-size:0.7rem;color:rgba(0,0,0,0.45);font-weight:600;}}
.op-count{{
  margin-left:4px;background:#e8f0fe;color:#003660;
  border-radius:99px;padding:1px 7px;font-size:0.68rem;font-weight:700;
}}
.op-divider{{border:none;border-top:1px solid rgba(0,0,0,0.08);margin:0.9rem 0;}}
.op-thesis{{
  display:block;padding:0.6rem 0.5rem;border-radius:8px;
  text-decoration:none;transition:background 0.12s;margin-bottom:2px;
}}
.op-thesis:hover{{background:rgba(0,0,0,0.04);}}
.op-tt{{font-size:0.83rem;font-weight:700;color:#0a2540;line-height:1.35;}}
.op-tm{{font-size:0.71rem;color:rgba(0,0,0,0.4);margin-top:2px;}}
.op-sdot{{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:4px;vertical-align:middle;}}
</style>
<div id="galaxy-wrap">
  <svg id="galaxy-svg"></svg>
  <div id="gt"><div id="gt-name"></div><div id="gt-sec"></div><div id="gt-cnt"></div></div>
  <div id="op"><div id="op-inner"></div></div>
</div>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
var OD={_org_json};
var SECTORS={_org_sectors_json};
var PROG="{_sdg_enc_prog}";
var UU_LOGO="{_uu_logo_uri}";
var SDG_HEX={{1:"#E5243B",2:"#DDA63A",3:"#4C9F38",4:"#C5192D",5:"#FF3A21",6:"#26BDE2",7:"#FCC30B",8:"#A21942",9:"#FD6925",10:"#DD1367",11:"#FD9D24",12:"#BF8B2E",13:"#3F7E44",14:"#0A97D9",15:"#56C02B",16:"#00689D",17:"#19486A"}};
var wrap=document.getElementById('galaxy-wrap');
var W=wrap.clientWidth||800,H=1100;
var svgEl=document.getElementById('galaxy-svg');
var gt=document.getElementById('gt');
var op=document.getElementById('op');
var opInner=document.getElementById('op-inner');
var activeSector=null,activeOrg=null;
function esc(s){{return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}
function sdgC(s){{var m=String(s).match(/(\d+)/);return m?SDG_HEX[+m[1]]||'#888':'#888';}}
// radius scale — sqrt so larger orgs are meaningfully bigger
var maxCnt=d3.max(OD,function(d){{return d.count;}});
var rScale=d3.scaleSqrt().domain([1,maxCnt]).range([32,72]);
// sector colour lookup only — no positional anchors, free-floating galaxy
var secMap={{}};
SECTORS.forEach(function(s){{
  var col=OD.find(function(o){{return o.sector===s;}}).sColor;
  secMap[s]={{color:col}};
}});
// nodes: scatter randomly across the canvas
var nodes=OD.map(function(d){{
  return Object.assign({{r:rScale(d.count)}},d,{{
    x:W*0.15+Math.random()*W*0.7,
    y:H*0.15+Math.random()*H*0.7
  }});
}});
var svg=d3.select('#galaxy-svg')
  .attr('viewBox',[0,0,W,H])
  .attr('width',W).attr('height',H);
// defs
var defs=svg.append('defs');
// glow filter
var glowF=defs.append('filter').attr('id','glow').attr('x','-50%').attr('y','-50%').attr('width','200%').attr('height','200%');
glowF.append('feGaussianBlur').attr('stdDeviation','6').attr('result','blur');
var feMerge=glowF.append('feMerge');
feMerge.append('feMergeNode').attr('in','blur');
feMerge.append('feMergeNode').attr('in','SourceGraphic');
// active glow
var agF=defs.append('filter').attr('id','aglow').attr('x','-80%').attr('y','-80%').attr('width','260%').attr('height','260%');
agF.append('feGaussianBlur').attr('stdDeviation','12').attr('result','blur');
var aFM=agF.append('feMerge');
aFM.append('feMergeNode').attr('in','blur');
aFM.append('feMergeNode').attr('in','SourceGraphic');
// subtle dust particles (light mode — very faint)
var stars=d3.range(120).map(function(){{
  return {{x:Math.random()*W,y:Math.random()*H,r:Math.random()*1.2+0.3,op:Math.random()*0.12+0.04}};
}});
svg.append('g').selectAll('circle').data(stars).enter().append('circle')
  .attr('cx',function(d){{return d.x;}}).attr('cy',function(d){{return d.y;}})
  .attr('r',function(d){{return d.r;}})
  .attr('fill','#aab').attr('opacity',function(d){{return d.op;}});

// UU logo centered in galaxy
if(UU_LOGO){{
  var uuSize=160;
  svg.append('image')
    .attr('href',UU_LOGO)
    .attr('x',W/2-uuSize/2).attr('y',H/2-uuSize/2)
    .attr('width',uuSize).attr('height',uuSize)
    .attr('preserveAspectRatio','xMidYMid meet')
    .attr('opacity',0.12)
    .attr('pointer-events','none');
}}

// node groups
var nodeG=svg.append('g').attr('class','nodes');
var nodeEls=nodeG.selectAll('g.node').data(nodes).enter().append('g')
  .attr('class','node').style('cursor','pointer');
// outer glow ring
nodeEls.append('circle')
  .attr('class','glow-ring')
  .attr('r',function(d){{return d.r+6;}})
  .attr('fill','none')
  .attr('stroke',function(d){{return d.sColor;}})
  .attr('stroke-width',1.5)
  .attr('opacity',0.0)
  .attr('filter','url(#glow)');
// main circle
nodeEls.append('circle')
  .attr('class','main-circle')
  .attr('r',function(d){{return d.r;}})
  .attr('fill',function(d){{
    return d.logo?'#fff':'none';
  }})
  .attr('stroke','none');
// gradient fill for no-logo nodes
nodes.forEach(function(d,i){{
  if(!d.logo){{
    var lg=defs.append('radialGradient').attr('id','ng'+i)
      .attr('cx','35%').attr('cy','35%').attr('r','65%');
    var c1=d3.color(d.sColor);c1.opacity=1;
    var c2=d3.color(d.sColor);c2.l=Math.min(1,c2.l*1.5);c2.opacity=0.7;
    lg.append('stop').attr('offset','0%').attr('stop-color',d3.hsl(d3.color(d.sColor)).brighter(0.8)).attr('stop-opacity',1);
    lg.append('stop').attr('offset','100%').attr('stop-color',d.sColor).attr('stop-opacity',1);
    d3.select(nodeEls.nodes()[i]).select('.main-circle').attr('fill','url(#ng'+i+')');
  }}
}});
// clip + logo or initials
nodes.forEach(function(d,i){{
  var gEl=d3.select(nodeEls.nodes()[i]);
  defs.append('clipPath').attr('id','cp'+i).append('circle').attr('r',d.r-1);
  if(d.logo){{
    gEl.append('image')
      .attr('href',d.logo)
      .attr('x',-d.r+2).attr('y',-d.r+2)
      .attr('width',(d.r-2)*2).attr('height',(d.r-2)*2)
      .attr('preserveAspectRatio','xMidYMid meet')
      .attr('clip-path','url(#cp'+i+')');
  }}else{{
    var fs=Math.max(9,Math.min(16,d.r*0.55));
    gEl.append('text')
      .attr('text-anchor','middle').attr('dominant-baseline','central')
      .attr('font-size',fs).attr('font-weight','900')
      .attr('fill','rgba(255,255,255,0.95)')
      .attr('font-family','Inter,sans-serif')
      .attr('clip-path','url(#cp'+i+')')
      .text(d.initials);
  }}
  // count badge (small circle top-right)
  if(d.count>1){{
    gEl.append('circle').attr('cx',d.r-6).attr('cy',-d.r+6).attr('r',9)
      .attr('fill','#FFCD00').attr('stroke','#080f1e').attr('stroke-width',1.5);
    gEl.append('text').attr('x',d.r-6).attr('y',-d.r+6)
      .attr('text-anchor','middle').attr('dominant-baseline','central')
      .attr('font-size',7.5).attr('font-weight','900').attr('fill','#003660')
      .attr('font-family','Inter,sans-serif').text(d.count);
  }}
}});
// interaction
nodeEls
  .on('mouseenter',function(event,d){{
    var idx=nodes.indexOf(d);
    d3.select(this).select('.glow-ring').attr('opacity',0.7);
    d3.select(this).select('.main-circle').attr('stroke-width',3);
    gt.style.display='block';
    document.getElementById('gt-name').textContent=d.name;
    document.getElementById('gt-sec').textContent=d.sector;
    document.getElementById('gt-cnt').textContent=d.count+' thesis'+(d.count!==1?'es':'');
    moveTip(event);
  }})
  .on('mousemove',moveTip)
  .on('mouseleave',function(event,d){{
    if(activeOrg!==d.name){{
      d3.select(this).select('.glow-ring').attr('opacity',0);
    }}
    gt.style.display='none';
  }})
  .on('click',function(event,d){{
    event.stopPropagation();
    if(activeOrg===d.name){{closePanel();return;}}
    openPanel(d,this);
  }});
svg.on('click',function(){{closePanel();}});
function moveTip(event){{
  var bounds=wrap.getBoundingClientRect();
  var bx=event.clientX-bounds.left,by=event.clientY-bounds.top;
  var tw=gt.offsetWidth+16,th=gt.offsetHeight+16;
  gt.style.left=(bx+12+tw>W?bx-tw:bx+12)+'px';
  gt.style.top=(by+12+th>H?by-th:by+12)+'px';
}}
function openPanel(d,el){{
  activeOrg=d.name;
  nodeEls.select('.glow-ring').attr('opacity',0);
  nodeEls.select('.main-circle').attr('opacity',0.25);
  var me=d3.select(el);
  me.select('.glow-ring').attr('opacity',0.9).attr('filter','url(#aglow)');
  me.select('.main-circle').attr('stroke-width',3).attr('opacity',1);
  // build panel content
  var lhHtml='';
  if(d.logo){{
    lhHtml='<div class="op-logo-wrap"><img class="op-logo" src="'+d.logo+'" /></div>';
  }}else{{
    lhHtml='<div class="op-logo-wrap"><div class="op-ini">'+esc(d.initials)+'</div></div>';
  }}
  var th='';
  d.theses.forEach(function(t){{
    var pdfKey=t.pdf?t.pdf.replace('.pdf',''):'';
    var href=pdfKey?'?program='+PROG+'&details='+encodeURIComponent(pdfKey):'#';
    var sc=sdgC(t.sdg);
    th+='<a class="op-thesis" href="'+href+'" target="_blank">'
      +'<div class="op-tt"><span class="op-sdot" style="background:'+sc+'"></span>'+esc(t.title)+'</div>'
      +'<div class="op-tm">'+esc(t.author)+' \u00b7 '+esc(t.year)
      +(t.sector&&t.sector.toLowerCase()!=='n/a'?' \u00b7 '+esc(t.sector):'')+'</div></a>';
  }});
  opInner.innerHTML=
    '<div class="op-close"><button onclick="closePanel()" title="Close">&#10005;</button></div>'
    +'<div class="op-hdr">'+lhHtml
    +'<div><div class="op-name">'+esc(d.name)+'</div>'
    +'<div class="op-meta">'
    +'<span class="op-sec-dot" style="background:'+d.sColor+'"></span>'
    +'<span class="op-sec-label">'+esc(d.sector)+'</span>'
    +'<span class="op-count">'+d.count+' thesis'+(d.count!==1?'es':'')+'</span>'
    +'</div></div></div>'
    +'<hr class="op-divider">'+th;
  op.classList.add('open');
}}
function closePanel(){{
  activeOrg=null;
  op.classList.remove('open');
  nodeEls.select('.glow-ring').attr('opacity',0).attr('filter','url(#glow)');
  nodeEls.select('.main-circle').attr('opacity',1);
}}

// force sim — stronger center pull, weaker repulsion to keep nodes grouped centrally
var sim=d3.forceSimulation(nodes)
  .force('charge',d3.forceManyBody().strength(-55))
  .force('collide',d3.forceCollide().radius(function(d){{return d.r+6;}}).iterations(3))
  .force('center',d3.forceCenter(W/2,H/2).strength(0.12))
  .force('radial',d3.forceRadial(Math.min(W,H)*0.38,W/2,H/2).strength(0.06))
  .force('bounds',function(){{
    nodes.forEach(function(d){{
      var pad=d.r+4;
      d.x=Math.max(pad,Math.min(W-pad,d.x));
      d.y=Math.max(pad,Math.min(H-pad,d.y));
    }});
  }})
  .on('tick',function(){{
    nodeEls.attr('transform',function(d){{return 'translate('+d.x+','+d.y+')';}});
  }});
// gentle float drift animation after sim cools
var driftFrames=0;
function drift(){{
  if(driftFrames++%240===0){{
    nodes.forEach(function(d){{
      d.vx+=(Math.random()-0.5)*0.4;
      d.vy+=(Math.random()-0.5)*0.4;
    }});
    sim.alpha(0.06).restart();
  }}
  requestAnimationFrame(drift);
}}
sim.on('end',function(){{drift();}});
</script>
"""
        _render_html_iframe(_org_html, height=1160)
        st.markdown("<div style='margin-bottom:3rem;'></div>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 3 — RESEARCH GEOGRAPHY
    # ══════════════════════════════════════════════════════════════════════
    _country_counts = {k: v for k, v in _ins_data["country_counts"].items()
                       if k.lower() not in ("global", "multi-region", "europe", "africa", "asia",
                                            "latin america", "middle east", "n/a", "nan", "")
                       and v >= 1}
    if _country_counts:
        st.markdown("""
        <div class="ins-section">
          <div class="ins-section-header">
            <div class="ins-section-number">03</div>
            <div class="ins-section-text">
              <div class="ins-section-title">Research Geography</div>
              <div class="ins-section-desc">Where in the world does the research take place? Bubble size reflects thesis count per country.</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        _sorted_countries = sorted(_country_counts.items(), key=lambda x: -x[1])[:30]
        _max_count = max(v for _, v in _sorted_countries)

        _COUNTRY_ISO2 = {
            "afghanistan":"af","albania":"al","algeria":"dz","angola":"ao","argentina":"ar",
            "armenia":"am","australia":"au","austria":"at","azerbaijan":"az","bangladesh":"bd",
            "belarus":"by","belgium":"be","benin":"bj","bolivia":"bo","bosnia":"ba",
            "botswana":"bw","brazil":"br","bulgaria":"bg","burkina faso":"bf","burundi":"bi",
            "cambodia":"kh","cameroon":"cm","canada":"ca","central african republic":"cf",
            "chad":"td","chile":"cl","china":"cn","colombia":"co","congo":"cg",
            "democratic republic of the congo":"cd","dr congo":"cd","democratic republic congo":"cd",
            "republic of the congo":"cg","costa rica":"cr","croatia":"hr","cuba":"cu",
            "czech republic":"cz","czechia":"cz","denmark":"dk","djibouti":"dj",
            "dominican republic":"do","ecuador":"ec","egypt":"eg","el salvador":"sv",
            "eritrea":"er","estonia":"ee","ethiopia":"et","eswatini":"sz","swaziland":"sz",
            "fiji":"fj","finland":"fi","france":"fr","gabon":"ga","georgia":"ge",
            "germany":"de","ghana":"gh","greece":"gr","guatemala":"gt","guinea":"gn",
            "guinea-bissau":"gw","haiti":"ht","honduras":"hn","hungary":"hu","iceland":"is",
            "india":"in","indonesia":"id","iran":"ir","iraq":"iq","ireland":"ie",
            "israel":"il","italy":"it","ivory coast":"ci","cote d'ivoire":"ci",
            "côte d'ivoire":"ci","cote divoire":"ci","jamaica":"jm","japan":"jp",
            "jordan":"jo","kazakhstan":"kz","kenya":"ke","kosovo":"xk","kyrgyzstan":"kg",
            "laos":"la","latvia":"lv","lebanon":"lb","lesotho":"ls","liberia":"lr",
            "libya":"ly","lithuania":"lt","luxembourg":"lu","madagascar":"mg","malawi":"mw",
            "malaysia":"my","mali":"ml","mauritania":"mr","mauritius":"mu","mexico":"mx",
            "moldova":"md","mongolia":"mn","montenegro":"me","morocco":"ma","mozambique":"mz",
            "myanmar":"mm","burma":"mm","namibia":"na","nepal":"np","netherlands":"nl",
            "new zealand":"nz","nicaragua":"ni","niger":"ne","nigeria":"ng",
            "north korea":"kp","north macedonia":"mk","norway":"no","pakistan":"pk",
            "palestine":"ps","panama":"pa","papua new guinea":"pg","paraguay":"py",
            "peru":"pe","philippines":"ph","poland":"pl","portugal":"pt","romania":"ro",
            "russia":"ru","rwanda":"rw","saudi arabia":"sa","senegal":"sn","serbia":"rs",
            "sierra leone":"sl","singapore":"sg","slovakia":"sk","slovenia":"si",
            "somalia":"so","south africa":"za","south korea":"kr","south sudan":"ss",
            "spain":"es","sri lanka":"lk","sudan":"sd","suriname":"sr","sweden":"se",
            "switzerland":"ch","syria":"sy","taiwan":"tw","tajikistan":"tj","tanzania":"tz",
            "thailand":"th","togo":"tg","tunisia":"tn","turkey":"tr","turkiye":"tr",
            "uganda":"ug","ukraine":"ua","united arab emirates":"ae","uae":"ae",
            "united kingdom":"gb","uk":"gb","united states":"us","usa":"us",
            "united states of america":"us","uruguay":"uy","uzbekistan":"uz",
            "venezuela":"ve","vietnam":"vn","viet nam":"vn","yemen":"ye",
            "zambia":"zm","zimbabwe":"zw","hong kong":"hk","timor-leste":"tl",
            "east timor":"tl","cabo verde":"cv","cape verde":"cv",
        }
        _COUNTRY_LATLNG = {
            "afghanistan":(33.9,67.7),"albania":(41.15,20.17),"algeria":(28.0,3.0),
            "angola":(-11.2,17.9),"argentina":(-38.4,-63.6),"armenia":(40.07,45.04),
            "australia":(-25.3,133.8),"austria":(47.5,14.6),"azerbaijan":(40.14,47.58),
            "bangladesh":(23.7,90.4),"belarus":(53.7,27.95),"belgium":(50.5,4.47),
            "benin":(9.31,2.32),"bolivia":(-16.3,-63.6),"bosnia":(44.2,17.9),
            "botswana":(-22.3,24.7),"brazil":(-14.2,-51.9),"bulgaria":(42.73,25.49),
            "burkina faso":(12.36,-1.54),"burundi":(-3.37,29.92),
            "cambodia":(12.57,104.99),"cameroon":(3.85,11.5),"canada":(56.13,-106.35),
            "central african republic":(6.61,20.94),"chad":(15.45,18.73),
            "chile":(-35.68,-71.54),"china":(35.86,104.2),"colombia":(4.57,-74.3),
            "congo":(-0.23,15.83),"democratic republic of the congo":(-4.04,21.76),
            "dr congo":(-4.04,21.76),"democratic republic congo":(-4.04,21.76),
            "republic of the congo":(-0.23,15.83),"costa rica":(9.75,-83.75),
            "croatia":(45.1,15.2),"cuba":(21.52,-77.78),"czech republic":(49.82,15.47),
            "czechia":(49.82,15.47),"denmark":(56.26,9.5),"djibouti":(11.83,42.59),
            "dominican republic":(18.74,-70.16),"ecuador":(-1.83,-78.18),
            "egypt":(26.82,30.8),"el salvador":(13.79,-88.9),"eritrea":(15.18,39.78),
            "estonia":(58.60,25.01),"ethiopia":(9.14,40.49),"eswatini":(-26.52,31.47),
            "swaziland":(-26.52,31.47),"fiji":(-17.71,178.07),"finland":(61.92,25.75),
            "france":(46.23,2.21),"gabon":(-0.80,11.61),"georgia":(42.32,43.36),
            "germany":(51.17,10.45),"ghana":(7.95,-1.02),"greece":(39.07,21.82),
            "guatemala":(15.78,-90.23),"guinea":(11.0,-10.9),"guinea-bissau":(11.8,-15.18),
            "haiti":(18.97,-72.29),"honduras":(15.2,-86.24),"hungary":(47.16,19.5),
            "iceland":(64.96,-19.02),"india":(20.59,78.96),"indonesia":(-0.79,113.92),
            "iran":(32.43,53.69),"iraq":(33.22,43.68),"ireland":(53.41,-8.24),
            "israel":(31.05,34.85),"italy":(41.87,12.57),
            "ivory coast":(7.54,-5.55),"cote d'ivoire":(7.54,-5.55),
            "côte d'ivoire":(7.54,-5.55),"cote divoire":(7.54,-5.55),
            "jamaica":(18.11,-77.3),"japan":(36.2,138.25),"jordan":(30.59,36.24),
            "kazakhstan":(48.02,66.92),"kenya":(-0.02,37.91),"kosovo":(42.6,20.9),
            "kyrgyzstan":(41.2,74.77),"laos":(19.86,102.50),"latvia":(56.88,24.60),
            "lebanon":(33.85,35.86),"lesotho":(-29.61,28.23),"liberia":(6.43,-9.43),
            "libya":(26.34,17.23),"lithuania":(55.17,23.88),"luxembourg":(49.82,6.13),
            "madagascar":(-18.77,46.87),"malawi":(-13.25,34.3),"malaysia":(4.21,101.98),
            "mali":(17.57,-4.0),"mauritania":(21.01,-10.94),"mauritius":(-20.35,57.55),
            "mexico":(23.63,-102.55),"moldova":(47.41,28.37),"mongolia":(46.86,103.85),
            "montenegro":(42.71,19.37),"morocco":(31.79,-7.09),"mozambique":(-18.67,35.53),
            "myanmar":(21.92,95.96),"burma":(21.92,95.96),"namibia":(-22.96,18.49),
            "nepal":(28.39,84.12),"netherlands":(52.13,5.29),"new zealand":(-40.9,174.89),
            "nicaragua":(12.87,-85.21),"niger":(17.61,8.08),"nigeria":(9.08,8.68),
            "north korea":(40.34,127.51),"north macedonia":(41.61,21.75),
            "norway":(60.47,8.47),"pakistan":(30.38,69.35),"palestine":(31.95,35.23),
            "panama":(8.54,-80.78),"papua new guinea":(-6.31,143.96),
            "paraguay":(-23.44,-58.44),"peru":(-9.19,-75.02),"philippines":(12.88,121.77),
            "poland":(51.92,19.15),"portugal":(39.4,-8.22),"romania":(45.94,24.97),
            "russia":(61.52,105.32),"rwanda":(-1.94,29.87),"saudi arabia":(23.89,45.08),
            "senegal":(14.5,-14.45),"serbia":(44.02,21.01),"sierra leone":(8.46,-11.78),
            "singapore":(1.35,103.82),"slovakia":(48.67,19.7),"slovenia":(46.15,14.99),
            "somalia":(5.15,46.2),"south africa":(-30.56,22.94),"south korea":(35.91,127.77),
            "south sudan":(6.88,31.31),"spain":(40.46,-3.75),"sri lanka":(7.87,80.77),
            "sudan":(12.86,30.22),"suriname":(3.92,-56.03),"sweden":(60.13,18.64),
            "switzerland":(46.82,8.23),"syria":(34.8,38.99),"taiwan":(23.7,121.0),
            "tajikistan":(38.86,71.28),"tanzania":(-6.37,34.89),"thailand":(15.87,100.99),
            "togo":(8.62,0.82),"tunisia":(33.89,9.54),"turkey":(38.96,35.24),
            "turkiye":(38.96,35.24),"uganda":(1.37,32.29),"ukraine":(48.38,31.17),
            "united arab emirates":(23.42,53.85),"uae":(23.42,53.85),
            "united kingdom":(55.38,-3.44),"uk":(55.38,-3.44),
            "united states":(37.09,-95.71),"usa":(37.09,-95.71),
            "united states of america":(37.09,-95.71),
            "uruguay":(-32.52,-55.77),"uzbekistan":(41.38,64.59),
            "venezuela":(6.42,-66.59),"vietnam":(14.06,108.28),"viet nam":(14.06,108.28),
            "yemen":(15.55,48.52),"zambia":(-13.13,27.85),"zimbabwe":(-19.02,29.15),
            "hong kong":(22.32,114.17),"timor-leste":(-8.87,125.73),
            "east timor":(-8.87,125.73),"cabo verde":(16.54,-23.04),
            "cape verde":(16.54,-23.04),
        }
        _geo_data = [{"name": k, "count": v,
                      "code": _COUNTRY_ISO2.get(k.lower().strip(), ""),
                      "lat": _COUNTRY_LATLNG.get(k.lower().strip(), (None, None))[0],
                      "lng": _COUNTRY_LATLNG.get(k.lower().strip(), (None, None))[1],
                      "theses": _ins_data["country_theses"].get(k, [])[:10]}
                     for k, v in _sorted_countries]
        _geo_json = _ins_json.dumps(_geo_data, ensure_ascii=False)
        _country_iso2_json = _ins_json.dumps(_COUNTRY_ISO2, ensure_ascii=False)
        _prog_color = {
            "sbi": "#003660", "energy_science": "#c45c00",
            "sustainable_development": "#2e7d32", "innovation_sciences": "#5c3d9e",
            "water_management": "#0077b6",
        }.get(PROGRAM, "#003660")

        _geo_html = f"""<!DOCTYPE html>
<html><head><style>
*{{box-sizing:border-box;margin:0;padding:0;}}
html,body{{width:100%;height:100%;background:transparent;overflow:hidden;}}
#gc{{width:100%;height:560px;cursor:grab;}}
#gc:active{{cursor:grabbing;}}
.tip{{
  position:fixed;background:rgba(20,20,40,0.88);color:#fff;
  padding:6px 14px;border-radius:8px;font-size:13px;font-weight:600;
  pointer-events:none;z-index:9999;display:none;
  font-family:Inter,-apple-system,sans-serif;white-space:nowrap;
  backdrop-filter:blur(4px);
}}
#pop{{
  position:fixed;top:50%;left:50%;transform:translate(-50%,-50%) scale(0.9);
  background:#fff;border-radius:18px;padding:0;
  box-shadow:0 8px 40px rgba(0,0,0,0.22);z-index:10000;
  display:none;opacity:0;width:360px;max-height:480px;
  font-family:Inter,-apple-system,sans-serif;
  transition:opacity 0.18s,transform 0.18s;
  flex-direction:column;
  overflow:hidden;
}}
#pop.open{{display:flex;opacity:1;transform:translate(-50%,-50%) scale(1);}}
#pop-header{{
  padding:16px 20px 12px;border-bottom:1px solid #e8ecf0;
  display:flex;align-items:center;gap:10px;flex-shrink:0;
}}
#pop-flag{{width:32px;height:22px;background-size:cover;background-position:center;border-radius:3px;border:1px solid #e0e0e0;}}
#pop-title{{font-size:15px;font-weight:800;color:#1a202c;flex:1;}}
#pop-close{{
  width:26px;height:26px;border-radius:50%;background:#f0f2f5;
  border:none;cursor:pointer;font-size:14px;color:#666;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;
}}
#pop-list{{overflow-y:auto;flex:1;padding:8px 0;}}
.pop-item{{
  padding:10px 20px;border-bottom:1px solid #f0f2f5;
  cursor:pointer;transition:background 0.15s;
}}
.pop-item:last-child{{border-bottom:none;}}
.pop-item:hover{{background:#f7f9fc;}}
.pop-item-title{{font-size:12.5px;font-weight:700;color:#1a202c;line-height:1.35;margin-bottom:2px;}}
.pop-item-meta{{font-size:11px;color:#6b7a8d;}}
.pop-item-flags{{display:flex;gap:3px;margin-top:4px;flex-wrap:wrap;}}
.pop-flag-chip{{display:inline-flex;align-items:center;gap:2px;background:#f0f4f8;border-radius:4px;padding:1px 6px;font-size:11px;color:#4a5568;font-weight:600;}}
.pop-more{{
  padding:10px 20px;text-align:center;font-size:12px;font-weight:700;
  color:{_prog_color};cursor:pointer;background:#f7f9fc;
  border-top:1px solid #e8ecf0;flex-shrink:0;
}}
.pop-more:hover{{background:#eef2f7;}}
#pop-overlay{{
  position:fixed;inset:0;z-index:9999;display:none;
  background:rgba(0,0,0,0.18);
}}
#pop-overlay.open{{display:block;}}
</style></head><body>
<div id="gc"></div>
<div class="tip" id="tip"></div>
<div id="pop-overlay"></div>
<div id="pop">
  <div id="pop-header">
    <div id="pop-flag"></div>
    <div id="pop-title"></div>
    <button id="pop-close">&#x2715;</button>
  </div>
  <div id="pop-list"></div>
</div>
<script src="https://unpkg.com/globe.gl@2/dist/globe.gl.min.js"></script>
<script>
var GDATA={_geo_json};
var ISO2={_country_iso2_json};
var MAX={_max_count};
var COL="{_prog_color}";
var PROG="{PROGRAM}";
var tip=document.getElementById('tip');
var container=document.getElementById('gc');
var pop=document.getElementById('pop');
var overlay=document.getElementById('pop-overlay');
var popFlag=document.getElementById('pop-flag');
var popTitle=document.getElementById('pop-title');
var popList=document.getElementById('pop-list');
var popClose=document.getElementById('pop-close');
var W=container.clientWidth||900,H=900;

// ── globe setup ──────────────────────────────────────────────────────────
var globe=Globe()(container);
globe.width(W).height(H);
globe.backgroundColor('rgba(0,0,0,0)');
globe.renderer().setClearColor(0x000000,0);
globe.globeImageUrl('https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg');
globe.bumpImageUrl('https://unpkg.com/three-globe/example/img/earth-topology.png');
globe.atmosphereColor('#b8d4f0');
globe.atmosphereAltitude(0.15);

// ── altitude tracking ────────────────────────────────────────────────────
var filtered=GDATA.filter(function(d){{return d.lat!=null&&d.lng!=null;}});

globe.htmlElementsData(filtered);
globe.htmlLat(function(d){{return d.lat;}});
globe.htmlLng(function(d){{return d.lng;}});
globe.htmlAltitude(0.01);

// ── DOM builder ──────────────────────────────────────────────────────────
globe.htmlElement(function(d){{
  var size=Math.round(22+Math.pow(d.count/MAX,0.5)*46);
  var wrap=document.createElement('div');
  wrap.style.cssText='position:relative;width:'+size+'px;height:'+size+'px;'
    +'border-radius:50%;overflow:visible;cursor:pointer;pointer-events:auto;';
  var circle=document.createElement('div');
  circle.style.cssText='width:'+size+'px;height:'+size+'px;border-radius:50%;'
    +'background-size:cover;background-position:center;overflow:hidden;'
    +'border:2px solid rgba(255,255,255,0.85);'
    +'box-shadow:0 2px 10px rgba(0,0,0,0.5);'
    +'transition:transform 0.22s cubic-bezier(.34,1.56,.64,1),box-shadow 0.22s;';
  if(d.code){{
    circle.style.backgroundImage="url('https://flagcdn.com/w80/"+d.code+".webp')";
  }} else {{
    circle.style.background=COL;
    circle.style.display='flex';
    circle.style.alignItems='center';
    circle.style.justifyContent='center';
    circle.style.color='#fff';
    circle.style.fontSize=Math.max(8,Math.round(size/5))+'px';
    circle.style.fontWeight='800';
    circle.style.fontFamily='Inter,-apple-system,sans-serif';
    circle.textContent=d.name.split(' ').map(function(w){{return w[0];}}).join('').slice(0,3).toUpperCase();
  }}
  if(d.count>1){{
    var bs=Math.max(14,Math.round(size*0.34));
    var badge=document.createElement('div');
    badge.style.cssText='position:absolute;bottom:-3px;right:-3px;z-index:2;'
      +'width:'+bs+'px;height:'+bs+'px;border-radius:50%;'
      +'background:'+COL+';color:#fff;'
      +'font-size:'+Math.max(8,Math.round(bs*0.58))+'px;'
      +'font-weight:800;display:flex;align-items:center;justify-content:center;'
      +'border:1.5px solid #fff;pointer-events:none;'
      +'font-family:Inter,-apple-system,sans-serif;';
    badge.textContent=d.count;
    wrap.appendChild(circle);
    wrap.appendChild(badge);
  }} else {{
    wrap.appendChild(circle);
  }}

  // hover: scale up
  wrap.addEventListener('mouseenter',function(e){{
    circle.style.transform='scale(1.18) translateY(-4px)';
    circle.style.boxShadow='0 8px 20px rgba(0,0,0,0.45)';
    tip.textContent=d.name+': '+d.count+' theses';
    tip.style.display='block';
  }});
  wrap.addEventListener('mousemove',function(e){{
    tip.style.left=(e.clientX+14)+'px';
    tip.style.top=(e.clientY-32)+'px';
  }});
  wrap.addEventListener('mouseleave',function(){{
    circle.style.transform='scale(1) translateY(0)';
    circle.style.boxShadow='0 2px 10px rgba(0,0,0,0.5)';
    tip.style.display='none';
  }});

  // click: popout
  wrap.addEventListener('click',function(e){{
    e.stopPropagation();
    openPopout(d);
  }});

  return wrap;
}});

// ── popout logic ──────────────────────────────────────────────────────────
function openPopout(d){{
  tip.style.display='none';
  popFlag.style.backgroundImage=d.code?"url('https://flagcdn.com/w80/"+d.code+".webp')":'';
  popFlag.style.background=d.code?'':'#e0e4ea';
  popTitle.textContent=d.name+' \u2014 '+d.count+' theses';
  popList.innerHTML='';
  var theses=d.theses||[];
  var total=d.count;
  theses.forEach(function(t){{
    var item=document.createElement('div');
    item.className='pop-item';
    var tit=document.createElement('div');
    tit.className='pop-item-title';
    tit.textContent=t.title||'Untitled';
    var meta=document.createElement('div');
    meta.className='pop-item-meta';
    meta.textContent=(t.author||'')+(t.year?' \u00b7 '+t.year:'');
    item.appendChild(tit);
    item.appendChild(meta);
    // per-thesis country flags (unicode emoji — no external CDN)
    if(t.countries&&t.countries.length){{
      var flags=document.createElement('div');
      flags.className='pop-item-flags';
      t.countries.forEach(function(cn){{
        var code=(ISO2[cn.toLowerCase().trim()]||'').toUpperCase();
        if(!code||code.length!==2)return;
        var emoji=String.fromCodePoint(0x1F1E6+code.charCodeAt(0)-65)+String.fromCodePoint(0x1F1E6+code.charCodeAt(1)-65);
        var chip=document.createElement('span');
        chip.className='pop-flag-chip';
        chip.textContent=emoji+'\u00a0'+cn;
        flags.appendChild(chip);
      }});
      if(flags.children.length)item.appendChild(flags);
    }}
    if(t.pdf&&t.pdf!=='nan'&&t.pdf!=='')item.addEventListener('click',function(){{
      var key=t.pdf.replace(/\.pdf$/i,'');
      var base=window.parent.location.href.split('?')[0];
      window.open(base+'?program='+PROG+'&details='+encodeURIComponent(key),'_blank');
    }});
    popList.appendChild(item);
  }});
  var existMore=pop.querySelector('.pop-more');
  if(existMore)pop.removeChild(existMore);
  if(total>10){{
    var more=document.createElement('div');
    more.className='pop-more';
    more.textContent='+'+(total-10)+' more theses';
    pop.appendChild(more);
  }}
  overlay.classList.add('open');
  pop.classList.add('open');
}}

// close pop
function closePop(){{
  pop.classList.remove('open');
  overlay.classList.remove('open');
  var more=pop.querySelector('.pop-more');
  if(more)pop.removeChild(more);
}}
popClose.addEventListener('click',closePop);
overlay.addEventListener('click',closePop);

// ── controls ─────────────────────────────────────────────────────────────
globe.controls().autoRotate=true;
globe.controls().autoRotateSpeed=0.5;
globe.controls().enableZoom=false; // zoom handled by our wheel listener
globe.controls().enableZoom=true;
globe.controls().minDistance=150;
globe.controls().maxDistance=500;
globe.pointOfView({{lat:20,lng:15,altitude:2.0}});

// stop rotation on first globe drag (not on flag click)
globe.controls().addEventListener('start',function(){{
  globe.controls().autoRotate=false;
}});

// ── pointer-events fix ────────────────────────────────────────────────────
// globe.gl creates an HTML overlay div (sibling of canvas) that intercepts
// wheel events, preventing OrbitControls from receiving them for zoom.
// Setting pointer-events:none on that overlay lets wheel events reach the canvas.
// Child flag elements with inline pointer-events:auto are unaffected by CSS rules.
setTimeout(function(){{
  globe.renderer().domElement.style.pointerEvents='auto';
  Array.from(container.children).forEach(function(el){{
    if(el.tagName!=='CANVAS'){{el.style.pointerEvents='none';}}
  }});
}},600);

// ── scroll isolation ──────────────────────────────────────────────────────
// When mouse is OVER the globe: capture wheel events so OrbitControls can zoom.
// When mouse is NOT over: forward wheel delta to parent page.
var _overGc=false;
container.addEventListener('mouseenter',function(){{_overGc=true;}});
container.addEventListener('mouseleave',function(){{_overGc=false;}});

// Non-passive listener on the container so we can preventDefault when over the globe.
container.addEventListener('wheel',function(e){{
  if(_overGc){{
    e.preventDefault(); // stop Streamlit iframe scroll
    // drive zoom via globe pointOfView altitude
    var pov=globe.pointOfView();
    var factor=e.deltaY>0?1.08:0.93;
    var newAlt=Math.max(0.2,Math.min(10,pov.altitude*factor));
    globe.pointOfView({{altitude:newAlt}},0);
  }}
}},{{passive:false}});

// Passive listener on document to pass scroll through when mouse is outside.
document.addEventListener('wheel',function(e){{
  if(!_overGc){{
    try{{window.parent.scrollBy({{top:e.deltaY,behavior:'auto'}});}}catch(ex){{}}
  }}
}},{{passive:true}});

window.addEventListener('resize',function(){{
  globe.width(container.clientWidth||900);
}});
</script></body></html>
"""
        _render_html_iframe(_geo_html, height=960)
        st.markdown("<div style='margin-bottom:3rem;'></div>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 4 — METHODOLOGY DNA
    # ══════════════════════════════════════════════════════════════════════
    _meth_counts = {k: v for k, v in _ins_data["method_counts"].items()
                    if k.lower() not in ("n/a", "nan", "") and v >= 1}
    if _meth_counts:
        st.markdown("""
        <div class="ins-section">
          <div class="ins-section-header">
            <div class="ins-section-number">04</div>
            <div class="ins-section-text">
              <div class="ins-section-title">Methodology DNA</div>
              <div class="ins-section-desc">The research methods that define how this programme investigates the world.</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        _meth_sorted = sorted(_meth_counts.items(), key=lambda x: -x[1])
        _meth_total = sum(v for _, v in _meth_sorted)
        _meth_payload = []
        for _mk, _mv in _meth_sorted:
            _meth_payload.append({
                "name": _mk,
                "count": _mv,
                "pct": round(100 * _mv / max(_meth_total, 1), 1),
                "color": _INS_METHOD_HEX.get(_mk, "#7a8fa8"),
            })
        _meth_json = _ins_json.dumps(_meth_payload, ensure_ascii=False)

        _meth_html = f"""
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:'Inter',-apple-system,sans-serif;background:transparent;}}
#meth-wrap{{padding:4px;}}
.meth-row{{
  display:flex;align-items:center;gap:1rem;margin-bottom:1rem;
  opacity:0;transform:translateX(-24px);
  animation:methIn 0.55s cubic-bezier(.34,1.56,.64,1) forwards;
}}
@keyframes methIn{{to{{opacity:1;transform:translateX(0);}}}}
.meth-label{{
  min-width:220px;max-width:220px;font-size:0.82rem;font-weight:700;
  color:#0a2540;line-height:1.3;flex-shrink:0;
}}
.meth-bar-bg{{
  flex:1;background:#f0f4f9;border-radius:99px;height:20px;overflow:hidden;
  position:relative;
}}
.meth-bar-fill{{
  height:100%;border-radius:99px;width:0;
  transition:width 1.2s cubic-bezier(.4,0,.2,1);
}}
.meth-count{{
  min-width:90px;text-align:right;font-size:0.8rem;font-weight:700;
  color:#0a2540;flex-shrink:0;
}}
.meth-pct{{font-size:0.72rem;color:#9aa5b4;font-weight:500;}}
</style>
<div id="meth-wrap"></div>
<script>
var MDATA={_meth_json};
var wrap=document.getElementById('meth-wrap');
var maxCount=MDATA[0].count;

MDATA.forEach(function(d,i){{
  var row=document.createElement('div');
  row.className='meth-row';
  row.style.animationDelay=(i*80)+'ms';
  var pct=Math.round(100*d.count/maxCount);
  row.innerHTML=
    '<div class="meth-label">'+d.name+'</div>'
    +'<div class="meth-bar-bg"><div class="meth-bar-fill" id="mbar'+i+'" style="background:'+d.color+'"></div></div>'
    +'<div class="meth-count">'+d.count+' <span class="meth-pct">('+d.pct+'%)</span></div>';
  wrap.appendChild(row);
}});

// Animate bars after paint
requestAnimationFrame(function(){{
  requestAnimationFrame(function(){{
    MDATA.forEach(function(d,i){{
      var pct=Math.round(100*d.count/maxCount);
      var el=document.getElementById('mbar'+i);
      if(el)el.style.width=pct+'%';
    }});
  }});
}});
</script>
"""
        _render_html_iframe(_meth_html, height=max(120, len(_meth_sorted) * 60 + 20))
        st.markdown("<div style='margin-bottom:3rem;'></div>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 5 — SECTOR TIMELINE
    # ══════════════════════════════════════════════════════════════════════
    _sector_year = _ins_data["sector_year"]
    _timeline_years = _ins_data["years"]
    if _sector_year and len(_timeline_years) >= 2:
        st.markdown("""
        <div class="ins-section">
          <div class="ins-section-header">
            <div class="ins-section-number">05</div>
            <div class="ins-section-text">
              <div class="ins-section-title">Sector Timeline</div>
              <div class="ins-section-desc">How research focus has shifted across sectors over the years. Hover a line to highlight.</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        _sec_payload = []
        for _sec, _sec_counts in sorted(
            _sector_year.items(),
            key=lambda x: -sum(x[1]),
        ):
            if sum(_sec_counts) == 0:
                continue
            _sec_payload.append({
                "name": _sec,
                "color": _INS_SECTOR_HEX.get(_sec, "#7a8fa8"),
                "counts": _sec_counts,
            })
        _sec_json = _ins_json.dumps({
            "sectors": _sec_payload,
            "years": _timeline_years,
        }, ensure_ascii=False)

        _timeline_html = f"""
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:'Inter',-apple-system,sans-serif;background:transparent;overflow:hidden;}}
#tl-wrap{{position:relative;width:100%;}}
#tl-svg{{width:100%;display:block;}}
#tl-legend{{
  display:flex;flex-wrap:wrap;gap:0.8rem 1.4rem;
  margin-top:0.8rem;padding:0 8px;
}}
.tl-legend-item{{
  display:flex;align-items:center;gap:0.4rem;
  font-size:0.75rem;font-weight:600;color:#4a5568;cursor:pointer;
  padding:0.2rem 0.4rem;border-radius:6px;transition:background 0.15s;
}}
.tl-legend-item:hover{{background:#f0f4f9;}}
.tl-legend-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0;}}
#tl-tooltip{{
  position:fixed;background:#fff;border:1px solid #e2e8f0;
  border-radius:10px;padding:0.6rem 0.9rem;pointer-events:none;
  box-shadow:0 4px 18px rgba(0,54,96,0.13);font-size:0.78rem;
  display:none;z-index:999;min-width:140px;
}}
</style>
<div id="tl-wrap">
  <svg id="tl-svg" height="300"></svg>
  <div id="tl-legend"></div>
</div>
<div id="tl-tooltip"></div>
<script>
var TL={_sec_json};
var svg=document.getElementById('tl-svg');
var legend=document.getElementById('tl-legend');
var tooltip=document.getElementById('tl-tooltip');
var W=800,H=300,PAD={{t:20,r:20,b:40,l:48}};
var years=TL.years;
var sectors=TL.sectors;
var maxVal=0;
sectors.forEach(function(s){{s.counts.forEach(function(c){{if(c>maxVal)maxVal=c;}});}});
if(maxVal===0)maxVal=1;
var xStep=(W-PAD.l-PAD.r)/(Math.max(years.length-1,1));

function xPos(i){{return PAD.l+i*xStep;}}
function yPos(v){{return PAD.t+(H-PAD.t-PAD.b)*(1-v/maxVal);}}

function makePath(counts){{
  var pts=counts.map(function(c,i){{return xPos(i)+','+yPos(c);}});
  return 'M'+pts.join(' L');
}}

svg.setAttribute('viewBox','0 0 '+W+' '+H);
svg.setAttribute('preserveAspectRatio','xMidYMid meet');

// Grid lines
for(var gi=0;gi<=4;gi++){{
  var gy=PAD.t+(H-PAD.t-PAD.b)*gi/4;
  var gl=document.createElementNS('http://www.w3.org/2000/svg','line');
  gl.setAttribute('x1',PAD.l);gl.setAttribute('x2',W-PAD.r);
  gl.setAttribute('y1',gy);gl.setAttribute('y2',gy);
  gl.setAttribute('stroke','#e8edf3');gl.setAttribute('stroke-width','1');
  svg.appendChild(gl);
  var gv=Math.round(maxVal*(1-gi/4));
  var gt=document.createElementNS('http://www.w3.org/2000/svg','text');
  gt.setAttribute('x',PAD.l-6);gt.setAttribute('y',gy+4);
  gt.setAttribute('text-anchor','end');gt.setAttribute('font-size','10');
  gt.setAttribute('fill','#9aa5b4');gt.textContent=gv;
  svg.appendChild(gt);
}}

// X axis labels
years.forEach(function(y,i){{
  var xt=document.createElementNS('http://www.w3.org/2000/svg','text');
  xt.setAttribute('x',xPos(i));xt.setAttribute('y',H-PAD.b+16);
  xt.setAttribute('text-anchor','middle');xt.setAttribute('font-size','11');
  xt.setAttribute('fill','#6b7a8d');xt.setAttribute('font-weight','600');
  xt.textContent=y;
  svg.appendChild(xt);
}});

var pathEls={{}};
sectors.forEach(function(s,si){{
  var path=document.createElementNS('http://www.w3.org/2000/svg','path');
  path.setAttribute('d',makePath(s.counts));
  path.setAttribute('fill','none');
  path.setAttribute('stroke',s.color);
  path.setAttribute('stroke-width','2.5');
  path.setAttribute('stroke-linecap','round');
  path.setAttribute('stroke-linejoin','round');
  path.setAttribute('opacity','0.85');
  path.style.transition='opacity 0.2s,stroke-width 0.2s';
  // animate draw
  var len=path.getTotalLength?path.getTotalLength():1000;
  path.style.strokeDasharray=len;
  path.style.strokeDashoffset=len;
  path.style.animation='drawLine 1.4s cubic-bezier(.4,0,.2,1) '+(si*120)+'ms forwards';
  svg.appendChild(path);
  pathEls[s.name]=path;

  // dots
  s.counts.forEach(function(c,i){{
    if(c===0)return;
    var circle=document.createElementNS('http://www.w3.org/2000/svg','circle');
    circle.setAttribute('cx',xPos(i));circle.setAttribute('cy',yPos(c));
    circle.setAttribute('r','4');circle.setAttribute('fill',s.color);
    circle.setAttribute('stroke','#fff');circle.setAttribute('stroke-width','2');
    circle.style.cursor='default';
    circle.addEventListener('mouseenter',function(e){{
      showTip(e,s.name,years[i],c);
    }});
    circle.addEventListener('mouseleave',hideTip);
    svg.appendChild(circle);
  }});
}});

// CSS animation keyframe via style tag
var styleEl=document.createElement('style');
styleEl.textContent='@keyframes drawLine{{to{{stroke-dashoffset:0}}}}';
document.head.appendChild(styleEl);

// Legend
sectors.forEach(function(s){{
  var item=document.createElement('div');
  item.className='tl-legend-item';
  item.innerHTML='<div class="tl-legend-dot" style="background:'+s.color+'"></div>'+s.name;
  item.addEventListener('mouseenter',function(){{
    Object.values(pathEls).forEach(function(p){{p.style.opacity='0.15';p.style.strokeWidth='2';}});
    if(pathEls[s.name]){{pathEls[s.name].style.opacity='1';pathEls[s.name].style.strokeWidth='3.5';}}
  }});
  item.addEventListener('mouseleave',function(){{
    Object.values(pathEls).forEach(function(p){{p.style.opacity='0.85';p.style.strokeWidth='2.5';}});
  }});
  legend.appendChild(item);
}});

function showTip(e,sector,year,count){{
  tooltip.style.display='block';
  tooltip.innerHTML='<b>'+sector+'</b><br/>'+year+': <b>'+count+'</b> thesis'+(count!==1?'es':'');
  moveTip(e);
}}
function moveTip(e){{tooltip.style.left=(e.clientX+12)+'px';tooltip.style.top=(e.clientY-38)+'px';}}
function hideTip(){{tooltip.style.display='none';}}
svg.addEventListener('mousemove',moveTip);
</script>
"""
        _render_html_iframe(_timeline_html, height=420)

elif page == "Supervisors" and PROGRAM == _ALL_PROGRAM_KEY:
    # Supervisors view is per-programme; gracefully redirect users in all-mode.
    st.markdown(
        "<div style='padding:32px 8px;'>"
        "<h3 style='color:var(--uu-blue);margin-bottom:8px;'>Supervisors are per-programme</h3>"
        "<p style='color:rgba(0,54,96,0.7);max-width:640px;'>"
        "Supervisor profiles and the directory rely on programme-specific metadata. "
        "Pick a programme below to continue."
        "</p>"
        "<div style='display:flex;flex-wrap:wrap;gap:10px;margin-top:14px;'>"
        + "".join(
            f"<a href='?program={k}&nav=Supervisors' target='_self' class='topnav-link'>{n}</a>"
            for k, n in PROGRAMME_DISPLAY_NAMES_SINGLE.items()
        )
        + "</div></div>",
        unsafe_allow_html=True,
    )

elif page == "Supervisors":
    import re as _re
    import unicodedata as _ud
    from collections import Counter as _Counter, defaultdict as _defaultdict

    # ══════════════════════════════════════════════════════════════════════
    # DATA PREP — name normalization + per-supervisor statistics
    # ══════════════════════════════════════════════════════════════════════
    _TITLE_PAT = _re.compile(
        r'^(?:[\s\.,;:]+)?(?:Prof\.?\s*Dr\.?|Prof\.?|Dr\.?|Ir\.?|Drs\.?|'
        r'Mr\.?|Ms\.?|Mrs\.?|Dhr\.?|Mw\.?|Ing\.?|Ass\.?\s*Prof\.?|'
        r'Assoc\.?\s*Prof\.?|Emer\.?(?:\s*Prof\.)?)(?!\w)\s*',
        _re.I,
    )
    _INIT_PAT = _re.compile(r'^[A-Z](?:\.[A-Z])*\.?$')
    _PARTICLES = {
        'de', 'den', 'der', 'van', 'von', 'ten', 'ter', 'te', 'op', 'het', 'la',
    }
    _NAME_FIXES = {
        # ── existing fixes ────────────────────────────────────────────────
        'marko hekkert': 'Marco Hekkert',
        'jesus rosalen carreon': 'Jesus Rosales Carreon',
        'alonzo fradejas': 'Alberto Alonso Fradejas',

        # ── missing/wrong particle in last name ───────────────────────────
        # Frank van Laerhoven (SD): "Frank Laerhoven" / "Dr. Frank Laerhoven"
        'frank laerhoven': 'Frank van Laerhoven',
        # Carel Dieperink (SD): one entry has spurious "van"
        'carel van dieperink': 'Carel Dieperink',
        # Kees van Leeuwen (WM): "Kees van de Leeuwen" has extra particle
        'kees van de leeuwen': 'Kees van Leeuwen',

        # ── typos in last name ────────────────────────────────────────────
        # Ine Dorresteijn (SD)
        'ine dorrestijn': 'Ine Dorresteijn',
        # Martin Junginger (SD, Energy)
        'martin junginer': 'Martin Junginger',
        # Thomas Bauwens (SBI)
        'thomas bouwens': 'Thomas Bauwens',
        # Elena Fumagalli (Energy)
        'elena fumagali': 'Elena Fumagalli',
        # Heitor Mancini Teixeira (SD): typo + truncations
        'heitor mancini texeira': 'Heitor Mancini Teixeira',
        'heitor teixeira': 'Heitor Mancini Teixeira',
        'heitor mancini': 'Heitor Mancini Teixeira',
        # Ioannis Lampropoulos (Energy)
        'iannis lampropoules': 'Ioannis Lampropoulos',
        # Wouter Boon (Innovation): extra "s"
        'wouter boons': 'Wouter Boon',
        # Ernst Worrell (SD)
        'ernst werrel': 'Ernst Worrell',
        # Mariska te Beest (SD): two different typos
        'mariska te beet': 'Mariska te Beest',
        'mariska the beest': 'Mariska te Beest',
        # Matthijs Janssen (SBI)
        'matthijs jansen': 'Matthijs Janssen',
        # Abe Hendriks (SBI)
        'abe hendrick': 'Abe Hendriks',
        # Gaston Heimeriks (Innovation)
        'gaston heimriks': 'Gaston Heimeriks',
        # Simona Negro (SBI): spurious "de" particle
        'simona de negro': 'Simona Negro',
        # Gert Jan Kramer (Energy/SD): hyphenated vs space
        'gert-jan kramer': 'Gert Jan Kramer',

        # ── double-surname / incomplete name cluster issues ───────────────
        # Dora Sampaio (SD): "Dora Martins Sampaio" puts last = "Martins Sampaio"
        'dora martins sampaio': 'Dora Sampaio',

        # ── reversed or initial-only names ───────────────────────────────
        # Rakhyun Kim (SD): name written reversed
        'kim rak': 'Rakhyun Kim',
        # Nick Verkade (SBI): "Verkade N." parsed as first=Verkade last=N
        'verkade n': 'Nick Verkade',

        # ── initials differ from canonical first name (different cluster) ─
        # Adriaan van der Loos (SBI): "H.Z.A. van der Loos" → first initial h ≠ a
        'h van der loos': 'Adriaan van der Loos',
        # Rens van Beek (WM): "Dr. L.P.H. van Beek" → first initial l ≠ r
        'l van beek': 'Rens van Beek',

        # ── unstripped suffixes / prefixes ────────────────────────────────
        # Joost Vervoort (SD): "Pr." is not in the title pattern
        'pr joost vervoort': 'Joost Vervoort',
        # Stefanie Lutz (WM): "PhD" at end treated as part of surname
        'stefanie lutz phd': 'Stefanie Lutz',
        # Joeri Wesseling (SBI): "Dr. J.H. Wesseling MSc" → last = "Wesseling Msc"
        'j wesseling msc': 'Joeri Wesseling',

        # ── no space in compound last name ────────────────────────────────
        # Jesus Rosales Carreon (SBI): written without space
        'jesus rosalescarreon': 'Jesus Rosales Carreon',

        # ── abbreviated last name ─────────────────────────────────────────
        # Wina Crijns-Graus (Energy): "W.H.J. Graus" drops the "Crijns-" prefix
        'w graus': 'Wina Crijns-Graus',
    }
    _AVATAR_PALETTE = [
        "#003660","#c45c00","#2e7d32","#5c3d9e","#0077b6",
        "#b00020","#00695c","#e65100","#283593","#558b2f",
    ]

    def _strip_titles(s: str) -> str:
        s = s.strip().lstrip('.,;: ')
        while True:
            m = _TITLE_PAT.match(s)
            if m:
                s = s[m.end():].strip().lstrip('.,;: ')
            else:
                return s

    def _fold_ascii(s: str) -> str:
        return ''.join(ch for ch in _ud.normalize('NFKD', s) if not _ud.combining(ch))

    def _name_tokens(s: str) -> list[str]:
        s = _strip_titles(s)
        s = _re.sub(r'\([^)]*\)', ' ', s)
        s = s.replace('/', ' ')
        s = _re.sub(r'\.(?=[A-Za-z])', ' ', s)
        s = _re.sub(r'[^\w\-\s]', ' ', s)
        s = _re.sub(r'\s+', ' ', s).strip()
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

    def _first_last_from_tokens(toks: list[str]) -> tuple[str, str] | tuple[None, None]:
        if len(toks) < 2:
            return None, None
        first = toks[0]
        start = len(toks) - 1
        # Include Dutch/French/German surname particles before the final token.
        while start - 1 >= 1 and toks[start - 1].lower() in _PARTICLES:
            start -= 1
        # If there are no particles and the previous token is not an initial,
        # keep one extra token for double surnames (e.g., Rosales Carreon).
        if start == len(toks) - 1 and start - 1 >= 1 and not _is_initial(toks[start - 1]):
            start -= 1
            while start - 1 >= 1 and toks[start - 1].lower() in _PARTICLES:
                start -= 1
        last = ' '.join(toks[start:])
        return first, last

    def _build_person(name: str) -> dict | None:
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
            return {
                'first': fixed.split()[0],
                'last': ' '.join(fixed.split()[1:]),
                'first_is_initial': len(fixed.split()[0]) == 1,
                'display': fixed,
                'key': _fold_ascii(fixed.lower()),
                'cluster_key': (
                    _fold_ascii(' '.join(fixed.split()[1:]).lower()),
                    fixed.split()[0][0].lower(),
                ),
            }
        return {
            'first': first_clean,
            'last': last_clean,
            'first_is_initial': _is_initial(first),
            'display': display,
            'key': key,
            'cluster_key': (_fold_ascii(last_clean.lower()), first_clean[0].lower()),
        }

    def _split_cell(cell) -> list:
        if pd.isna(cell): return []
        raw = str(cell).strip()
        if raw.lower() in ('n/a', 'nan', ''): return []
        parts = [_strip_titles(x) for x in raw.split(',')]
        return [p for p in parts if p and p.lower() not in ('n/a', 'nan', '') and len(p) > 1]

    # First pass — collect all names and learn canonical display name per person cluster
    _all_cln: list[str] = []
    for _c in ('Supervisor', 'Second reader'):
        if _c in df.columns:
            for _cell in df[_c].dropna():
                _all_cln.extend(_split_cell(_cell))

    _cluster_stats: dict = _defaultdict(lambda: _defaultdict(int))
    for _n in _all_cln:
        _p = _build_person(_n)
        if _p:
            _score = 3 if not _p['first_is_initial'] else 1
            _score += len(_p['first']) / 100.0
            _cluster_stats[_p['cluster_key']][_p['display']] += _score

    _cluster_canon: dict = {}
    for _k, _choices in _cluster_stats.items():
        _cluster_canon[_k] = max(_choices.items(), key=lambda kv: kv[1])[0]

    def _norm(raw: str) -> str:
        _p = _build_person(raw.strip())
        if not _p:
            return _strip_titles(raw.strip())
        return _cluster_canon.get(_p['cluster_key'], _p['display'])

    # Second pass — build supervisor rows dict
    _sups: dict = _defaultdict(lambda: {'s': [], 'r': []})
    for _, _row in df.iterrows():
        for _n in _split_cell(_row.get('Supervisor', '')):
            _cn = _norm(_n)
            if _cn: _sups[_cn]['s'].append(_row)
        for _n in _split_cell(_row.get('Second reader', '')):
            _cn = _norm(_n)
            if _cn: _sups[_cn]['r'].append(_row)

    _sups = {k: v for k, v in _sups.items()
             if k and k.lower() not in ('n/a', 'nan', '') and len(k) > 2
             and len(v['s']) + len(v['r']) >= 1}

    _PROFILES = _SUP_PROFILES

    def _stats(name: str) -> dict:
        d = _sups.get(name, {'s': [], 'r': []})
        ar = d['s'] + d['r']
        kw, meth, sec = _Counter(), _Counter(), _Counter()
        for r in ar:
            for fld in ('Keywords', 'Main sector'):
                v = str(r.get(fld, '') or '')
                if v.lower() not in ('n/a', 'nan', ''):
                    for w in _re.split(r'[,;]', v):
                        w = w.strip()
                        if len(w) > 3:
                            kw[w.title()] += 1
            for fld in ('Methodology Type', 'Specific Methods'):
                v = str(r.get(fld, '') or '')
                if v.lower() not in ('n/a', 'nan', ''):
                    for m in _re.split(r'[,;]', v):
                        m = m.strip()
                        if m and m.lower() not in ('n/a', 'nan', ''):
                            meth[m] += 1
            sv = str(r.get('Main sector', '') or '')
            if sv.lower() not in ('n/a', 'nan', ''):
                sec[sv.strip()] += 1
        years = sorted(
            {int(str(r.get('Year', ''))) for r in ar if str(r.get('Year', '')).isdigit()},
            reverse=True
        )
        return {
            'sc': len(d['s']), 'rc': len(d['r']), 'total': len(ar),
            'kw': kw.most_common(7), 'meth': meth.most_common(6),
            'sec': sec.most_common(4), 'years': years,
            's_rows': d['s'], 'r_rows': d['r'], 'all': ar,
        }

    def _avatar_color(name: str) -> str:
        return _AVATAR_PALETTE[sum(ord(c) for c in name) % len(_AVATAR_PALETTE)]

    def _initials(name: str) -> str:
        pts = name.split()
        return (pts[0][0] + pts[-1][0]).upper() if len(pts) >= 2 else name[:2].upper()

    # ══════════════════════════════════════════════════════════════════════
    # SESSION STATE
    # ══════════════════════════════════════════════════════════════════════
    for _k, _v in [
        ('sup_view', 'directory'), ('sup_selected', None),
        ('sup_search', ''), ('sup_finder_topic', ''),
        ('sup_finder_dept', 'Any'),
        ('sup_finder_results', False),
    ]:
        if _k not in st.session_state:
            st.session_state[_k] = _v

    _all_sorted = sorted(
        _sups.keys(),
        key=lambda n: len(_sups[n]['s']) + len(_sups[n]['r']),
        reverse=True,
    )

    # ══════════════════════════════════════════════════════════════════════
    # CSS
    # ══════════════════════════════════════════════════════════════════════
    st.markdown("""<style>
    .sup-page-hero {
        background: linear-gradient(135deg, #003660 0%, #0a5c8a 100%);
        border-radius: 18px; padding: 2.2rem 2.4rem 1.8rem;
        margin-bottom: 1.8rem;
    }
    .sup-page-hero h1 { font-size: 2rem; font-weight: 800; margin: 0 0 0.4rem; color: #fff; }
    .sup-page-hero p  { font-size: 1rem; opacity: 0.85; margin: 0; color: #fff; }
    .sup-page-hero-row {
        display: flex; align-items: center; justify-content: space-between;
        gap: 1.5rem; flex-wrap: wrap; margin-top: 1.2rem;
        padding-top: 1.1rem;
        border-top: 1px solid rgba(255,255,255,0.18);
    }
    .sup-page-hero-cta-text {
        font-size: 0.88rem; color: rgba(255,255,255,0.78); line-height: 1.5;
    }
    .sup-page-hero-cta-text strong { color: #fff; }
    .sup-page-hero-btn {
        display: inline-block;
        background: #ffcd00; color: #003660;
        font-weight: 800; font-size: 0.92rem;
        padding: 0.55rem 1.3rem; border-radius: 9px;
        text-decoration: none; white-space: nowrap; flex-shrink: 0;
        transition: background 0.15s, transform 0.15s;
    }
    .sup-page-hero-btn:hover { background: #f0c200; transform: translateY(-2px); }
    .sup-card-wrap {
        background: #fff; border-radius: 16px; padding: 1.3rem 1.3rem 0.9rem;
        border: 1px solid #e8edf3; box-shadow: 0 2px 12px rgba(0,54,96,0.07);
        transition: box-shadow 0.2s, transform 0.2s;
        flex: 1; display: flex; flex-direction: column; overflow: hidden;
    }
    .sup-card-wrap:hover {
        box-shadow: 0 8px 28px rgba(0,54,96,0.14); transform: translateY(-3px);
    }
    .sup-avatar {
        width: 54px; height: 54px; border-radius: 50%;
        display: inline-flex; align-items: center; justify-content: center;
        font-size: 1.25rem; font-weight: 800; color: white; margin-bottom: 0.7rem;
        flex-shrink: 0;
    }
    .sup-card-photo {
        width: 54px; height: 54px; border-radius: 50%; object-fit: cover;
        flex-shrink: 0; margin-bottom: 0.7rem;
        border: 2px solid #fff; box-shadow: 0 1px 5px rgba(0,54,96,0.14);
    }
    .sup-card-name {
        font-size: 1.04rem; font-weight: 700; color: #0a2540; margin-bottom: 0.25rem;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .sup-card-counts { font-size: 0.78rem; color: #5a6a7e; margin-bottom: 0.55rem; font-weight: 500; flex-shrink: 0; }
    .sup-tags { display: flex; flex-wrap: wrap; gap: 0.28rem; margin-bottom: 0.4rem; flex: 1; align-content: flex-start; overflow: hidden; }
    .sup-tag { background: #f0f4f9; color: #2d5a8e; font-size: 0.69rem;
               padding: 0.17rem 0.52rem; border-radius: 20px; font-weight: 600; }
    .sup-tag-matched { background: #fff3cd; color: #7c4a00; border: 1px solid #f0c040; }
    .sup-card-year { font-size: 0.71rem; color: #9aa5b4; margin-top: auto; padding-top: 0.25rem; flex-shrink: 0; }
    .sup-profile-hero {
        background: #f7f9fc; border-radius: 16px; padding: 1.8rem 2rem;
        border: 1px solid #e2e8f0; margin-bottom: 1.6rem;
        display: flex; align-items: flex-start; gap: 1.8rem; flex-wrap: wrap;
    }
    .sup-profile-avatar {
        width: 96px; height: 96px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 2.2rem; font-weight: 800; color: white; flex-shrink: 0;
    }
    .sup-profile-photo {
        width: 96px; height: 96px; border-radius: 50%; object-fit: cover;
        flex-shrink: 0; border: 2px solid #fff;
        box-shadow: 0 2px 8px rgba(0,54,96,0.12);
    }
    .sup-profile-body { display: flex; flex-direction: column; min-width: 0; flex: 1; }
    .sup-profile-name { font-size: 1.85rem; font-weight: 800; color: #0a2540; margin-bottom: 0.1rem; }
    .sup-profile-subtitle {
        font-size: 0.88rem; color: #4a6080; font-weight: 500;
        margin-bottom: 0.4rem;
    }
    .sup-stats-row { display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 0.5rem; }
    .sup-stat-pill {
        background: #eef3fa; border-radius: 10px; padding: 0.38rem 0.9rem;
        font-size: 0.8rem; font-weight: 700; color: #003660;
    }
    .sup-expertise-row {
        display: flex; flex-wrap: wrap; gap: 0.32rem; margin-top: 0.85rem;
    }
    .sup-expertise-tag {
        background: #fff; border: 1px solid #d2dce8; color: #2d5a8e;
        font-size: 0.74rem; padding: 0.22rem 0.62rem; border-radius: 14px;
        font-weight: 600;
    }
    .sup-bio {
        font-size: 0.92rem; line-height: 1.55; color: #3a4a5e;
        margin-top: 0.85rem; max-width: 62ch;
    }
    .sup-section-title {
        font-size: 0.68rem; font-weight: 800; letter-spacing: 0.13em;
        text-transform: uppercase; color: #7a8fa8; margin: 1.4rem 0 0.65rem;
    }
    .sup-kw-tag {
        display: inline-block; background: #e8f0fe; color: #1a4a8a;
        border-radius: 20px; padding: 0.24rem 0.65rem; font-size: 0.77rem;
        font-weight: 600; margin: 0.16rem;
    }
    .sup-method-bar-wrap { margin-bottom: 0.38rem; }
    .sup-method-label { font-size: 0.79rem; color: #2d3748; font-weight: 600;
                        margin-bottom: 0.1rem; display: flex; justify-content: space-between; }
    .sup-method-bar-bg { background: #edf2f7; border-radius: 6px; height: 7px; overflow: hidden; }
    .sup-method-bar-fill { height: 7px; border-radius: 6px; background: #003660; }
    .sup-thesis-row {
        background: #fff; border: 1px solid #e8edf3; border-radius: 10px;
        padding: 0.8rem 1rem; margin-bottom: 0.45rem;
        transition: box-shadow 0.15s;
    }
    .sup-thesis-row:hover { box-shadow: 0 4px 14px rgba(0,54,96,0.09); }
    .sup-thesis-title { font-size: 0.9rem; font-weight: 700; color: #0a2540; }
    .sup-thesis-meta  { font-size: 0.76rem; color: #6b7a8d; margin-top: 0.18rem; }
    .sup-finder-hero {
        background: linear-gradient(135deg, #5c3d9e 0%, #003660 100%);
        border-radius: 18px; padding: 2rem 2.4rem 1.8rem; margin-bottom: 1.8rem;
    }
    .sup-finder-hero h2 { font-size: 1.6rem; font-weight: 800; margin: 0 0 0.4rem; color: #fff; }
    .sup-finder-hero p  { font-size: 0.95rem; opacity: 0.88; margin: 0; color: #fff; }
    /* Supervisor CTA banner on directory page - removed, now integrated in hero */
    .sup-finder-cta { display: none; }
    /* White search input on directory page */
    .st-key-sup_search_input input {
        background: #ffffff !important;
        border-radius: 8px !important;
    }
    .sup-result-card {
        background: #fff; border-radius: 14px; padding: 1.2rem 1.4rem;
        border: 1px solid #e0e8f0; margin-bottom: 0.8rem;
        box-shadow: 0 2px 10px rgba(0,54,96,0.06);
    }
    .sup-result-rank {
        display: inline-flex; width: 30px; height: 30px; border-radius: 50%;
        background: #003660; color: white; align-items: center; justify-content: center;
        font-weight: 800; font-size: 0.85rem; margin-right: 0.5rem; flex-shrink: 0;
    }
    .sup-result-name { font-size: 1.04rem; font-weight: 700; color: #0a2540; }
    .sup-result-reason { font-size: 0.82rem; color: #4a6080; margin-top: 0.4rem; line-height: 1.55; }
    .sup-match-bar { height: 5px; border-radius: 4px; background: #003660; margin-top: 0.55rem; }
    .st-key-sup_finder_back button {
        background: var(--uu-yellow) !important; border: none !important;
        color: var(--uu-blue) !important; font-weight: 700 !important;
        box-shadow: 0 4px 14px rgba(255,205,0,0.35) !important;
        font-size: 0.9rem !important; padding: 0.54rem 1rem !important;
    }
    .st-key-sup_finder_back button:hover {
        background: #f0c200 !important;
        box-shadow: 0 7px 20px rgba(255,205,0,0.46) !important;
        transform: translateY(-2px) !important;
    }
    /* Clickable supervisor directory cards */
    [class*="st-key-supcard"] {
        position: relative !important;
        cursor: pointer !important;
        overflow: visible !important;
    }
    [class*="st-key-supcard"] > div,
    [class*="st-key-supcard"] [data-testid="stVerticalBlock"] {
        position: relative !important;
        overflow: visible !important;
    }
    [class*="st-key-supcard"] .stButton,
    [class*="st-key-supcard"] [data-testid="stButton"] {
        position: absolute !important;
        top: 0 !important; right: 0 !important;
        bottom: 0 !important; left: 0 !important;
        width: 100% !important; height: 100% !important;
        z-index: 99 !important;
        margin: 0 !important; padding: 0 !important;
        pointer-events: all !important;
    }
    [class*="st-key-supcard"] .stButton > button,
    [class*="st-key-supcard"] [data-testid="stButton"] > button {
        position: absolute !important;
        top: 0 !important; right: 0 !important;
        bottom: 0 !important; left: 0 !important;
        width: 100% !important; height: 100% !important;
        opacity: 0 !important; cursor: pointer !important;
        border: none !important; background: transparent !important;
        padding: 0 !important; margin: 0 !important;
        box-shadow: none !important; z-index: 99 !important;
        pointer-events: all !important;
    }
    /* Clickable thesis rows */
    [class*="st-key-supthrow"] {
        position: relative !important;
        cursor: pointer !important;
        overflow: visible !important;
    }
    [class*="st-key-supthrow"] > div,
    [class*="st-key-supthrow"] [data-testid="stVerticalBlock"] {
        position: relative !important;
        overflow: visible !important;
    }
    [class*="st-key-supthrow"] .stButton,
    [class*="st-key-supthrow"] [data-testid="stButton"] {
        position: absolute !important;
        top: 0 !important; right: 0 !important;
        bottom: 0 !important; left: 0 !important;
        width: 100% !important; height: 100% !important;
        z-index: 99 !important;
        margin: 0 !important; padding: 0 !important;
        pointer-events: all !important;
    }
    [class*="st-key-supthrow"] .stButton > button,
    [class*="st-key-supthrow"] [data-testid="stButton"] > button {
        position: absolute !important;
        top: 0 !important; right: 0 !important;
        bottom: 0 !important; left: 0 !important;
        width: 100% !important; height: 100% !important;
        opacity: 0 !important; cursor: pointer !important;
        border: none !important; background: transparent !important;
        padding: 0 !important; margin: 0 !important;
        box-shadow: none !important; z-index: 99 !important;
        pointer-events: all !important;
    }
    .sup-thesis-sdg {
        display: inline-block; border-radius: 12px; padding: 0.15rem 0.5rem;
        font-size: 0.68rem; font-weight: 700; color: #fff; margin-right: 0.3rem;
    }
    .sup-thesis-kwtag {
        display: inline-block; background: #f0f4f9; color: #2d5a8e;
        border-radius: 10px; padding: 0.13rem 0.45rem; font-size: 0.68rem;
        font-weight: 600; margin: 0.1rem 0.12rem 0 0;
    }
    </style>""", unsafe_allow_html=True)

    _view = st.session_state.sup_view

    # ══════════════════════════════════════════════════════════════════════
    # PROFILE PAGE
    # ══════════════════════════════════════════════════════════════════════
    if _view == 'profile' and st.session_state.sup_selected:
        # Resolve raw name (e.g. from thesis detail link) to canonical display name
        _raw_sel = st.session_state.sup_selected
        _sname = _raw_sel if _raw_sel in _sups else _norm(_raw_sel)
        # If still not found, try a case-insensitive scan as last resort
        if _sname not in _sups:
            _fold = _raw_sel.strip().lower()
            for _k in _sups:
                if _k.lower() == _fold:
                    _sname = _k
                    break
        _sst   = _stats(_sname)
        _scol  = _avatar_color(_sname)
        _sini  = _initials(_sname)

        _render_back_btn("back_btn_sup")

        _prof = _PROFILES.get(_sname) or {}

        # Photo: prefer UU staff photo, fall back to coloured-initials avatar.
        _photo_rel = _prof.get('photo_path')
        _avatar_html = (
            f'<div class="sup-profile-avatar" style="background:{_scol}">{_sini}</div>'
        )
        if _photo_rel:
            _photo_abs = os.path.join(os.path.dirname(__file__), _photo_rel)
            _photo_b64 = _load_image_b64(_photo_abs)
            if _photo_b64:
                _avatar_html = (
                    f'<img class="sup-profile-photo" alt="{_sname}" '
                    f'src="data:image/jpeg;base64,{_photo_b64}" />'
                )

        _subtitle_parts = [p for p in (_prof.get('position'), _prof.get('department_group')) if p]
        _subtitle_html = (
            f'<div class="sup-profile-subtitle">{" · ".join(_subtitle_parts)}</div>'
            if _subtitle_parts else ''
        )

        _expertise = _prof.get('expertise') or []
        if _expertise:
            _tags = ''.join(
                f'<span class="sup-expertise-tag">{e}</span>' for e in _expertise[:14]
            )
            _expertise_html = f'<div class="sup-expertise-row">{_tags}</div>'
        else:
            _expertise_html = ''

        _bio = _prof.get('bio')
        _bio_html = f'<div class="sup-bio">{_bio}</div>' if _bio else ''

        _hero_inner = "".join(p for p in [
            _avatar_html,
            '<div class="sup-profile-body">',
            f'<div class="sup-profile-name">{_sname}</div>',
            _subtitle_html,
            (f'<div class="sup-stats-row">'
             f'<span class="sup-stat-pill">📘 {_sst["sc"]} supervised</span>'
             f'<span class="sup-stat-pill">📖 {_sst["rc"]} second reader</span>'
             f'<span class="sup-stat-pill">🗓 {", ".join(str(y) for y in _sst["years"][:3]) if _sst["years"] else "n/a"}</span>'
             f'</div>'),
            _expertise_html,
            _bio_html,
            '</div>',
        ] if p)
        st.markdown(
            f'<div class="sup-profile-hero">{_hero_inner}</div>',
            unsafe_allow_html=True,
        )

        st.markdown("<div style='height:1.2rem'></div>", unsafe_allow_html=True)

        # Thesis lists rendered full-width below the stats band so each card
        # has room for its title (in the previous 2-column layout, cards were
        # squeezed into 60% of the page and titles wrapped aggressively).
        _tab_s, _tab_r = st.tabs([
            f"📘 Supervised ({_sst['sc']})",
            f"📖 Second Reader ({_sst['rc']})",
        ])

        def _render_thesis_list(rows, _tab_key):
            if not rows:
                st.caption("No theses in this category.")
                return
            sorted_rows = sorted(rows, key=lambda x: str(x.get('Year', '0')), reverse=True)
            for i in range(0, len(sorted_rows), 4):
                chunk = sorted_rows[i:i+4]
                cols = st.columns(4)
                for j, _r in enumerate(chunk):
                    with cols[j]:
                        cover_path, resolved_pdf_path = resolve_cover_and_pdf_paths(_r)
                        _pdf_raw = str(_r.get('Thesis_PDF', '') or '')
                        _has_pdf = bool(_pdf_raw and _pdf_raw.lower() not in ('n/a', 'nan', ''))
                        _pdf_key = _pdf_raw.replace('.pdf', '') if _has_pdf else None
                        _is_featured = bool(_r.get('Featured', False))
                        _enc_p = urllib.parse.quote(PROGRAM, safe='')
                        if _pdf_key:
                            _enc_d = urllib.parse.quote(_pdf_key, safe='')
                            card_link = f"?program={_enc_p}&details={_enc_d}"
                            card_html = (
                                f'<a href="{card_link}" class="thesis-card-link" target="_self">'
                                '<div class="thesis-card">'
                                + render_cover_html(cover_path, resolved_pdf_path, featured=_is_featured)
                                + f"<div class='thesis-title'>{_r.get('Title','Untitled')}</div>"
                                + f"<div class='thesis-meta'>{_r.get('Author(s)','')} &#8226; {_r.get('Year','')}</div>"
                                + '</div></a>'
                            )
                        else:
                            card_html = (
                                '<div class="thesis-card" style="cursor:default">'
                                + render_cover_html(cover_path, resolved_pdf_path, featured=_is_featured)
                                + f"<div class='thesis-title'>{_r.get('Title','Untitled')}</div>"
                                + f"<div class='thesis-meta'>{_r.get('Author(s)','')} &#8226; {_r.get('Year','')}</div>"
                                + '</div>'
                            )
                        st.markdown(card_html, unsafe_allow_html=True)

        with _tab_s:
            _render_thesis_list(_sst['s_rows'], 's')
        with _tab_r:
            _render_thesis_list(_sst['r_rows'], 'r')

    # ══════════════════════════════════════════════════════════════════════
    # DIRECTORY PAGE
    # ══════════════════════════════════════════════════════════════════════
    else:
        _enc_p = urllib.parse.quote(PROGRAM, safe='')
        st.markdown(
            f'<div class="sup-page-hero">'
            f'<h1>\U0001f465 Supervisor Directory</h1>'
            f'<p>Browse {len(_all_sorted)} supervisors from the {_display_name} programme &mdash; '
            f'explore their expertise, methods and supervised theses.</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

        _ds1, _ds2, _ds3 = st.columns([3, 2, 2])
        with _ds1:
            _dsearch = st.text_input(
                "Search", value=st.session_state.sup_search,
                placeholder="Search by name or topic (e.g. climate governance, energy transition…)",
                label_visibility="collapsed", key="sup_search_input",
            )
        _dir_sec_opts = ['All sectors'] + sorted({
            s for n in _all_sorted for s, _ in _stats(n)['sec']
        })
        with _ds2:
            _dfsec = st.selectbox("Sector", _dir_sec_opts, label_visibility="collapsed", key="sup_dir_sector")
        with _ds3:
            _dsort = st.selectbox(
                "Sort", ['Most supervised', 'Alphabetical', 'Most recent'],
                label_visibility="collapsed", key="sup_dir_sort",
            )
        st.session_state.sup_search = _dsearch
        # Mirror the directory search into the URL so back/forward restores it.
        _sync_supervisor_url()

        # ── Search logic: name match + expertise/bio topic match ──────────
        _qwords = [w.lower().strip() for w in _dsearch.replace(',', ' ').split() if len(w) > 2] if _dsearch else []
        _is_topic_search = _dsearch and not any(_dsearch.lower() in _n.lower() for _n in _all_sorted)

        def _topic_score(name: str) -> tuple[int, list[str]]:
            """Return (relevance_score, matched_tags) for topic-mode search."""
            if not _qwords:
                return 0, []
            _prof2 = _PROFILES.get(name, {})
            _score = 0
            _mtags: list[str] = []
            for _tag in (_prof2.get('expertise') or []):
                _tl = _tag.lower()
                _hits = sum(1 for w in _qwords if w in _tl)
                if _hits:
                    _score += 10 if _hits == len(_qwords) else _hits * 4
                    _mtags.append(_tag)
            _bio_hits = sum(1 for w in _qwords if w in (_prof2.get('bio') or '').lower())
            if _bio_hits:
                _score += _bio_hits * 2
            return _score, _mtags

        _filtered_with_score: list[tuple[str, int, list]] = []
        for _n in _all_sorted:
            if _dfsec != 'All sectors':
                if not any(_dfsec.lower() in s.lower() for s, _ in _stats(_n)['sec']):
                    continue
            if _dsearch:
                _name_hit = _dsearch.lower() in _n.lower()
                _tscore, _tmtags = _topic_score(_n)
                if _name_hit:
                    _filtered_with_score.append((_n, 1000 + _tscore, _tmtags))  # name match always wins
                elif _tscore > 0:
                    _filtered_with_score.append((_n, _tscore, _tmtags))
                # else: skip — neither name nor topic matches
            else:
                _filtered_with_score.append((_n, 0, []))

        # Sort: when searching, sort by relevance score descending; else respect _dsort
        if _dsearch:
            _filtered_with_score.sort(key=lambda x: x[1], reverse=True)
        elif _dsort == 'Alphabetical':
            _filtered_with_score.sort(key=lambda x: x[0])
        elif _dsort == 'Most recent':
            _filtered_with_score.sort(
                key=lambda x: max((_stats(x[0])['years'] or [0])), reverse=True
            )

        _filtered = [x[0] for x in _filtered_with_score]
        _score_map = {x[0]: x[1] for x in _filtered_with_score}
        _tag_map   = {x[0]: x[2] for x in _filtered_with_score}

        if not _filtered:
            st.info("No supervisors match your search.")
        else:
            _is_topic_mode = bool(_dsearch and any(_score_map[n] < 1000 for n in _filtered))
            _count_label = f"{len(_filtered)} supervisor{'s' if len(_filtered) != 1 else ''} found"
            if _dsearch and _is_topic_mode:
                _count_label += " &nbsp;·&nbsp; sorted by topic relevance"
            st.markdown(
                f"<p style='color:#7a8fa8;font-size:.82rem;margin:.2rem 0 .8rem'>{_count_label}</p>",
                unsafe_allow_html=True,
            )
            _gcols = st.columns(3, gap="medium")
            _grid_cards = []
            for _idx, _n in enumerate(_filtered):
                _dst = _stats(_n)
                _ci  = _avatar_color(_n)
                _ii  = _initials(_n)
                _rec = f"Active: {', '.join(str(y) for y in _dst['years'][:3])}" if _dst['years'] else ""
                _enc_n = urllib.parse.quote(_n, safe='')
                _enc_p = urllib.parse.quote(PROGRAM, safe='')
                _cprof = _PROFILES.get(_n, {})
                _cphoto = _cprof.get('_photo_b64', '') or ''
                _cexpertise = _cprof.get('expertise') or []
                _cavatar = (
                    f'<img class="sup-card-photo" alt="{_n}" src="data:image/jpeg;base64,{_cphoto}"/>'
                    if _cphoto else
                    f'<div class="sup-avatar" style="background:{_ci}">{_ii}</div>'
                )
                # When a topic search matched expertise tags, highlight those tags first
                _matched_tags_for_n = _tag_map.get(_n, [])
                _display_tags = _matched_tags_for_n[:3] if _matched_tags_for_n else _cexpertise[:3]
                _ctags = (
                    '<div class="sup-tags">'
                    + ''.join(
                        f'<span class="sup-tag{" sup-tag-matched" if t in _matched_tags_for_n else ""}">{t}</span>'
                        for t in _display_tags
                    )
                    + '</div>'
                    if _display_tags else ''
                )
                _cparts = [
                    '<div class="sup-card-wrap">',
                    _cavatar,
                    f'<div class="sup-card-name">{_n}</div>',
                    f'<div class="sup-card-counts">{_dst["sc"]} supervised &nbsp;·&nbsp; {_dst["rc"]} second reader</div>',
                    _ctags,
                    f'<div class="sup-card-year">{_rec}</div>',
                    '</div>',
                ]
                _grid_cards.append(
                    f'<a href="?program={_enc_p}&sup_selected={_enc_n}" class="sup-card-link" target="_self">'
                    + ''.join(p for p in _cparts if p)
                    + '</a>'
                )
            st.markdown(
                '<div class="sup-card-grid">' + ''.join(_grid_cards) + '</div>',
                unsafe_allow_html=True,
            )

