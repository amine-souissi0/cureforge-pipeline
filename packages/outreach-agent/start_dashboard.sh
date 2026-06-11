#!/bin/bash
cd /Users/mac/Desktop/curge/Communication-AI-Agent
exec /usr/bin/python3 -m streamlit run streamlit_app.py \
  --server.port 8501 \
  --server.headless true \
  --browser.gatherUsageStats false
