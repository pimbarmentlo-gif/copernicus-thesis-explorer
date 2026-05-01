"""Root launcher so `streamlit run dashboard.py` works from project root."""

from pathlib import Path
import runpy

_TARGET = Path(__file__).resolve().parent / "dashboard" / "dashboard.py"

if __name__ == "__main__":
    runpy.run_path(str(_TARGET), run_name="__main__")
