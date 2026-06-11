# Patient Medical AI — 7-agent pipeline (ClickUp 86exv176h)

Post-CEA stroke recovery simulation for Patient O.I.T. (83y).

## Run

```bash
pip install -r ../outreach-agent/requirements.txt
export NVIDIA_API_KEY=...   # or OPENAI_API_KEY
streamlit run streamlit_app.py
```

## Protocols

| Protocol | File | Schedule |
|----------|------|----------|
| Camera (arm + leg) | `guides/camera_recording_protocol.md` | 08:00 / 13:00 / 18:00 daily |
| Speech (RU/EN/Swahili) | `guides/speech_recording_protocol.md` | 09:30 / 15:00 / 19:30 daily |

## Agents

| # | Agent | Module |
|---|-------|--------|
| 5 | Physical rehab | `agents/rehab_agent.py` |
| 6 | CV movement tracker | `agents/vision_agent.py` |
| 7 | Speech simulation | `agents/speech_sim_agent.py` |

Full pipeline: `pipeline.py` | Dashboard: `dashboard.py` (EN/RU toggle)
