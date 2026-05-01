# the try/except blocks below guard against missing dependencies during execution.
# we also add type-ignore comments so linters like Pylance stop complaining.
try:
    import streamlit as st  # type: ignore[import]
except ImportError as e:
    raise ImportError("streamlit is required to run this dashboard. install with `pip install streamlit`") from e

try:
    from streamlit_pdf_viewer import pdf_viewer  # type: ignore[import]
except ImportError as e:
    # pdf_viewer is optional but required for embedded PDF viewing
    raise ImportError("streamlit-pdf-viewer is required for PDF display; install via `pip install streamlit-pdf-viewer`") from e

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
import urllib.parse

# ensure file paths work regardless of current working directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROGRAM = "sbi"

# Map programme keys (used in URLs/session state) to actual folder names on disk.
_PROGRAMME_FOLDER_MAP = {
    "sbi": "sbi",
    "energy_science": "energy_science",
    "sustainable_development": "sustainable_development",
    "innovation_sciences": "innovation_sciences",
    "water_management": "water_management",
}

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
    "saved_master_track_filter", "saved_featured_only",
]
for _fk in _FILTER_KEYS:
    if _fk not in st.session_state:
        st.session_state[_fk] = [] if _fk != "saved_search_query" and _fk != "saved_featured_only" else ("" if _fk == "saved_search_query" else False)

# session state for homepage navigation
if 'page' not in st.session_state:
    st.session_state.page = "home"
if 'program' not in st.session_state:
    st.session_state.program = "sbi"

# Allow deep-links from homepage/thesis cards using query params.
_VALID_PROGRAMS = {"sbi", "energy_science", "sustainable_development", "innovation_sciences", "water_management"}
_program_from_query = st.query_params.get("program")
_details_from_query = st.query_params.get("details")

# Prioritize details links so clicking a thesis card always opens details first.
if _details_from_query:
    if _program_from_query and _program_from_query in _VALID_PROGRAMS:
        st.session_state.program = _program_from_query
    st.session_state.page = "dashboard"
    st.session_state.selected_details = str(_details_from_query)
    st.session_state.selected_pdf = None
    st.query_params.clear()
    st.rerun()

# Supervisor card click → open profile (must be before the generic program handler)
_sup_selected_from_query = st.query_params.get("sup_selected")
if _sup_selected_from_query:
    if _program_from_query and _program_from_query in _VALID_PROGRAMS:
        st.session_state.program = _program_from_query
    st.session_state.page = "dashboard"
    st.session_state.page_nav = "Supervisors"
    st.session_state.sup_selected = _sup_selected_from_query
    st.session_state.sup_view = 'profile'
    st.query_params.clear()
    st.rerun()

if _program_from_query and _program_from_query in _VALID_PROGRAMS:
    st.session_state.program = _program_from_query
    st.session_state.page = "dashboard"
    st.query_params.clear()
    st.rerun()

# Logo click → back to programmes
if st.query_params.get("back_home") == "1":
    st.session_state.page = "home"
    st.query_params.clear()
    st.rerun()

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

    /* header/title styles */
    .header-row {
        display: flex;
        align-items: center;
        gap: 16px;
        margin-bottom: 20px;
    }
    .header-logo-wrap {
        width: 64px;
        min-width: 64px;
        height: 64px;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
    }
    .header-logo {
        width: 64px;
        height: 64px;
        object-fit: contain;
        display: block;
    }
    .header-container {
        background-color: transparent;
        border: none;
        padding: 0;
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: 3px;
    }
    .header-title {
        color: var(--uu-blue);
        margin: 0;
        font-size: 1.55rem;
        font-weight: 700;
        line-height: 1.22;
        letter-spacing: -0.02em;
    }
    .header-subtitle {
        color: rgba(0,54,96,0.5);
        margin: 0;
        font-size: 0.82rem;
        font-weight: 400;
        letter-spacing: 0.01em;
    }

    /* ── Sidebar navigation items (key-based selectors for reliable styling) ── */
    section[data-testid="stSidebar"] .st-key-sidenav_Explorer,
    section[data-testid="stSidebar"] .st-key-sidenav_Supervisors,
    section[data-testid="stSidebar"] .st-key-sidenav_Find_My_Research_Topic {
        margin-bottom: 0.24rem !important;
    }
    section[data-testid="stSidebar"] .st-key-sidenav_Explorer .stButton > button,
    section[data-testid="stSidebar"] .st-key-sidenav_Supervisors .stButton > button,
    section[data-testid="stSidebar"] .st-key-sidenav_Find_My_Research_Topic .stButton > button {
        border-radius: 12px !important;
        padding: 0.56rem 0.92rem !important;
        width: 100% !important;
        text-align: left !important;
        font-size: 0.88rem !important;
        letter-spacing: 0.01em !important;
        transition: background 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease !important;
    }
    /* Inactive nav item */
    section[data-testid="stSidebar"] .st-key-sidenav_Explorer .stButton > button[data-testid="baseButton-secondary"],
    section[data-testid="stSidebar"] .st-key-sidenav_Supervisors .stButton > button[data-testid="baseButton-secondary"],
    section[data-testid="stSidebar"] .st-key-sidenav_Find_My_Research_Topic .stButton > button[data-testid="baseButton-secondary"] {
        background: rgba(255,255,255,0.11) !important;
        border: 1px solid rgba(255,255,255,0.24) !important;
        color: rgba(255,255,255,0.92) !important;
        font-weight: 600 !important;
        box-shadow: 0 3px 10px rgba(0,0,0,0.12) !important;
    }
    section[data-testid="stSidebar"] .st-key-sidenav_Explorer .stButton > button[data-testid="baseButton-secondary"]:hover,
    section[data-testid="stSidebar"] .st-key-sidenav_Supervisors .stButton > button[data-testid="baseButton-secondary"]:hover,
    section[data-testid="stSidebar"] .st-key-sidenav_Find_My_Research_Topic .stButton > button[data-testid="baseButton-secondary"]:hover {
        background: rgba(255,255,255,0.22) !important;
        border-color: rgba(255,255,255,0.40) !important;
        color: #ffffff !important;
        box-shadow: 0 7px 20px rgba(0,0,0,0.22) !important;
        transform: translateY(-2px) !important;
    }
    /* Active nav item */
    section[data-testid="stSidebar"] .st-key-sidenav_Explorer .stButton > button[data-testid="baseButton-primary"],
    section[data-testid="stSidebar"] .st-key-sidenav_Supervisors .stButton > button[data-testid="baseButton-primary"],
    section[data-testid="stSidebar"] .st-key-sidenav_Find_My_Research_Topic .stButton > button[data-testid="baseButton-primary"] {
        background: #ffffff !important;
        border: none !important;
        color: #0a3d5c !important;
        font-weight: 700 !important;
        box-shadow: 0 6px 18px rgba(0,0,0,0.18) !important;
        transform: translateY(-1px) !important;
    }
    section[data-testid="stSidebar"] .st-key-sidenav_Explorer .stButton > button[data-testid="baseButton-primary"]:hover,
    section[data-testid="stSidebar"] .st-key-sidenav_Supervisors .stButton > button[data-testid="baseButton-primary"]:hover,
    section[data-testid="stSidebar"] .st-key-sidenav_Find_My_Research_Topic .stButton > button[data-testid="baseButton-primary"]:hover {
        background: #f4f8fc !important;
        color: #07314b !important;
        box-shadow: 0 8px 22px rgba(0,0,0,0.22) !important;
        transform: translateY(-2px) !important;
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
        display: block;
    }
    .sup-card-link * {
        text-decoration: none !important;
        color: inherit !important;
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

    /* ── Back navigation buttons — match yellow UU brand (same as details action buttons) ── */
    .st-key-back_to_home button,
    .st-key-reader_back_to_explorer button,
    .st-key-details_reader_back_to_explorer button,
    .st-key-back_to_explorer_pdf_err button,
    .st-key-back_to_explorer_no_pdf button,
    .st-key-back_to_explorer_not_found button {
        background: var(--uu-yellow) !important;
        border: none !important;
        color: var(--uu-blue) !important;
        font-weight: 700 !important;
        box-shadow: 0 4px 14px rgba(255,205,0,0.35) !important;
        font-size: 0.9rem !important;
        padding: 0.54rem 1rem !important;
    }
    .st-key-back_to_home button:hover,
    .st-key-reader_back_to_explorer button:hover,
    .st-key-details_reader_back_to_explorer button:hover,
    .st-key-back_to_explorer_pdf_err button:hover,
    .st-key-back_to_explorer_no_pdf button:hover,
    .st-key-back_to_explorer_not_found button:hover {
        background: #f0c200 !important;
        box-shadow: 0 7px 20px rgba(255,205,0,0.46) !important;
        transform: translateY(-2px) !important;
        border: none !important;
    }

    /* ── Details action buttons (Full-Page Viewer + Download) — yellow brand ── */
    .st-key-details_action_buttons .stButton > button,
    .st-key-details_action_buttons .stDownloadButton > button {
        background: var(--uu-yellow) !important;
        border: none !important;
        color: var(--uu-blue) !important;
        font-weight: 700 !important;
        box-shadow: 0 4px 14px rgba(255,205,0,0.35) !important;
        font-size: 0.9rem !important;
        padding: 0.54rem 1rem !important;
    }
    .st-key-details_action_buttons .stButton > button:hover,
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
        # Load local icon from the project folder and base64 encode it
        local_file = os.path.join(PROGRAM_DIR, "sdg_icons", f"Goal-{number:02d}.png")
        if os.path.exists(local_file):
            with open(local_file, "rb") as f:
                icon_b64 = base64.b64encode(f.read()).decode("utf-8")
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


def resolve_cover_and_pdf_paths(row) -> tuple[str, str]:
    pdf_name = str(row.get("Thesis_PDF", "")).strip()
    pdf_path = ""
    if _has_value(pdf_name):
        pdf_path = os.path.join(PROGRAM_DIR, "pdfs", pdf_name)

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
        candidate_path = os.path.join(PROGRAM_DIR, "covers", candidate)
        if os.path.exists(candidate_path):
            return candidate_path, pdf_path

    return "", pdf_path


def render_cover_html(cover_path: str, pdf_path: str = "", featured: bool = False) -> str:
    """Render a fixed-size cover block so all cards align, even without an image."""
    badge = "<span class='thesis-cover-badge'>&#9733; Featured</span>" if featured else ""
    if os.path.exists(cover_path):
        with open(cover_path, "rb") as f:
            cover_b64 = base64.b64encode(f.read()).decode("utf-8")
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
    # ── Research Overview ──
    with st.container(border=True, key="detail_overview"):
        st.markdown("<div class='detail-section-header'>Research Overview</div>", unsafe_allow_html=True)
        rq = row.get("Main Research Question", "n/a")
        if _has_value(rq):
            st.markdown(f"<div class='detail-label'>Main Research Question</div>"
                        f"<div class='detail-rq'>{rq}</div>", unsafe_allow_html=True)
        else:
            _detail_field("Main Research Question", "n/a")

        abstract = row.get("Abstract/Summary", "n/a")
        if _has_value(abstract):
            with st.expander("Summary", expanded=False):
                st.markdown(f"<div class='detail-abstract'>{abstract}</div>", unsafe_allow_html=True)
        else:
            _detail_field("Summary", "n/a")

        st.markdown("<div class='detail-label'>Keywords</div>", unsafe_allow_html=True)
        render_keyword_pills(row.get("Keywords", "n/a"))

    # ── Methodology & Theory ──
    with st.container(border=True, key="detail_methodology"):
        st.markdown("<div class='detail-section-header'>Methodology & Theory</div>", unsafe_allow_html=True)
        mc1, mc2 = st.columns(2)
        with mc1:
            _detail_field("Methodology Type", row.get("Methodology Type", "n/a"))
            _detail_field("Specific Methods", row.get("Specific Methods", "n/a"))
        with mc2:
            _detail_field("Theories", row.get("Theories", "n/a"))

    # ── Research Context + Academic ──
    with st.container(border=True, key="detail_context"):
        st.markdown("<div class='detail-section-header'>Research Context</div>", unsafe_allow_html=True)
        cc1, cc2 = st.columns(2)
        with cc1:
            _detail_field("Geographical Scope", row.get("Geographical scope", "n/a"))
            st.markdown("<div class='detail-label'>SDG</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='detail-sdg-slot'>{sdg_badge(str(row.get('SDG', 'n/a')))}</div>", unsafe_allow_html=True)
        with cc2:
            _detail_field("Research Scale", row.get("Scale", row.get("Research Scale", row.get("Research scale", "n/a"))))

    # ── Academic context and partnerships are shown separately for clarity ──
    col_academic, col_partnerships = st.columns(2, gap="medium")
    with col_academic:
        with st.container(border=True, key="detail_academic"):
            st.markdown("<div class='detail-section-header'>Academic Context</div>", unsafe_allow_html=True)
            # Master Track is specific to Sustainable Development
            master_track = row.get("Master Track", None)
            if _has_value(master_track):
                _detail_field("Master Track", master_track)
            _detail_field("Supervisor", row.get("Supervisor", "n/a"))
            _detail_field("Second Reader", row.get("Second reader", row.get("Second Reader", "n/a")))

    with col_partnerships:
        with st.container(border=True, key="detail_partnerships"):
            st.markdown("<div class='detail-section-header'>Partnerships</div>", unsafe_allow_html=True)
            _detail_field("Internship Organization", row.get("Internship Organization", "n/a"))
            _detail_field("Organizations Studied", row.get("Organizations Studied", "n/a"))


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
    "sbi": "Sustainable Business and Innovation",
    "energy_science": "Energy Science",
    "sustainable_development": "Sustainable Development",
    "innovation_sciences": "Innovation Sciences",
    "water_management": "Water Management for Climate Adaptation",
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
    if not os.path.exists(asset_path):
        return ""
    with open(asset_path, "rb") as f:
        data_b64 = base64.b64encode(f.read()).decode("utf-8")
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
        if os.path.exists(bg_path):
            with open(bg_path, "rb") as f:
                bg_b64 = base64.b64encode(f.read()).decode("utf-8")
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
    if os.path.exists(_logo_path):
        with open(_logo_path, "rb") as f:
            _logo_b64 = base64.b64encode(f.read()).decode("utf-8")
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

    programme_keys = list(PROGRAMME_DISPLAY_NAMES.keys())

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


# ----- page routing ---------------------------------------------------------
if st.session_state.page == "home":
    show_homepage()
    st.stop()

# From here on, we are in dashboard mode for the selected programme.
PROGRAM = st.session_state.program
PROGRAM_DIR = os.path.abspath(
    os.path.join(BASE_DIR, "..", "programs", _PROGRAMME_FOLDER_MAP.get(PROGRAM, PROGRAM))
)

# ----- load data ------------------------------------------------------------

import zipfile

# Processed dataset produced by prepare_thesis_files.py
metadata_path = os.path.join(PROGRAM_DIR, "thesis_metadata_matched.csv")

# load metadata with graceful error handling for encoding or wrong file type
df = pd.DataFrame()

try:
    if not os.path.exists(metadata_path):
        st.error(f"Metadata file not found: {metadata_path}. Run prepare_thesis_files.py first.")
        df = pd.DataFrame()
    elif zipfile.is_zipfile(metadata_path):
        st.error(
            "The metadata file appears to be a compressed archive rather than a CSV. "
            "Please replace it with a valid thesis_metadata file (or .csv)."
        )
        df = pd.DataFrame()
    else:
        # try common encodings and separators used in programme metadata exports
        last_error = None
        loaded = False
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

        if not loaded:
            st.error(f"Could not read metadata file: {last_error}")
            df = pd.DataFrame()
except Exception as exc:
    st.error(f"Error reading metadata: {exc}")
    df = pd.DataFrame()

# continue safely even if df is empty
if not df.empty:
    # Exclude unresolved records from all dashboard views.
    if "Match_Status" in df.columns:
        df = df[~df["Match_Status"].astype(str).str.strip().str.lower().eq("not found")].copy()

    df = df.fillna("n/a")

    # Normalize year values (remove trailing .0 from float conversions)
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
    df["Year"] = df["Year"].astype("Int64")
    df["Year"] = df["Year"].astype(str).replace("<NA>", "n/a")

    # Featured theses selected by programme coordinators (SBI only).
    # Matched with a thorough process using surname + given-name checks and PDF verification.
    # Names without reliable evidence are intentionally left unmatched.
    featured_sbi_pdfs_matched = {
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

    # Featured theses for Innovation Sciences (Caspar van Bentum, Teun de Craen, Tim Dekker,
    # Bart Janssen, Luc de Jongh not yet in metadata — will activate once PDFs are added).
    featured_is_pdfs_matched = {
        "conijn_2025.pdf",        # Maike Conijn
        "khachatryan_2025.pdf",   # Lilya Khachatryan
        "raedts_2023.pdf",        # Cas Raedts
        "schuitemaker_2023.pdf",  # Nena Schuitemaker
        "trooijen_2023.pdf",      # Steven van Trooijen
        "bentum_2025.pdf",        # Caspar van Bentum (PDF not yet in system)
        "craen_2025.pdf",         # Teun de Craen (PDF not yet in system)
        "dekker_2025.pdf",        # Tim Dekker (PDF not yet in system)
        "janssen_2025.pdf",       # Bart Janssen (PDF not yet in system)
        "jongh_2025.pdf",         # Luc de Jongh (PDF not yet in system)
    }

    if PROGRAM == "sbi":
        df["Featured"] = df["Thesis_PDF"].astype(str).str.strip().isin(featured_sbi_pdfs_matched)
    elif PROGRAM == "innovation_sciences":
        df["Featured"] = df["Thesis_PDF"].astype(str).str.strip().isin(featured_is_pdfs_matched)
    else:
        df["Featured"] = False
else:
    df["Featured"] = False

pdf_folder = os.path.join(PROGRAM_DIR, "pdfs")

# ----- explorer page background colour (per-programme palette tint) -------
_PROG_BG_TINT = {
    "sbi":                    "#eef5fa",   # pale steel blue (SD's former tint)
    "energy_science":         "#fff8f0",   # pale warm amber
    "sustainable_development":"#f0f8f1",   # pale green
    "innovation_sciences":    "#f7f3fd",   # pale lavender
    "water_management":       "#f0f9ff",   # pale cyan
}
_prog_tint = _PROG_BG_TINT.get(PROGRAM, "#f8f9fa")
st.markdown(
    "<style>"
    " .stApp, .stApp > .main {"
    f"  background-color: {_prog_tint} !important;"
    "  background-image: none !important;"
    " }"
    "</style>",
    unsafe_allow_html=True,
)

# ----- navigation ----------------------------------------------------------

_display_name = PROGRAMME_DISPLAY_NAMES.get(PROGRAM, PROGRAM)

logo_path = os.path.join(PROGRAM_DIR, "assets", "uu_logo.png")
if not os.path.exists(logo_path):
    logo_path = os.path.join(BASE_DIR, "..", "programs", "sbi", "assets", "uu_logo.png")
with open(logo_path, "rb") as f:
    logo_b64 = base64.b64encode(f.read()).decode("utf-8")

st.markdown(
    f"""
    <div class="header-row">
        <div class="header-logo-wrap">
            <a href="?back_home=1" title="Back to Programmes" style="display:block;cursor:pointer;">
                <img src="data:image/png;base64,{logo_b64}" class="header-logo" style="cursor:pointer;" />
            </a>
        </div>
        <div class="header-container">
            <div class="header-title">{_display_name} Thesis Explorer</div>
            <div class="header-subtitle">MSc {_display_name} &ndash; Utrecht University</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ----- page navigation (sidebar) ------------------------------------------
if "page_nav" not in st.session_state:
    st.session_state.page_nav = "Explorer"
_VALID_PAGES = ("Explorer", "Supervisors")
if st.session_state.get("pending_page_nav") in _VALID_PAGES:
    st.session_state.page_nav = st.session_state.pending_page_nav
    st.session_state.pending_page_nav = None

page = st.session_state.page_nav

# Render clean vertical nav in sidebar
st.sidebar.markdown("<div class='sidebar-programme-label'>Navigation</div>", unsafe_allow_html=True)
for _np in _VALID_PAGES:
    _is_active = page == _np
    if st.sidebar.button(
        _np,
        key=f"sidenav_{_np.replace(' ', '_')}",
        use_container_width=True,
        type="primary" if _is_active else "secondary",
    ):
        st.session_state.page_nav = _np
        st.rerun()

st.sidebar.markdown("<hr style='border-color:rgba(255,255,255,0.09);margin:10px 0;'>", unsafe_allow_html=True)

# ----- main tabs -----------------------------------------------------------

# move filters/search into sidebar for a cleaner main area
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
    # Reset compact mode when returning to the Explorer front page or another page.
    st.session_state.details_sidebar_expanded = False

if explorer_detail_mode:
    # Fully hide sidebar — back navigation is in the main content area
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

show_explorer_filters = (
    page == "Explorer"
    and not explorer_detail_mode
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
            placeholder="Title, author, or keyword…",
            key="explorer_search_input",
        )

        with st.sidebar.expander("Filter by metadata", expanded=False):
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

            theory_options_set = set()
            if "Theories" in df.columns:
                for value in df["Theories"].tolist():
                    theory_options_set.update(_split_multi_values(value))
            theory_options = sorted(theory_options_set, key=lambda x: x.lower())

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
            theory_filter = st.multiselect(
                "Theories", theory_options,
                default=[v for v in st.session_state.saved_theory_filter if v in theory_options],
                key="filter_theory",
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
                if _k == "saved_search_query":
                    st.session_state[_k] = ""
                elif _k == "saved_featured_only":
                    st.session_state[_k] = False
                else:
                    st.session_state[_k] = []
            # Also clear the widget keys so they reset visually
            for _wk in ["filter_year", "filter_sdg", "filter_sector", "filter_method",
                         "filter_theory", "filter_geo", "filter_scale", "filter_internship_org",
                         "filter_master_track", "filter_featured", "explorer_search_input"]:
                if _wk in st.session_state:
                    del st.session_state[_wk]

        st.sidebar.button("Reset filters", on_click=_reset_filters, key="reset_filters_btn")

    else:
        search_query = ""
        year_filter = []
        sdg_filter = []
        sector_filter = []
        method_filter = []
        theory_filter = []
        geo_filter = []
        scale_filter = []
        internship_org_filter = []
        master_track_filter = []
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

    if featured_only and "Featured" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Featured"]]

    if scale_filter:
        _scale_column = "Scale" if "Scale" in filtered_df.columns else "Research Scale" if "Research Scale" in filtered_df.columns else None
        if _scale_column:
            filtered_df = filtered_df[filtered_df[_scale_column].isin(scale_filter)]

    if search_query:
        _q = search_query.strip()
        _title_match  = filtered_df["Title"].str.contains(_q, case=False, regex=False, na=False)
        _author_match = filtered_df["Author(s)"].str.contains(_q, case=False, regex=False, na=False)
        _kw_match     = filtered_df["Keywords"].str.contains(_q, case=False, regex=False, na=False)
        filtered_df = filtered_df[_title_match | _author_match | _kw_match]

    if theory_filter:
        selected_theories = {item.strip().lower() for item in theory_filter}
        filtered_df = filtered_df[
            filtered_df["Theories"].apply(
                lambda raw: bool(selected_theories.intersection({part.lower() for part in _split_multi_values(raw)}))
            )
        ]

    # show summary of active filters
    active_filters_count = sum(
        bool(value)
        for value in [
            search_query,
            year_filter,
            sdg_filter,
            sector_filter,
            method_filter,
            theory_filter,
            geo_filter,
            scale_filter,
            internship_org_filter,
            master_track_filter,
            featured_only,
        ]
    )
    # Persist current filter values so they survive navigating into/out of details view
    st.session_state.saved_search_query = search_query
    st.session_state.saved_year_filter = year_filter
    st.session_state.saved_sdg_filter = sdg_filter
    st.session_state.saved_sector_filter = sector_filter
    st.session_state.saved_method_filter = method_filter
    st.session_state.saved_theory_filter = theory_filter
    st.session_state.saved_geo_filter = geo_filter
    st.session_state.saved_scale_filter = scale_filter
    st.session_state.saved_internship_org_filter = internship_org_filter
    st.session_state.saved_master_track_filter = master_track_filter
    st.session_state.saved_featured_only = featured_only
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
            if st.button("\u2190 Back to Explorer", key="reader_back_to_explorer"):
                st.session_state.selected_pdf = None
                st.rerun()
            with open(pdf_path, "rb") as pdf_file:
                binary_data = pdf_file.read()

            st.caption("Full-page thesis viewer. Use the viewer controls to navigate and inspect the document in detail.")
            pdf_viewer(
                binary_data,
                width="100%",
                height=1100,
                zoom_level="auto",
                viewer_align="center",
            )

            st.download_button(
                label="Download Thesis PDF",
                data=binary_data,
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
            st.error("The requested thesis PDF could not be found.")
            if st.button("\u2190 Back to Explorer", key="back_to_explorer_pdf_err"):
                st.session_state.selected_pdf = None
                st.rerun()

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
                if st.button("\u2190 Back to Explorer", key="details_reader_back_to_explorer"):
                    st.session_state.selected_details = None
                    st.session_state.selected_pdf = None
                    st.rerun()

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
                    with open(pdf_path, "rb") as pdf_file:
                        binary_data = pdf_file.read()

                    pdf_viewer(
                        binary_data,
                        width="100%",
                        height=850,
                        zoom_level="auto",
                        viewer_align="center",
                    )

                    download_icon_uri = _asset_data_uri("pdf_download_icon.png", "image/png")
                    download_label = (
                        f"![download]({download_icon_uri}) Download PDF"
                        if download_icon_uri
                        else "Download PDF"
                    )

                    with st.container(key="details_action_buttons"):
                        btn_c1, btn_c2 = st.columns(2)
                        with btn_c1:
                            if st.button("Full-Page Viewer", key="details_open_full_page_viewer", width='stretch'):
                                st.session_state.selected_pdf = pdf_name
                                st.session_state.selected_details = None
                                st.rerun()
                        with btn_c2:
                            st.download_button(
                                label=download_label,
                                data=binary_data,
                                file_name=pdf_name,
                                mime="application/pdf",
                                key=f"details_download_{pdf_name}",
                                width='stretch',
                            )

                with col_meta:
                    render_structured_details_sections(matching_row)

                render_related_thesis_cards(matching_row, "details_reader_related_view")
            else:
                if st.button("\u2190 Back to Explorer", key="back_to_explorer_no_pdf"):
                    st.session_state.selected_details = None
                    st.rerun()

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
                            st.rerun()
                    else:
                        st.caption("PDF not available")

                st.markdown("")
                render_structured_details_sections(matching_row)
                render_related_thesis_cards(matching_row, "details_no_pdf_related_view")

        else:
            st.error("The requested thesis details could not be found.")
            if st.button("\u2190 Back to Explorer", key="back_to_explorer_not_found"):
                st.session_state.selected_details = None
                st.rerun()

    else:
        if st.button("← Back to Programmes", key="back_to_home"):
            st.session_state.page = "home"
            st.rerun()

        explorer_df = filtered_df.copy()
        # Always show newest theses first (e.g., 2025 -> older years).
        explorer_df["_year_sort"] = pd.to_numeric(explorer_df["Year"], errors="coerce")
        explorer_df = explorer_df.sort_values(by="_year_sort", ascending=False, na_position="last")

        # Reset page when filters change the result count
        import math
        total_theses = len(explorer_df)
        total_pages = max(1, math.ceil(total_theses / THESES_PER_PAGE))
        current_page = st.session_state.explorer_page
        if current_page >= total_pages:
            current_page = total_pages - 1
            st.session_state.explorer_page = current_page

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
                                st.rerun()
                except ImportError:
                    pass

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
                            pdf_path = os.path.join(pdf_folder, pdf_name) if pdf_name not in ("n/a", "", "nan") else ""
                            details_key = pdf_name.replace('.pdf', '') if pdf_name.endswith('.pdf') else pdf_name
                            featured_html = _featured_badge_html(bool(row.get("Featured", False)))
                            _is_featured = bool(row.get("Featured", False))

                            card_link = (
                                f"?program={urllib.parse.quote(PROGRAM, safe='')}&"
                                f"details={urllib.parse.quote(details_key, safe='')}"
                            )
                            card_html = (
                                f'<a href="{card_link}" class="thesis-card-link" target="_self">'
                                '<div class="thesis-card">'
                                + render_cover_html(cover_path, resolved_pdf_path or pdf_path, featured=_is_featured)
                                + f"<div class='thesis-title'>{row['Title']}</div>"
                                + f"<div class='thesis-meta'>{row['Author(s)']} &#8226; {row['Year']}</div>"
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
        if os.path.exists(sdg_icon_path):
            with open(sdg_icon_path, "rb") as f:
                sdg_b64 = base64.b64encode(f.read()).decode("utf-8")
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

    from collections import Counter
    from difflib import SequenceMatcher
    import re
    import numpy as np

    def normalize_keyword(keyword: str) -> str:
        k = str(keyword).lower().strip()
        k = k.replace("&", " and ").replace("/", " ").replace("-", " ")
        k = re.sub(r"[^a-z0-9\s]", " ", k)
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
        ratio = SequenceMatcher(None, a, b).ratio()
        if ratio >= 0.93:
            return True

        a_tokens = set(a.split())
        b_tokens = set(b.split())
        if not a_tokens or not b_tokens:
            return False
        overlap = len(a_tokens.intersection(b_tokens)) / max(len(a_tokens), len(b_tokens))
        return overlap >= 0.85 and abs(len(a) - len(b)) <= 10

    norm_keyword_counts = Counter()
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

    canonical_map = {}
    canonical_counts = Counter()
    canonical_keys = []

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
        import streamlit.components.v1 as _te_components

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
        _te_components.html(full_html, height=720, scrolling=False)


    st.markdown("## Knowledge Network")
    with st.container():
        import streamlit.components.v1 as components  # type: ignore[import]

        network_path = os.path.join(PROGRAM_DIR, "network", "network.html")

        if os.path.exists(network_path):
            st.caption("Interactive thesis network embedded in Programme Analytics.")

            with open(network_path, "r", encoding="utf-8") as f:
                html_content = f.read()

            components.html(html_content, height=800, scrolling=True)
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
        ('sup_finder_method', 'Any'), ('sup_finder_sector', 'Any'),
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
    .sup-card-wrap {
        background: #fff; border-radius: 16px; padding: 1.3rem 1.3rem 0.9rem;
        border: 1px solid #e8edf3; box-shadow: 0 2px 12px rgba(0,54,96,0.07);
        transition: box-shadow 0.2s, transform 0.2s; margin-bottom: 0.8rem;
    }
    .sup-card-wrap:hover {
        box-shadow: 0 8px 28px rgba(0,54,96,0.14); transform: translateY(-3px);
    }
    .sup-avatar {
        width: 54px; height: 54px; border-radius: 50%;
        display: inline-flex; align-items: center; justify-content: center;
        font-size: 1.25rem; font-weight: 800; color: white; margin-bottom: 0.7rem;
    }
    .sup-card-name { font-size: 1.04rem; font-weight: 700; color: #0a2540; margin-bottom: 0.25rem; }
    .sup-card-counts { font-size: 0.78rem; color: #5a6a7e; margin-bottom: 0.55rem; font-weight: 500; }
    .sup-tags { display: flex; flex-wrap: wrap; gap: 0.28rem; margin-bottom: 0.4rem; }
    .sup-tag { background: #f0f4f9; color: #2d5a8e; font-size: 0.69rem;
               padding: 0.17rem 0.52rem; border-radius: 20px; font-weight: 600; }
    .sup-card-year { font-size: 0.71rem; color: #9aa5b4; margin-top: 0.15rem; }
    .sup-profile-hero {
        background: #f7f9fc; border-radius: 16px; padding: 1.8rem 2rem;
        border: 1px solid #e2e8f0; margin-bottom: 1.6rem;
        display: flex; align-items: center; gap: 1.8rem;
    }
    .sup-profile-avatar {
        width: 80px; height: 80px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 2rem; font-weight: 800; color: white; flex-shrink: 0;
    }
    .sup-profile-name { font-size: 1.85rem; font-weight: 800; color: #0a2540; margin-bottom: 0.3rem; }
    .sup-stats-row { display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 0.5rem; }
    .sup-stat-pill {
        background: #eef3fa; border-radius: 10px; padding: 0.38rem 0.9rem;
        font-size: 0.8rem; font-weight: 700; color: #003660;
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
    .st-key-sup_back_to_dir button,
    .st-key-sup_finder_back button {
        background: var(--uu-yellow) !important; border: none !important;
        color: var(--uu-blue) !important; font-weight: 700 !important;
        box-shadow: 0 4px 14px rgba(255,205,0,0.35) !important;
        font-size: 0.9rem !important; padding: 0.54rem 1rem !important;
    }
    .st-key-sup_back_to_dir button:hover,
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
        _sname = st.session_state.sup_selected
        _sst   = _stats(_sname)
        _scol  = _avatar_color(_sname)
        _sini  = _initials(_sname)

        if st.button("← Back to Supervisors", key="sup_back_to_dir"):
            st.session_state.sup_view = 'directory'
            st.session_state.sup_selected = None
            st.rerun()

        st.markdown(
            f"""<div class="sup-profile-hero">
              <div class="sup-profile-avatar" style="background:{_scol}">{_sini}</div>
              <div>
                <div class="sup-profile-name">{_sname}</div>
                <div class="sup-stats-row">
                  <span class="sup-stat-pill">📘 {_sst['sc']} supervised</span>
                  <span class="sup-stat-pill">📖 {_sst['rc']} second reader</span>
                  <span class="sup-stat-pill">🗓 {', '.join(str(y) for y in _sst['years'][:3]) if _sst['years'] else 'n/a'}</span>
                </div>
              </div>
            </div>""",
            unsafe_allow_html=True,
        )

        _pc1, _pc2 = st.columns([2, 3], gap="large")

        with _pc1:
            st.markdown("<div class='sup-section-title'>Expertise Areas</div>", unsafe_allow_html=True)
            if _sst['kw']:
                st.markdown(
                    ''.join(
                        f"<span class='sup-kw-tag'>{kw} <span style='opacity:.5;font-weight:400'>×{cnt}</span></span>"
                        for kw, cnt in _sst['kw']
                    ),
                    unsafe_allow_html=True,
                )
            else:
                st.caption("No keyword data.")

            st.markdown("<div class='sup-section-title'>Methods Experience</div>", unsafe_allow_html=True)
            if _sst['meth']:
                _mmax = _sst['meth'][0][1]
                for _m, _mc in _sst['meth']:
                    _pct = int(100 * _mc / max(_mmax, 1))
                    st.markdown(
                        f"""<div class='sup-method-bar-wrap'>
                          <div class='sup-method-label'><span>{_m}</span><span>{_mc}</span></div>
                          <div class='sup-method-bar-bg'>
                            <div class='sup-method-bar-fill' style='width:{_pct}%'></div>
                          </div></div>""",
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("No method data.")

            st.markdown("<div class='sup-section-title'>Sectors</div>", unsafe_allow_html=True)
            if _sst['sec']:
                st.markdown(
                    ''.join(
                        f"<span class='sup-kw-tag' style='background:#f0faf0;color:#2e7d32'>{s} ×{c}</span>"
                        for s, c in _sst['sec']
                    ),
                    unsafe_allow_html=True,
                )
            else:
                st.caption("No sector data.")

        with _pc2:
            _tab_s, _tab_r = st.tabs([
                f"📘 Supervised ({_sst['sc']})",
                f"📖 Second Reader ({_sst['rc']})",
            ])

            _SDG_CLR = {
                '1':'#E5243B','2':'#DDA63A','3':'#4C9F38','4':'#C5192D',
                '5':'#FF3A21','6':'#26BDE2','7':'#FCC30B','8':'#A21942',
                '9':'#FD6925','10':'#DD1367','11':'#FD9D24','12':'#BF8B2E',
                '13':'#3F9A44','14':'#0A97D9','15':'#56C02B','16':'#00689D',
                '17':'#19486A',
            }

            def _render_thesis_list(rows, _tab_key):
                if not rows:
                    st.caption("No theses in this category.")
                    return
                for _ri, _r in enumerate(sorted(rows, key=lambda x: str(x.get('Year', '0')), reverse=True)):
                    _title   = str(_r.get('Title', 'Untitled'))
                    _year    = str(_r.get('Year', '') or '')
                    _author  = str(_r.get('Author(s)', '') or '')
                    _sector  = str(_r.get('Main sector', '') or '')
                    _method  = str(_r.get('Methodology Type', '') or '')
                    _org     = str(_r.get('Organizations Studied', '') or '')
                    _kws     = str(_r.get('Keywords', '') or '')
                    _country = str(_r.get('Country', '') or '')
                    _sdg_raw = str(_r.get('SDG', '') or '')
                    _pdf_raw = str(_r.get('Thesis_PDF', '') or '')
                    _has_pdf = bool(_pdf_raw and _pdf_raw.lower() not in ('n/a', 'nan', ''))
                    _pdf_key = _pdf_raw.replace('.pdf', '') if _has_pdf else None
                    # SDG badge
                    _sdg_m = _re.search(r'\d+', _sdg_raw)
                    _sdg_html = ''
                    if _sdg_m:
                        _sn = _sdg_m.group(); _sc2 = _SDG_CLR.get(_sn, '#888')
                        _sdg_html = f"<span class='sup-thesis-sdg' style='background:{_sc2}'>SDG {_sn}</span>"
                    # keyword tags (up to 3)
                    _kw_tags = ''
                    for _kw in _re.split(r'[,;]', _kws)[:3]:
                        _kw = _kw.strip()
                        if _kw and _kw.lower() not in ('n/a', 'nan', ''):
                            _kw_tags += f"<span class='sup-thesis-kwtag'>{_kw[:30]}</span>"
                    # meta line
                    _meta_parts = [p for p in [_year, _method, _sector]
                                   if p and p.lower() not in ('n/a', 'nan', '')]
                    _meta_str = ' · '.join(_meta_parts[:3])
                    # org + country
                    _org_pts = [p.strip() for p in _re.split(r'[;,]', _org)
                                if p.strip() and p.strip().lower() not in ('n/a','nan','')][:2]
                    _ctr_pts = [p.strip() for p in _re.split(r'[;,]', _country)
                                if p.strip() and p.strip().lower() not in ('n/a','nan','')][:2]
                    _loc = ', '.join(_org_pts)
                    if _ctr_pts:
                        _loc += (' — ' if _loc else '') + ', '.join(_ctr_pts)
                    _pdf_icon = ''
                    _loc_line = (f"<div class='sup-thesis-meta' style='color:#5a7a9a;margin-top:.28rem'>"
                                 f"{_loc}</div>") if _loc else ''
                    _auth_line = (f"<div class='sup-thesis-meta' style='color:#4a6a8a;font-style:italic;margin-top:.12rem'>"
                                  f"{_author}</div>") if _author and _author.lower() not in ('n/a','nan','') else ''
                    _row_ck = f"supthrow_{_tab_key}_{_ri}"
                    _card_inner = f"""<div class='sup-thesis-row' style='cursor:{"pointer" if _pdf_key else "default"}'>
                              <div style='margin-bottom:.35rem'>{_sdg_html}{_kw_tags}</div>
                              <div class='sup-thesis-title'>{_pdf_icon}{_title}</div>
                              <div class='sup-thesis-meta' style='margin-top:.22rem'>{_meta_str}</div>
                              {_auth_line}{_loc_line}
                            </div>"""
                    if _pdf_key:
                        _enc_p = urllib.parse.quote(PROGRAM, safe='')
                        _enc_d = urllib.parse.quote(_pdf_key, safe='')
                        st.markdown(
                            f'<a href="?program={_enc_p}&details={_enc_d}" class="sup-card-link" target="_self">{_card_inner}</a>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(_card_inner, unsafe_allow_html=True)

            with _tab_s:
                _render_thesis_list(_sst['s_rows'], 's')
            with _tab_r:
                _render_thesis_list(_sst['r_rows'], 'r')

    # ══════════════════════════════════════════════════════════════════════
    # FINDER PAGE
    # ══════════════════════════════════════════════════════════════════════
    elif _view == 'finder':
        if st.button("← Back to Directory", key="sup_finder_back"):
            st.session_state.sup_view = 'directory'
            st.session_state.sup_finder_results = False
            st.rerun()

        st.markdown("""<div class="sup-finder-hero">
          <h2>🎯 Who Should Supervise My Thesis?</h2>
          <p>Describe your research interests and we'll match you with the best-fit supervisors
             based on their full thesis supervision history.</p>
        </div>""", unsafe_allow_html=True)

        _fa, _fb, _fc = st.columns([3, 2, 2])
        with _fa:
            _ftopic = st.text_input(
                "Research topic or keywords",
                value=st.session_state.sup_finder_topic,
                placeholder="e.g. energy transition, governance, SMEs, circular economy…",
                key="sup_topic_input",
            )
        _all_meth_opts = ['Any'] + sorted({
            m for n in _all_sorted for m, _ in _stats(n)['meth']
        })
        _all_sec_opts = ['Any'] + sorted({
            s for n in _all_sorted for s, _ in _stats(n)['sec']
        })
        with _fb:
            _fmethod = st.selectbox("Preferred method", _all_meth_opts, key="sup_method_input")
        with _fc:
            _fsector = st.selectbox("Preferred sector", _all_sec_opts, key="sup_sector_input")

        if st.button("Find matching supervisors →", key="sup_run_finder", type="primary"):
            st.session_state.sup_finder_topic  = _ftopic
            st.session_state.sup_finder_method = _fmethod
            st.session_state.sup_finder_sector = _fsector
            st.session_state.sup_finder_results = True
            st.rerun()

        if st.session_state.sup_finder_results and (
            st.session_state.sup_finder_topic
            or st.session_state.sup_finder_method != 'Any'
            or st.session_state.sup_finder_sector != 'Any'
        ):
            _qt     = st.session_state.sup_finder_topic
            _qm     = st.session_state.sup_finder_method
            _qs     = st.session_state.sup_finder_sector
            _qwords = [w.lower().strip() for w in _qt.split() if len(w) > 2] if _qt else []

            _scored = []
            for _n in _all_sorted:
                _st2   = _stats(_n)
                _score = 0
                _reas  = []

                if _qwords:
                    _tm = sum(
                        1 for _r in _st2['all']
                        if any(w in ' '.join([
                            str(_r.get('Title', '')),
                            str(_r.get('Keywords', '')),
                            str(_r.get('Abstract/Summary', '')),
                            str(_r.get('Main sector', '')),
                        ]).lower() for w in _qwords)
                    )
                    if _tm:
                        _score += _tm * 3
                        _reas.append(f"{_tm} thesis{'es' if _tm > 1 else ''} matching your topic")

                if _qm != 'Any':
                    _mm = sum(1 for _r in _st2['all']
                              if _qm.lower() in str(_r.get('Methodology Type', '')).lower()
                              or _qm.lower() in str(_r.get('Specific Methods', '')).lower())
                    if _mm:
                        _score += _mm * 4
                        _reas.append(f"Experience with {_qm.lower()} ({_mm} theses)")

                if _qs != 'Any':
                    _sm2 = sum(1 for _r in _st2['all']
                               if _qs.lower() in str(_r.get('Main sector', '')).lower())
                    if _sm2:
                        _score += _sm2 * 4
                        _reas.append(f"Active in {_qs} ({_sm2} theses)")

                if _st2['sc'] >= 8:
                    _score += 2
                if _score > 0:
                    _scored.append((_n, _score, _reas, _st2))

            _scored.sort(key=lambda x: x[1], reverse=True)
            _top = _scored[:8]

            if _top:
                _max_sc = _top[0][1]
                st.markdown(f"### Top {len(_top)} Matches")
                for _rank, (_n, _sc2, _reas2, _st3) in enumerate(_top, 1):
                    _pct    = int(100 * _sc2 / max(_max_sc, 1))
                    _ci     = _avatar_color(_n)
                    _ii     = _initials(_n)
                    _kw_str = ', '.join(kw for kw, _ in _st3['kw'][:3])
                    _enc_n = urllib.parse.quote(_n, safe='')
                    _enc_p = urllib.parse.quote(PROGRAM, safe='')
                    st.markdown(
                        f"""<a href="?program={_enc_p}&sup_selected={_enc_n}" class="sup-card-link" target="_self">
                          <div class="sup-result-card">
                            <div style="display:flex;align-items:center;gap:0.8rem;margin-bottom:0.5rem">
                              <span class="sup-result-rank">{_rank}</span>
                              <div class="sup-avatar" style="background:{_ci};width:40px;height:40px;font-size:1rem;margin-bottom:0">{_ii}</div>
                              <div>
                                <div class="sup-result-name">{_n}</div>
                                <div style="font-size:.76rem;color:#6b7a8d">{_st3['sc']} supervised · {_st3['rc']} second reader</div>
                              </div>
                              <div style="margin-left:auto;font-size:.88rem;font-weight:800;color:#003660">{_pct}% match</div>
                            </div>
                            <div class="sup-match-bar" style="width:{_pct}%"></div>
                            <div class="sup-result-reason">{'&nbsp;&nbsp;·&nbsp;&nbsp;'.join(f'✓ {r}' for r in _reas2)}</div>
                            {f"<div style='margin-top:.38rem;font-size:.74rem;color:#8a95a3'>Key areas: {_kw_str}</div>" if _kw_str else ''}
                          </div>
                        </a>""",
                        unsafe_allow_html=True,
                    )
            else:
                st.info("No supervisors matched your criteria. Try broader keywords or fewer filters.")

    # ══════════════════════════════════════════════════════════════════════
    # DIRECTORY PAGE
    # ══════════════════════════════════════════════════════════════════════
    else:
        st.markdown(
            f"""<div class="sup-page-hero">
              <h1>👥 Supervisor Directory</h1>
              <p>Browse {len(_all_sorted)} supervisors from the {_display_name} programme —
              explore their expertise, methods and supervised theses.</p>
            </div>""",
            unsafe_allow_html=True,
        )

        _cta_c, _ = st.columns([2, 3])
        with _cta_c:
            if st.button("🎯 Find My Supervisor", key="sup_open_finder", type="primary"):
                st.session_state.sup_view = 'finder'
                st.rerun()

        st.markdown("")
        _ds1, _ds2, _ds3 = st.columns([3, 2, 2])
        with _ds1:
            _dsearch = st.text_input(
                "Search", value=st.session_state.sup_search,
                placeholder="Search by name…",
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

        _filtered = []
        for _n in _all_sorted:
            if _dsearch and _dsearch.lower() not in _n.lower():
                continue
            if _dfsec != 'All sectors':
                if not any(_dfsec.lower() in s.lower() for s, _ in _stats(_n)['sec']):
                    continue
            _filtered.append(_n)

        if _dsort == 'Alphabetical':
            _filtered = sorted(_filtered)
        elif _dsort == 'Most recent':
            _filtered = sorted(_filtered, key=lambda n: max((_stats(n)['years'] or [0])), reverse=True)

        if not _filtered:
            st.info("No supervisors match your search.")
        else:
            st.markdown(
                f"<p style='color:#7a8fa8;font-size:.82rem;margin:.2rem 0 .8rem'>"
                f"{len(_filtered)} supervisor{'s' if len(_filtered) != 1 else ''} found</p>",
                unsafe_allow_html=True,
            )
            _gcols = st.columns(3, gap="medium")
            for _idx, _n in enumerate(_filtered):
                _dst = _stats(_n)
                _ci  = _avatar_color(_n)
                _ii  = _initials(_n)
                _tag_html = ''.join(
                    f"<span class='sup-tag'>{kw}</span>" for kw, _ in _dst['kw'][:3]
                ) or "<span class='sup-tag' style='opacity:.45'>—</span>"
                _rec = f"Active: {', '.join(str(y) for y in _dst['years'][:3])}" if _dst['years'] else ""
                with _gcols[_idx % 3]:
                    _enc_n = urllib.parse.quote(_n, safe='')
                    _enc_p = urllib.parse.quote(PROGRAM, safe='')
                    st.markdown(
                        f"""<a href="?program={_enc_p}&sup_selected={_enc_n}" class="sup-card-link" target="_self">
                          <div class="sup-card-wrap">
                            <div class="sup-avatar" style="background:{_ci}">{_ii}</div>
                            <div class="sup-card-name">{_n}</div>
                            <div class="sup-card-counts">{_dst['sc']} supervised &nbsp;·&nbsp; {_dst['rc']} second reader</div>
                            <div class="sup-tags">{_tag_html}</div>
                            <div class="sup-card-year">{_rec}</div>
                          </div>
                        </a>""",
                        unsafe_allow_html=True,
                    )

