"""Launcher for launchd — sets working directory then execs streamlit."""
import os, sys
os.chdir("/Users/mac/Desktop/curge/Communication-AI-Agent")
sys.argv = [
    "streamlit", "run", "streamlit_app.py",
    "--server.port", "8501",
    "--server.headless", "true",
    "--browser.gatherUsageStats", "false",
]
from streamlit.web import cli as st_cli
st_cli.main()
