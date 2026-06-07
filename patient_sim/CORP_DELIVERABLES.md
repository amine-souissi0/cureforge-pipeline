# 📋 CureForge Patient Agent — Corp Deliverables Index
## For: Saipavan & CureForge Leadership | Patient: O.I.T., 83y post-CEA stroke

---

## 📄 1. CLINICAL REPORT (in this repo)
👉 **[patient_sim/REPORT_BILINGUAL.md](./REPORT_BILINGUAL.md)** — Full bilingual EN+RU report
- NIHSS trajectory 15→18→14→12
- Anticoagulation status (Enoxaparin completed, long-term AC pending)
- All 3 CT + MRI processed
- AI Clinical Decision Support output

## 📦 2. CODE ZIP (in this repo)
👉 **[patient_sim/CureForge_Patient_Agent.zip](./CureForge_Patient_Agent.zip)** — 415KB, full 7-agent system
- All agents, dashboard, models, guides, simulation specs

## 🌐 3. LIVE DASHBOARD
👉 https://amine-souissi0-cureforge-dashboard-streamlit-app-ypvvfl.streamlit.app
- 8 tabs, bilingual EN/RU
- Run Analysis runs all 6 agents live

---

# 🎯 WHAT THE BOSS ASKED — ANSWERED

## 📷 PHYSICAL PROGRESS ON CAMERA — `WHERE, WHEN, WHAT TO DO`

**📁 Full protocol:** [patient_sim/guides/camera_recording_protocol.md](./guides/camera_recording_protocol.md)

### **WHEN** — how many times per day
- **3 sessions/day:** Morning 08:00 | Midday 13:00 | Evening 18:00 (~5 min each)
- Minimum: 1 session/day (morning)
- Same exercises EVERY DAY so the AI compares day-to-day

### **WHERE** — camera positions for RIGHT ARM
| Exercise | Camera position | Distance | Frame |
|---|---|---|---|
| Fist open/close | **FRONT** at table height | 1 m | Wrist→fingertips |
| Elbow bend | **SIDE 90° (right)** at elbow height | 1.5 m | Shoulder→hand |
| Shoulder raise | **SIDE 90°** | 2 m | Head→waist, full arm |

### **WHERE** — camera positions for RIGHT LEG
| Exercise | Camera position | Distance | Frame |
|---|---|---|---|
| Knee extension (seated) | **SIDE 90° (right)** at knee height | 2 m | Hip→foot |
| Leg raise | **SIDE 90°** | 2.5 m | Chest→toes |
| Standing balance | **FRONT** | 2.5 m | Full body+floor (caregiver beside — fall risk) |

### **WHAT TO DO** — rules
1. Phone STILL on a stand (don't hand-hold)
2. Plain wall behind, good light in front
3. Whole limb visible the entire clip
4. **SAME distance/angle every day** — mark floor with tape
5. Filename: `YYYY-MM-DD_arm_morning.mp4`

---

## 🗣️ SPEECH RECOGNITION RU/EN/SW — `WHERE, WHEN, WHAT TO DO`

**📁 Full protocol:** [patient_sim/guides/speech_recording_protocol.md](./guides/speech_recording_protocol.md)

### **WHEN** — how many times per day
- **3 sessions/day, one per language:**
  - Morning 09:30 — **Russian** (native, priority)
  - Afternoon 15:00 — **English**
  - Evening 19:30 — **Swahili** (emotional/long-term memory)
- Minimum: 1 Russian session/day

### **WHERE** — recording setup
- Quiet room
- Phone 30–40 cm from mouth
- **Front camera ON** (AI reads lips + sound together)
- Plain background

### **WHAT TO DO** — fixed task list (same every day)
1. **Sustained vowels** 10s each: A / I / U
2. **Counting 1→10** in target language
3. **Days of the week**
4. **5 everyday words** (RU: вода, хлеб, дом, рука, спасибо | EN: water, bread, house, hand, thank you | SW: maji, mkate, nyumba, mkono, asante)
5. **One sentence** repeated after caregiver
6. **Free speech** 30 sec

---

## 🧠 SPEECH RECOVERY SIMULATION MODEL

**📁 Code:** [patient_sim/agents/speech_sim_agent.py](./agents/speech_sim_agent.py)

### What it does
- Whisper-large-v3 multilingual ASR (RU/EN/SW)
- Articulation scorer (dysarthria)
- Aphasia marker detector (pauses, word-finding)
- Per-language logistic recovery curves
- Cross-language transfer model (does RU recovery pull EN/SW?)
- Daily adaptive word-list tuning (edge of patient ability)

### Milestones (predicted)
| Week | Target |
|---|---|
| 2 | Sustained vowels stable, counting 1-10 RU |
| 6 | 5-word naming RU >80%, EN emerging |
| 12 | Short sentences RU, single words EN/SW |

### **Endpoint** — where it ends
Goal: **functional Russian (daily needs) by ~month 3.** EN/SW bonus.
Simulation continuously forecasts the date this is reached and flags if the patient falls off the predicted curve → alert to clinician.

---

## 🤖 7-AGENT ARCHITECTURE
| # | Agent | Purpose | File |
|---|---|---|---|
| 1 | ING | Parse clinical docs → JSON | `agents/ingestion_agent.py` |
| 2 | CDS | Clinical Decision Support EN+RU | `agents/cds_agent.py` |
| 3 | RLP | Recovery & Longevity Planner | `agents/recovery_agent.py` |
| 4 | RPT | Bilingual report | `agents/report_agent.py` |
| 5 | PHY | Physical rehab (arm + leg) | `agents/rehab_agent.py` |
| 6 | CVT | Computer vision movement tracker | `agents/vision_agent.py` |
| 7 | SPC | Speech recovery simulation | `agents/speech_sim_agent.py` |

## 🔑 LLM Provider
- **Active:** NVIDIA NIM (`meta/llama-3.3-70b-instruct`)
- **Key:** in Streamlit Cloud → Settings → Secrets as `NVIDIA_API_KEY`
- Auto-routes: `nvapi-*` → NVIDIA | `gsk_*` → Groq

---

*Generated 07.06.2026. All content originated from the dashboard repo at amine-souissi0/cureforge-dashboard and is now committed into the corp pipeline.*
