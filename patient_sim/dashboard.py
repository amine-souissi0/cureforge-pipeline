"""CureForge Patient Simulation Dashboard — Bilingual (EN/RU)."""
from __future__ import annotations
import json, sys
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patient_sim.models.patient import PatientModel
from patient_sim.pipeline import run_analysis, load_latest

st.set_page_config(page_title="CureForge — Patient OIT", page_icon="🧠",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""<style>
.agent-badge{display:inline-block;padding:2px 10px;border-radius:4px;font-size:12px;font-weight:700;margin:2px}
.ok{background:#1a4731;color:#22c55e} .err{background:#4a1a1a;color:#ef4444} .pend{background:#1a2340;color:#60a5fa}
</style>""", unsafe_allow_html=True)

patient = PatientModel()

# ── Language selector ─────────────────────────────────────────────────────────
lang = st.sidebar.radio("🌐 Language / Язык", ["🇬🇧 English (Investors)", "🇷🇺 Русский (Врачи)"])
RU = lang.startswith("🇷🇺")

def T(en, ru): return ru if RU else en

# ── Header ────────────────────────────────────────────────────────────────────
c1, c2 = st.columns([3,1])
with c1:
    st.title("🧠 CureForge — " + T("Patient OIT", "Пациент О.И.Т."))
    st.caption(T("Post-CEA Stroke | Oleg I.T., 83 y/o | GKB Konchalovskogo | Stroke: 27.05.2026",
                 "Постинсультный период (ЦЭА) | О.И.Т., 83 л. | ГКБ им. Кончаловского | Инсульт: 27.05.2026"))
with c2:
    n0 = patient.neurology.nihss_trajectory[-1]["score"]
    n_start = patient.neurology.nihss_trajectory[0]["score"]
    st.metric(T("NIHSS (latest)", "NIHSS (последний)"), n0,
              delta=f"{n_start - n0} {T('pts improved','баллов улучшение')}")

st.divider()

tab1,tab2,tab3,tab4,tab5,tab6 = st.tabs([
    T("👤 Patient Profile","👤 Профиль пациента"),
    T("🔬 Imaging","🔬 Визуализация"),
    T("▶ Run Analysis","▶ Запуск анализа"),
    T("⚕ Findings","⚕ Заключения"),
    T("🏃 Recovery Plan","🏃 План реабилитации"),
    T("📄 Export Report","📄 Экспорт отчёта"),
])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 1 — PATIENT PROFILE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab1:
    d,n,c = patient.demographics, patient.neurology, patient.comorbidities
    c1,c2,c3,c4 = st.columns(4)
    c1.metric(T("Age","Возраст"), f"{d.age} {T('y/o','лет')}")
    c2.metric("ASPECTS", n.aspects_score, delta=T("Favorable (≥7)","Благоприятный (≥7)"))
    c3.metric("CRP", f"{c.crp_mg_l} mg/L", delta=T("↑ Elevated","↑ Повышен"))
    c4.metric("eGFR", "~74 (CKD G2)")

    ca, cb = st.columns(2)
    with ca:
        st.subheader(T("Demographics","Демография"))
        st.markdown(f"""
| {T('Field','Поле')} | {T('Value','Значение')} |
|---|---|
| {T('Patient ID','ID пациента')} | `{d.patient_id}` |
| {T('Age / Sex','Возраст / Пол')} | {d.age} {T('y','л')} / {T(d.sex,'мужской')} |
| {T('Institution','Учреждение')} | {d.institution} |
| {T('Native language','Родной язык')} | {d.native_language} |
| {T('Other languages','Другие языки')} | {', '.join(d.other_languages)} |
| {T('Smoking','Курение')} | {d.smoking} |
| {T('Africa residence','Проживание в Африке')} | {d.africa_residence_years}{T('y','г')} — {d.africa_region} |
""")
    with cb:
        st.subheader(T("NIHSS Trajectory","Динамика NIHSS"))
        import pandas as pd
        nihss_df = pd.DataFrame(n.nihss_trajectory)
        nihss_df["date"] = pd.to_datetime(nihss_df["date"]).dt.strftime("%d.%m")
        st.dataframe(nihss_df.rename(columns={"date":T("Date","Дата"),"score":"NIHSS",
                     "note":T("Clinical note","Примечание")}), hide_index=True, width="stretch")
        st.caption(T("↓ Improving: 15→18→9→7 — favourable trajectory",
                     "↓ Улучшение: 15→18→9→7 — благоприятная динамика"))

    st.subheader(T("Neurological Status (01.06.2026)","Неврологический статус (01.06.2026)"))
    n1, n2 = st.columns(2)
    with n1:
        st.markdown(f"""
| {T('Domain','Домен')} | {T('Status','Статус')} |
|---|---|
| {T('Consciousness','Сознание')} | ✅ {T(n.consciousness,'ясное, ориентирован')} |
| {T('Aphasia','Афазия')} | ⚠️ {T(n.aphasia_type,'моторная (Брока)')} |
| {T('Comprehension','Понимание речи')} | ✅ {T(n.aphasia_comprehension,'сохранено')} |
| {T('Right arm','Правая рука')} | ⚠️ {T(n.right_arm,'парез — сжимает кулак')} |
| {T('Right leg','Правая нога')} | ✅ {T(n.right_leg,'практически восстановлена')} |
| {T('Swallowing','Глотание')} | ⚠️ {T(n.swallowing,'не проверено (GUSS не выполнен)')} |
""")
    with n2:
        st.subheader(T("Comorbidities","Сопутствующие заболевания"))
        st.markdown(f"""
| {T('System','Система')} | {T('Status','Статус')} |
|---|---|
| {T('Cardiac','Сердце')} | {T(c.cardiac_af,'ФП, ЧСС ~87 уд/мин')} |
| LVEF | {c.lvef_pct}% |
| {T('Scar','Рубец')} | ⚠️ {T(c.anteroseptal_scar[:45],'подозрение на переднеперегородочный рубец')} |
| {T('R-ICA','П-ВСА')} | ⚠️ {c.right_ica_plaque} |
| {T('Renal','Почки')} | {c.ckd_stage} |
| CRP | 🔴 {c.crp_mg_l} mg/L |
| UTI | 🔴 {T('Active','Активная')} |
| {T('Coagulogram','Коагулограмма')} | {"🔴 " + T('PENDING','ОЖИДАЕТСЯ') if not c.coagulogram_result else c.coagulogram_result} |
""")

    with st.expander(T("⚠️ Africa Exposure Differential","⚠️ Дифференциал: Воздействие Африки")):
        st.warning(T(
            "**27 years in Eastern Africa (1978–2005)**\n\nTests needed: Eosinophil count, Strongyloides IgG ELISA, Schistosomiasis serology\n\nStatus: HYPOTHESIS",
            "**27 лет в Восточной Африке (1978–2005)**\n\nНеобходимые анализы: Эозинофилы, IgG ELISA на Strongyloides, Серология Schistosoma\n\nСтатус: ГИПОТЕЗА"))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 2 — IMAGING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab2:
    img = patient.imaging
    st.subheader(T("Imaging Studies — ALL 3 ZIPs processed ✅","Исследования — все 3 архива обработаны ✅"))

    i1, i2, i3 = st.columns(3)
    with i1:
        st.markdown(T("#### ZIP 1 — Neck CTA","#### ZIP 1 — КТ-ангиография шеи"))
        st.success(f"✅ {img.zip1_slices} DICOM")
        st.markdown(f"""
| | |
|---|---|
| {T('Body part','Область')} | **{T('NECK','ШЕЯ')}** |
| {T('Date','Дата')} | {img.zip1_study_date} |
| {T('Slices','Срезы')} | {img.zip1_slices} |
| {T('Note','Примечание')} | {T('Post-CEA carotid assessment','Оценка после ЦЭА')} |
""")
    with i2:
        st.markdown(T("#### ZIP 2 — Brain CT ✅ NEW","#### ZIP 2 — КТ головного мозга ✅ НОВЫЙ"))
        st.success(f"✅ {img.zip2_slices} DICOM — {T('HEAD confirmed','ГОЛОВА подтверждена')}")
        st.markdown(f"""
| | |
|---|---|
| {T('Body part','Область')} | **{T('HEAD','ГОЛОВА')}** |
| {T('Date','Дата')} | {img.zip2_study_date} |
| {T('Slices','Срезы')} | {img.zip2_slices} |
| {T('Scanner','Сканер')} | {img.zip2_manufacturer} |
| KVP | {img.zip2_kvp} kV |
| {T('Slice thickness','Толщина среза')} | {img.zip2_slice_thickness_mm} mm |
| {T('Coverage','Охват')} | {img.zip2_coverage_mm} mm |
| {T('Window','Окно')} | {img.zip2_window} |
""")
        st.info(T("ASPECTS 8 — left frontal cortex M4-M5 infarct — no hemorrhage — no edema\n(Human radiologist, 28.05.2026 — not AI-computed)",
                  "ASPECTS 8 — инфаркт левой лобной коры M4-M5 — без кровоизлияния — без отёка\n(Рентгенолог, 28.05.2026 — не AI-расчёт)"))
    with i3:
        st.markdown(T("#### ZIP 3 — Follow-up Brain CT ✅","#### ZIP 3 — КТ контроль День 2 ✅"))
        st.success(T(f"✅ {img.zip3_slices} DICOM — HEAD confirmed",
                     f"✅ {img.zip3_slices} DICOM — ГОЛОВА подтверждена"))
        st.markdown(f"""
| | |
|---|---|
| {T('Body part','Область')} | **{T('HEAD','ГОЛОВА')}** |
| {T('Date','Дата')} | {img.zip3_study_date} |
| {T('Slices','Срезы')} | {img.zip3_slices} |
| {T('Scanner','Сканер')} | {img.zip3_manufacturer} |
| KVP | {img.zip3_kvp} kV ({T('low-dose','низкая доза')}) |
| {T('Slice thickness','Толщина среза')} | {img.zip3_slice_thickness_mm} mm |
| {T('Coverage','Охват')} | {img.zip3_coverage_mm} mm |
| {T('Window','Окно')} | {img.zip3_window} |
""")
        st.info(T("Day 2 CT confirms: no hemorrhagic transformation, no malignant MCA edema",
                  "КТ День 2: нет геморрагической трансформации, нет злокачественного отёка СМА"))

    st.divider()
    st.caption(T(
        "⚠️ ASPECTS was NOT computed from DICOM by AI. Source: human radiologist report 28.05.2026.",
        "⚠️ ASPECTS НЕ вычислялся ИИ по DICOM. Источник: заключение рентгенолога 28.05.2026."))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 3 — RUN ANALYSIS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab3:
    st.subheader(T("Run 4-Agent Analysis Pipeline","Запуск 4-агентного конвейера"))
    st.markdown(f"""
| {T('Step','Шаг')} | {T('Agent','Агент')} | {T('Action','Действие')} |
|---|---|---|
| 1 | **ING** | {T('Parse 8 clinical DOCX → structured JSON','Парсинг 8 DOCX → структурированный JSON')} |
| 2 | **CDS** | {T('Clinical decisions — anticoag/BP/rehab (EN+RU)','Клинические решения — антикоаг/АД/реаб (EN+RU)')} |
| 3 | **RLP** | {T('Recovery roadmap — multilingual speech plan (EN+RU)','План реабилитации — мультиязычная речь (EN+RU)')} |
| 4 | **RPT** | {T('Bilingual report — EN for investors, RU for doctors','Двуязычный отчёт — EN для инвесторов, RU для врачей')} |
""")

    coag = st.text_input(
        T("Coagulogram result (unlocks anticoagulation recommendation)",
          "Коагулограмма (разблокирует рекомендацию по антикоагуляции)"),
        placeholder=T("e.g. INR 1.2, APTT normal, Plt 180","например: МНО 1,2, АПТВ норма, Тр 180"))

    if "run_result" not in st.session_state:
        st.session_state.run_result = None

    prev = load_latest()
    if prev and not st.session_state.run_result:
        st.info(T("📂 Previous results loaded. Click Run Analysis to refresh.",
                  "📂 Загружены предыдущие результаты. Нажмите «Запуск» для обновления."))

    if st.button(T("▶ Run Analysis","▶ Запустить анализ"), type="primary"):
        bar = st.progress(0)
        status = st.empty()
        log = st.empty()
        steps = []

        def cb(d):
            bar.progress(d["progress_pct"]/100)
            status.markdown(f"**{d['step']}**")
            steps.append(f"`{d['progress_pct']}%` {d['step']}")
            log.markdown("\n\n".join(steps[-5:]))

        result = run_analysis(progress_callback=cb, coagulogram=coag.strip() or None)
        st.session_state.run_result = result

        ag = result["agents_succeeded"]
        cols = st.columns(4)
        for col, (name, ok) in zip(cols, ag.items()):
            cls = "ok" if ok else "err"
            lbl = "✅" if ok else "❌"
            col.markdown(f'<span class="agent-badge {cls}">{lbl} {name}</span>', unsafe_allow_html=True)

        if all(ag.values()):
            st.success(T(f"✅ Complete in {result['duration_seconds']}s — see Findings & Recovery tabs",
                         f"✅ Завершено за {result['duration_seconds']}с — см. вкладки Заключения и Реабилитация"))
        else:
            failed = [k for k,v in ag.items() if not v]
            st.warning(f"⚠️ Partial — failed: {', '.join(failed)}")
            # Show exact error for debugging
            for _fn in failed:
                _raw = result.get(_fn, {})
                if isinstance(_raw, dict) and "error" in _raw:
                    st.error(f"🔍 {_fn}: {_raw['error'][:300]}")
                    break

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 4 — FINDINGS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab4:
    result = st.session_state.get("run_result") or {}
    cds = result.get("cds") or (load_latest() or {}).get("model", {}).get("outputs", {}).get("cds_result", {})

    if not cds or "error" in cds:
        st.warning(T("Run analysis first, or check that GROQ_API_KEY is correct in Streamlit Cloud secrets.",
                     "Сначала запустите анализ или проверьте GROQ_API_KEY в настройках Streamlit Cloud."))
        if cds and "error" in cds:
            st.error(f"Error: {cds.get('error','?')}")
    else:
        st.subheader(T("Clinical Decision Support","Клиническая поддержка принятия решений"))
        ac = cds.get("anticoagulation", {})
        status_icon = {"BLOCKED":"🔴","RECOMMENDED":"🟢","CONDITIONAL":"🟡"}.get(str(ac.get("status","")).upper(),"⚪")
        st.markdown(f"### {status_icon} {T('Anticoagulation','Антикоагуляция')} — {ac.get('status','—')}")

        a1, a2 = st.columns(2)
        with a1:
            rec = ac.get("recommendation_ru" if RU else "recommendation_en") or ac.get("recommendation","—")
            st.markdown(f"**{T('Recommendation','Рекомендация')}:** {rec}")
            st.markdown(f"**{T('Drug','Препарат')}:** {ac.get('drug','—')} | **{T('Start day','День начала')}:** {ac.get('start_day','—')}")
            if ac.get("blocker"):
                st.error(f"🔒 {T('Blocker','Блокирующий фактор')}: {ac['blocker']}")
        with a2:
            cav = ac.get("age83_caveat_ru" if RU else "age83_caveat_en") or ac.get("age83_caveat","—")
            st.markdown(f"**{T('Citation','Источник')}:** {ac.get('citation','—')}")
            st.caption(f"⚠️ Age 83: {cav}")

        st.divider()
        col_a, col_b = st.columns(2)
        with col_a:
            bp = cds.get("bp_management", {})
            st.markdown(f"### 💊 {T('BP Management','Контроль АД')}")
            rec_bp = bp.get("recommendation_ru" if RU else "recommendation_en") or bp.get("recommendation","—")
            st.markdown(f"**{T('Target','Цель')}:** {bp.get('target_mmhg','—')}\n\n{rec_bp}\n\n*{bp.get('citation','—')}*")

        with col_b:
            reh = cds.get("rehabilitation", {})
            st.markdown(f"### 🏃 {T('Rehabilitation','Реабилитация')}")
            caut = reh.get("key_caution_ru" if RU else "key_caution_en") or reh.get("key_caution","—")
            st.markdown(f"**{T('Frequency','Частота')}:** {reh.get('frequency','—')} | **{T('Intensity','Интенсивность')}:** {reh.get('intensity','—')}\n\n⚠️ {caut}\n\n*{reh.get('citation','—')}*")

        col_c, col_d = st.columns(2)
        with col_c:
            inf = cds.get("infection_management", {})
            st.markdown(f"### 🦠 {T('Infection & CRP','Инфекция и СРБ')}")
            uti = inf.get("uti_treatment_ru" if RU else "uti_treatment_en") or inf.get("uti_treatment","—")
            st.markdown(f"**UTI:** {uti}\n\n**{T('CRP schedule','График СРБ')}:** {inf.get('serial_crp_schedule','—')}")

        with col_d:
            nut = cds.get("nutrition", {})
            st.markdown(f"### 🍽️ {T('Nutrition','Питание')}")
            rec_nut = nut.get("recommendation_ru" if RU else "recommendation_en") or nut.get("total_protein_note","—")
            st.markdown(f"**{T('Protein','Белок')}:** {nut.get('protein_target_g_per_kg','—')} g/kg/d\n\n{rec_nut}")

        pending = cds.get("pending_investigations", [])
        if pending:
            st.subheader(T("📋 Pending Investigations","📋 Необходимые исследования"))
            import pandas as pd
            rows = [{"Investigation" if not RU else "Исследование":
                     p.get("item_ru" if RU else "item_en", p.get("item","?")),
                     "Urgency/Срочность": p.get("urgency","?"),
                     "Reason/Причина": p.get("reason","?")} for p in pending]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

        flags = cds.get("red_flags", [])
        if flags:
            st.subheader(T("🚨 Red Flags","🚨 Тревожные признаки"))
            for f in flags:
                sign = f.get("sign_ru" if RU else "sign_en") or f.get("sign","?")
                action = f.get("action_ru" if RU else "action_en") or f.get("action","?")
                st.error(f"**{sign}** → {action}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 5 — RECOVERY PLAN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab5:
    result = st.session_state.get("run_result") or {}
    recovery = result.get("recovery") or {}

    # Fallback to last cached run if session cleared or agents failed
    if not recovery or "error" in recovery:
        _cached5 = load_latest()
        if _cached5:
            recovery = _cached5.get("model", {}).get("outputs", {}).get("recovery_result", {}) or {}

    if not recovery or "error" in recovery:
        st.warning(T("Run analysis first — then results appear here automatically.",
                     "Сначала запустите анализ — результаты появятся автоматически."))
    else:
        st.subheader(T("Recovery & Longevity Roadmap","Маршрут восстановления и долголетия"))
        phases = recovery.get("phases", {})

        sub_acute, sub_sub, sub_chr = st.tabs([
            T("⚡ Acute (Week 1)","⚡ Острый (Неделя 1)"),
            T("📈 Subacute (Wk 2–12)","📈 Подострый (2–12 нед)"),
            T("♾️ Chronic (3m+)","♾️ Хронический (3м+)"),
        ])

        with sub_acute:
            acute = phases.get("acute_week1", {})
            for key in ["neuro","speech","mobility","infection","nursing"]:
                val = acute.get(f"{key}_ru" if RU else f"{key}_en") or acute.get(key,"")
                if val:
                    st.markdown(f"**{key.title()}:** {val}")

        with sub_sub:
            sub = phases.get("subacute_weeks2_to_12", {})
            speech = sub.get("speech_therapy", {})
            if speech:
                st.markdown(f"#### 🗣️ {T('Speech Therapy','Речевая терапия')}")
                c1,c2 = st.columns(2)
                with c1:
                    method = speech.get("method_ru" if RU else "method_en","—")
                    lang_s = speech.get("language_strategy_ru" if RU else "language_strategy_en","—")
                    st.markdown(f"**{T('Method','Метод')}:** {method}\n\n**{T('Frequency','Частота')}:** {speech.get('frequency','—')}\n\n**{T('Strategy','Стратегия')}:** {lang_s}")
                with c2:
                    swahili = speech.get("swahili_note_ru" if RU else "swahili_note_en","—")
                    apps = speech.get("apps_ru" if RU else "apps_en","—")
                    st.markdown(f"**Swahili:** {swahili}\n\n**Apps:** {apps}")
            for key in ["motor_rehab","cardiovascular","nutrition"]:
                val = sub.get(f"{key}_ru" if RU else f"{key}_en","")
                if val: st.markdown(f"**{key.replace('_',' ').title()}:** {val}")

        with sub_chr:
            chron = phases.get("chronic_3months_plus", {})
            for key in ["maintenance","secondary_prevention","longevity_goals"]:
                val = chron.get(f"{key}_ru" if RU else f"{key}_en","")
                if val: st.markdown(f"**{key.replace('_',' ').title()}:** {val}")

        fam = recovery.get("family_guide", {})
        if fam:
            st.divider()
            st.subheader(T("👨‍👩‍👧 Family Guide","👨‍👩‍👧 Руководство для семьи"))
            f1, f2 = st.columns(2)
            with f1:
                st.markdown(T("**Communication tips:**","**Советы по общению:**"))
                for tip in fam.get("communication_tips_ru" if RU else "communication_tips_en",[]):
                    st.markdown(f"- {tip}")
            with f2:
                st.markdown(T("**⚠️ Call doctor if:**","**⚠️ Вызвать врача если:**"))
                for s in fam.get("warning_signs_ru" if RU else "warning_signs_en",[]):
                    st.markdown(f"- {s}")
            sched = fam.get("daily_schedule_ru" if RU else "daily_schedule_en","")
            if sched: st.info(sched)

        actions = recovery.get("priority_actions", [])
        if actions:
            st.subheader(T("🎯 Priority Actions","🎯 Приоритетные действия"))
            import pandas as pd
            rows = [{T("Rank","Приоритет"): a.get("rank"),
                     T("Action","Действие"): a.get("action_ru" if RU else "action_en", a.get("action","?")),
                     T("Timeline","Сроки"): a.get("timeline",""),
                     T("Owner","Ответственный"): a.get("owner","")} for a in actions]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 6 — EXPORT REPORT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab6:
    result = st.session_state.get("run_result") or {}
    report_md = result.get("report_md","") or (load_latest() or {}).get("report","")

    if not report_md:
        st.info(T("Run analysis first.","Сначала запустите анализ."))
    else:
        st.subheader(T("Clinical Report — Ready to Export","Клинический отчёт — готов к экспорту"))

        # Split EN/RU if bilingual
        if "🇷🇺" in report_md and "🇬🇧" in report_md:
            parts = report_md.split("---")
            en_part = parts[0] if parts else report_md
            ru_part = parts[1] if len(parts) > 1 else ""
            shown = ru_part if RU else en_part
        else:
            shown = report_md

        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                T("⬇ Download Full Report (.md)","⬇ Скачать полный отчёт (.md)"),
                data=report_md.encode(), file_name="CureForge_OIT_Report_ENRU.md", mime="text/markdown")
        with c2:
            patient_json = PatientModel().model_dump_json(indent=2)
            st.download_button(
                T("⬇ Download Patient Model (.json)","⬇ Скачать модель пациента (.json)"),
                data=patient_json.encode(), file_name="CureForge_OIT_PatientModel.json",
                mime="application/json")

        st.markdown("---")
        st.markdown(shown)
