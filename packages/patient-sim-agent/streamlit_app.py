"""CureForge — Patient Simulation Dashboard (Streamlit Cloud entry point)."""
import sys, os
from pathlib import Path

# Ensure repo root is on the path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# Execute dashboard directly (avoids import-time Streamlit conflicts)
exec(open(ROOT / "patient_sim" / "dashboard.py").read())
