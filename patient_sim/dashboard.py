"""CureForge Patient Simulation Dashboard — 8-tab bilingual (EN/RU)."""
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
.agent-badge{display:inline-block;padding:3px 10px;border-radius:4px;font-size:12px;font-weight:700;margin:2px}
.ok{background:#1a4731;color:#22c55e}.err{background:#4a1a1a;color:#ef4444}.pend{background:#1a2340;color:#60a5fa}
.cure-card{background:#1e2329;border-left:4px solid #00c49f;padding:10px 14px;border-radius:0 6px 6px 0;margin:6px 0}
</style>""", unsafe_allow_html=True)

patient = PatientModel()

# ── Language toggle — visible in header ───────────────────────────────────────
lang_col, _ = st.columns([1, 4])
with lang_col:
    lang = st.radio("🌐", ["🇬🇧 EN", "🇷🇺 RU"], horizontal=True, label_visibility="collapsed")
RU = lang == "🇷🇺 RU"
def T(en, ru): return ru if RU else en

# ── Header ────────────────────────────────────────────────────────────────────
c1, c2 = st.columns([3, 1])
with c1:
    st.title("🧠 " + T("CureForge — Patient OIT", "CureForge — Пациент О.И.Т."))
    st.caption(T("Post-CEA Stroke | Oleg I.T., 83 y/o | GKB Konchalovskogo | Stroke: 27.05.2026",
                 "Инсульт после ЦЭА | О.И.Т., 83 л. | ГКБ Кончаловского | Инсульт: 27.05.2026"))
with c2:
    n0 = patient.neurology.nihss_trajectory[-1]["score"]
    n_start = patient.neurology.nihss_trajectory[0]["score"]
    st.metric(T("NIHSS (latest)", "NIHSS (последний)"), n0,
              delta=f"{n_start - n0} {T('pts improved','баллов улучшение')}")
st.divider()

# ── Get results (session state → cache fallback) ───────────────────────────────
def _get_results():
    """Get best available results: session state → cached file."""
    sr = st.session_state.get("run_result") or {}
    cached = load_latest() or {}
    def _pick(key, fallback_path):
        val = sr.get(key)
        if val and isinstance(val, dict) and "error" not in val:
            return val
        # fallback to cached model outputs
        return cached.get("model", {}).get("outputs", {}).get(fallback_path, {}) or {}
    return {
        "cds":      _pick("cds", "cds_result"),
        "recovery": _pick("recovery", "recovery_result"),
        "rehab":    sr.get("rehab") or {},
        "cv":       sr.get("cv") or {},
        "report":   sr.get("report_md") or cached.get("report", ""),
    }

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab1,tab2,tab3,tab4,tab5,tab6,tab7,tab8 = st.tabs([
    T("👤 Profile","👤 Профиль"),
    T("🔬 Imaging","🔬 Визуализация"),
    T("▶ Run Analysis","▶ Анализ"),
    T("⚕ Findings","⚕ Заключения"),
    T("🏃 Recovery","🏃 Реабилитация"),
    T("💪 Physio","💪 ЛФК"),
    T("📷 CV Tracker","📷 CV Трекер"),
    T("📄 Export","📄 Экспорт"),
])

# ━━ TAB 1 — PATIENT PROFILE + CURE FINDINGS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab1:
    d,n,c = patient.demographics, patient.neurology, patient.comorbidities

    # CURE FINDINGS BANNER at top
    st.subheader(T("🔍 Key CURE Findings", "🔍 Ключевые находки CureForge"))
    f1,f2,f3,f4 = st.columns(4)
    f1.markdown(f'<div class="cure-card">🔴 <b>{T("Anticoagulation","Антикоагуляция")}</b><br>{T("Pending decision for AF","Решение по ФП ожидается")}</div>', unsafe_allow_html=True)
    f2.markdown(f'<div class="cure-card">⚠️ <b>{T("Aphasia","Афазия")}</b><br>{T("Complex motor + dysarthria","Комплексная мотор + дизартрия")}</div>', unsafe_allow_html=True)
    f3.markdown(f'<div class="cure-card">🟡 <b>{T("Rankin 5","Рэнкин 5")}</b><br>{T("Severe — rehab Stage 2","Тяжёлая — этап реаб. 2")}</div>', unsafe_allow_html=True)
    f4.markdown(f'<div class="cure-card">✅ <b>{T("No hemorrhage","Нет кровоизлияния")}</b><br>{T("ASPECTS 8 stable","ASPECTS 8 стабильный")}</div>', unsafe_allow_html=True)

    st.divider()
    c1m,c2m,c3m,c4m = st.columns(4)
    c1m.metric(T("Age","Возраст"), f"{d.age} {T('y/o','лет')}")
    c2m.metric("ASPECTS", n.aspects_score, delta=T("Favorable (≥7)","Благоприятный (≥7)"))
    c3m.metric("CRP", f"{c.crp_mg_l} mg/L", delta=T("↑ Elevated","↑ Повышен"))
    c4m.metric("eGFR", f"76.7 (CKD G2)")

    ca,cb = st.columns(2)
    with ca:
        st.subheader(T("Demographics","Демография"))
        st.markdown(f"""
| {T('Field','Поле')} | {T('Value','Значение')} |
|---|---|
| {T('Patient','Пациент')} | {d.full_name if hasattr(d,'full_name') else d.name_initials} |
| {T('Age / Sex','Возраст / Пол')} | {d.age} {T('y','л')} / {T('male','мужской')} |
| {T('Institution','Учреждение')} | {d.institution} |
| {T('Admission','Поступление')} | {getattr(d,'admission_date','26.05.2026 18:22')} |
| {T('Languages','Языки')} | {', '.join(d.other_languages)} |
| {T('Smoking','Курение')} | {d.smoking} |
| {T('Africa','Африка')} | {d.africa_residence_years}y — {d.africa_region} |
""")
        st.subheader(T("Functional Scales (03.06.26)","Функциональные шкалы (03.06.26)"))
        rankin = getattr(n,'rankin_scale',5)
        river = getattr(n,'rivermead_index',2)
        srm = getattr(n,'srm_score',5)
        st.markdown(f"""
| {T('Scale','Шкала')} | {T('Score','Балл')} | {T('Meaning','Значение')} |
|---|---|---|
| Modified Rankin | **{rankin}** | {T('Severe disability','Тяжёлая инвалидизация')} |
| Rivermead | **{river}** | {T('Minimal mobility','Минимальная мобильность')} |
| SRM | **{srm}** | {T('Needs intensive rehab','Требует интенсивной реаб.')} |
""")
    with cb:
        st.subheader(T("NIHSS Trajectory","Динамика NIHSS"))
        import pandas as pd
        nihss_df = pd.DataFrame(n.nihss_trajectory)
        nihss_df["date"] = pd.to_datetime(nihss_df["date"]).dt.strftime("%d.%m")
        st.dataframe(nihss_df.rename(columns={"date":T("Date","Дата"),"score":"NIHSS","note":T("Note","Примечание")}),
                     hide_index=True, width="stretch")
        st.caption(T("↓ Improving: 15→18→14→12 — minimum confirmed 12","↓ Улучшение: 15→18→14→12 — минимум подтверждён 12"))

        st.subheader(T("Neurological Status","Неврологический статус"))
        st.markdown(f"""
| {T('Domain','Домен')} | {T('Status','Статус')} |
|---|---|
| {T('Consciousness','Сознание')} | ✅ {T('Clear, oriented','Ясное, ориентирован')} |
| {T('Aphasia','Афазия')} | ⚠️ {T('Complex motor + dysarthria','Комплексная мотор + дизартрия')} |
| {T('Right arm','Правая рука')} | ⚠️ {T('Paresis — makes fist','Парез — сжимает кулак')} |
| {T('Right leg','Правая нога')} | ✅ {T('Nearly recovered','Практически восстановлена')} |
| {T('Cognition','Когниция')} | ⚠️ {T('Impairment noted','Нарушения отмечены')} |
| {T('Trajectory','Динамика')} | ✅ {T('IMPROVEMENT','УЛУЧШЕНИЕ')} |
""")

    st.subheader(T("Comorbidities","Сопутствующие заболевания"))
    cn1,cn2 = st.columns(2)
    with cn1:
        st.markdown(f"""
| {T('System','Система')} | {T('Status','Статус')} |
|---|---|
| {T('Cardiac','Сердце')} | AF HR 66-83-113 bpm |
| {T('Echo','ЭхоКГ')} | LVEF 56%, no WMA |
| {T('Scar','Рубец')} | ✅ {T('REMOVED on ECG trend','Снято по динамике ЭКГ')} |
| {T('R-ICA','П-ВСА')} | ⚠️ 35-40% Plaque RADS III |
| {T('Renal','Почки')} | CKD G2 (eGFR 76.7) |
""")
    with cn2:
        st.markdown(f"""
| {T('Lab','Лаб')} | {T('Value','Значение')} |
|---|---|
| CRP (29.05) | 🔴 22.95 mg/L |
| WBC (30.05) | ✅ 9.45 (normalised) |
| INR (admit) | ⚠️ 2.08 (elevated) |
| Eosinophils | ✅ 0.24% (LOW — tropical -) |
| UTI | 🔴 {T('Active','Активная')} |
| {T('Coagulogram','Коагулограмма')} | ⚠️ {T('Long-term AC decision pending','Решение по АК ожидается')} |
""")

    with st.expander(T("⚠️ Africa Differential — WEAKENED","⚠️ Дифференциал Африки — ОСЛАБЛЕН")):
        st.info(T(
            "27y in Eastern Africa (1978–2005). However: eosinophils 0.24% (LOW — below normal range). Strongyloides hypothesis significantly weakened. Standard tropical screen still reasonable but not urgent.",
            "27 лет в Восточной Африке (1978–2005). Однако: эозинофилы 0,24% (НИЗКИЕ — ниже нормы). Гипотеза стронгилоидоза значительно ослаблена. Стандартный тропический скрининг возможен, но не срочен."))

# ━━ TAB 2 — IMAGING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab2:
    img = patient.imaging
    st.subheader(T("Imaging Studies — ALL 3 ZIPs + MRI ✅","Исследования — все 3 архива + МРТ ✅"))

    i1,i2,i3,i4 = st.columns(4)
    with i1:
        st.markdown(T("**ZIP 1 — Neck CTA**","**ZIP 1 — КТА шеи**"))
        st.success(f"✅ {img.zip1_slices} DICOM")
        st.caption(T("27.05.2026 | Post-CEA carotid","27.05.2026 | Оценка после ЦЭА"))
    with i2:
        st.markdown(T("**ZIP 2 — Brain CT Day 1**","**ZIP 2 — КТ головы День 1**"))
        st.success(f"✅ {img.zip2_slices} DICOM | HEAD")
        st.caption(f"27.05.2026 | KVP {img.zip2_kvp} | {img.zip2_manufacturer}")
    with i3:
        st.markdown(T("**ZIP 3 — Brain CT Day 2**","**ZIP 3 — КТ головы День 2**"))
        st.success(f"✅ {img.zip3_slices} DICOM | HEAD")
        st.caption(f"28.05.2026 | KVP {img.zip3_kvp} {T('low-dose','низкая доза')}")
    with i4:
        st.markdown(T("**MRI — 27.05.2026**","**МРТ — 27.05.2026**"))
        st.success(T("✅ Confirmed acute stroke","✅ Подтверждён острый инсульт"))
        st.caption(T("Fazekas 2, GCA 1","Fazekas 2, GCA 1"))

    st.info(T(f"ASPECTS 8 — {img.aspects_from_radiologist}",
              f"ASPECTS 8 — {img.aspects_from_radiologist}"))
    st.caption(T("⚠️ ASPECTS NOT AI-computed — from human radiologist 28.05.2026",
                 "⚠️ ASPECTS НЕ вычислен ИИ — из заключения рентгенолога 28.05.2026"))

# ━━ TAB 3 — RUN ANALYSIS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab3:
    st.subheader(T("Run 6-Agent Analysis Pipeline","Запуск 6-агентного конвейера"))
    st.markdown(f"""
| {T('Step','Шаг')} | {T('Agent','Агент')} | {T('Action','Действие')} |
|---|---|---|
| 1 | **ING** | {T('Parse clinical docs → structured JSON','Парсинг документов → структурированный JSON')} |
| 2 | **CDS** | {T('Clinical decisions — anticoag/BP/rehab (EN+RU)','Клинические решения (EN+RU)')} |
| 3 | **RLP** | {T('Recovery roadmap — trilingual (EN/RU/SW)','План реабилитации (EN/RU)')} |
| 4 | **RPT** | {T('Bilingual report — EN investors / RU doctors','Двуязычный отчёт')} |
| 5 | **PHY** | {T('Physical rehab — right arm + leg protocol','ЛФК — правая рука и нога')} |
| 6 | **CVT** | {T('Computer vision movement tracker design','Трекер движений компьютерного зрения')} |
""")

    coag = st.text_input(
        T("Coagulogram result (unlocks anticoagulation recommendation)",
          "Коагулограмма (разблокирует рекомендацию по антикоагуляции)"),
        placeholder=T("e.g. INR 1.2, APTT normal, Plt 180","МНО 1,2, АПТВ норма, Тр 180"))

    if "run_result" not in st.session_state:
        st.session_state.run_result = None

    prev = load_latest()
    if prev:
        st.info(T("📂 Previous results loaded — tabs show cached data. Click Run Analysis to refresh.",
                  "📂 Загружены предыдущие результаты. Нажмите «Запуск» для обновления."))

    if st.button(T("▶ Run Analysis","▶ Запустить анализ"), type="primary"):
        bar = st.progress(0)
        status_ph = st.empty()
        log_ph = st.empty()
        steps = []

        def cb(d):
            pct = d["progress_pct"]
            bar.progress(pct/100)
            status_ph.markdown(f"**{d['step']}**")
            steps.append(f"`{pct}%` {d['step']}")
            log_ph.markdown("\n\n".join(steps[-6:]))

        with st.spinner(T("Running 6 agents...","Запуск 6 агентов...")):
            result = run_analysis(progress_callback=cb, coagulogram=coag.strip() or None)

        st.session_state.run_result = result
        ag = result["agents_succeeded"]
        cols = st.columns(4)
        for col, (name, ok) in zip(cols, ag.items()):
            col.markdown(f'<span class="agent-badge {"ok" if ok else "err"}">{"✅" if ok else "❌"} {name}</span>',
                        unsafe_allow_html=True)

        if all(ag.values()):
            st.success(T(f"✅ All agents complete in {result['duration_seconds']}s — switch to Findings tab",
                         f"✅ Все агенты завершены за {result['duration_seconds']}с — перейдите в Заключения"))
        else:
            failed = [k for k,v in ag.items() if not v]
            st.warning(f"⚠️ {T('Partial','Частично')} — failed: {', '.join(failed)}")
            for fn in failed:
                raw = result.get(fn, {})
                if isinstance(raw, dict) and "error" in raw:
                    st.error(f"🔍 {fn}: {raw['error'][:250]}")
                    break

# ━━ TAB 4 — FINDINGS (CDS) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab4:
    res = _get_results()
    cds = res["cds"]

    if not cds or "error" in cds:
        st.info(T("Click ▶ Run Analysis to load clinical findings.",
                  "Нажмите ▶ Анализ для загрузки клинических заключений."))
    else:
        st.subheader(T("Clinical Decision Support","Клиническая поддержка решений"))
        ac = cds.get("anticoagulation", {})
        status_icon = {"BLOCKED":"🔴","RECOMMENDED":"🟢","CONDITIONAL":"🟡"}.get(str(ac.get("status","")).upper(),"⚪")
        st.markdown(f"### {status_icon} {T('Anticoagulation','Антикоагуляция')} — {ac.get('status','—')}")
        a1,a2 = st.columns(2)
        with a1:
            rec = ac.get("recommendation_ru" if RU else "recommendation_en") or ac.get("recommendation","—")
            st.markdown(f"**{T('Recommendation','Рекомендация')}:** {rec}")
            if ac.get("blocker"):
                st.error(f"🔒 {T('Blocker','Блокирующий фактор')}: {ac['blocker']}")
        with a2:
            cav = ac.get("age83_caveat_ru" if RU else "age83_caveat_en") or "—"
            st.markdown(f"**{T('Citation','Источник')}:** {ac.get('citation','—')}")
            st.caption(f"⚠️ Age 83: {cav}")

        st.divider()
        col_a,col_b = st.columns(2)
        with col_a:
            bp = cds.get("bp_management", {})
            st.markdown(f"### 💊 {T('BP Management','Контроль АД')}")
            rec_bp = bp.get("recommendation_ru" if RU else "recommendation_en") or bp.get("recommendation","—")
            st.markdown(f"**{T('Target','Цель')}:** {bp.get('target_mmhg','—')}\n\n{rec_bp}")
            st.caption(bp.get('citation',''))

            inf = cds.get("infection_management", {})
            st.markdown(f"\n### 🦠 {T('Infection & CRP','Инфекция и СРБ')}")
            uti = inf.get("uti_treatment_ru" if RU else "uti_treatment_en") or inf.get("uti_treatment","—")
            st.markdown(f"**UTI:** {uti}\n\n**{T('CRP schedule','График СРБ')}:** {inf.get('serial_crp_schedule','—')}")
        with col_b:
            reh = cds.get("rehabilitation", {})
            st.markdown(f"### 🏃 {T('Rehabilitation','Реабилитация')}")
            caut = reh.get("key_caution_ru" if RU else "key_caution_en") or reh.get("key_caution","—")
            st.markdown(f"**{T('Frequency','Частота')}:** {reh.get('frequency','—')} | **{T('Intensity','Интенсивность')}:** {reh.get('intensity','—')}\n\n⚠️ {caut}")

            nut = cds.get("nutrition", {})
            st.markdown(f"\n### 🍽️ {T('Nutrition','Питание')}")
            rec_nut = nut.get("recommendation_ru" if RU else "recommendation_en") or "—"
            st.markdown(f"**{T('Protein','Белок')}:** {nut.get('protein_target_g_per_kg','—')} g/kg/d — {rec_nut}")

        flags = cds.get("red_flags", [])
        if flags:
            st.subheader(T("🚨 Red Flags","🚨 Тревожные признаки"))
            for f in flags:
                sign = f.get("sign_ru" if RU else "sign_en") or f.get("sign","?")
                action = f.get("action_ru" if RU else "action_en") or f.get("action","?")
                st.error(f"**{sign}** → {action}")

        pending = cds.get("pending_investigations", [])
        if pending:
            st.subheader(T("📋 Pending","📋 Необходимые исследования"))
            import pandas as pd
            rows = [{T("Investigation","Исследование"): p.get("item_ru" if RU else "item_en",p.get("item","?")),
                     "Urgency": p.get("urgency","?"), "Reason": p.get("reason","?")} for p in pending]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

# ━━ TAB 5 — RECOVERY PLAN ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab5:
    res = _get_results()
    recovery = res["recovery"]

    if not recovery or "error" in recovery:
        st.subheader(T("Recovery & Longevity Roadmap","Маршрут восстановления и долголетия"))
        st.caption(T("Static baseline plan shown. Run Analysis for the AI-personalised version.",
                     "Показан базовый план. Запустите анализ для ИИ-персонализированной версии."))
        ra, rb, rc = st.tabs([T("⚡ Acute (W1)","⚡ Острый (Н1)"),
                              T("📈 Subacute (W2-12)","📈 Подострый (2-12н)"),
                              T("♾️ Chronic (3m+)","♾️ Хронический (3м+)")])
        with ra:
            st.markdown(T(
"""**Neuro:** Continue Cerebrolysin + Mexidol; daily NIHSS monitoring; aspiration precautions until GUSS swallowing screen done.
**Speech:** Begin bedside SLT — short Russian naming tasks, comprehension intact so use it as the anchor.
**Mobility:** Passive ROM right arm/leg 3×/day; sit-to-stand with 2 assists; DVT prophylaxis (already on enoxaparin→aspirin).
**Infection:** Complete ampicillin+sulbactam course; recheck CRP (was 22.95) and urine.
**Nursing:** 2-hourly repositioning, pressure-area care (foot amputation + reduced mobility).""",
"""**Неврология:** Продолжить Церебролизин + Мексидол; ежедневный контроль NIHSS; меры против аспирации до теста GUSS.
**Речь:** Начать логопедию у постели — короткие задания на называние по-русски; понимание сохранено — опора на него.
**Мобильность:** Пассивная разработка правой руки/ноги 3×/день; присаживание с 2 помощниками; профилактика ТГВ.
**Инфекция:** Завершить курс ампициллин+сульбактам; контроль СРБ (был 22,95) и мочи.
**Уход:** Поворот каждые 2 часа, профилактика пролежней (ампутация стопы + сниженная мобильность)."""))
        with rb:
            st.markdown(T(
"""**Speech therapy (trilingual):** 30-min sessions 5×/week. Anchor in Russian (native); reintroduce English; Swahili passively. Mirror + melodic intonation therapy for motor aphasia.
**Motor rehab:** Progress right arm passive→active-assisted→active; task-specific grasp; right leg gait retraining with frame.
**Cardiovascular:** Optimise AF rate control (bisoprolol); BP target <140/90 (valsartan+amlodipine); statin continued.
**Nutrition:** 1.2–1.5 g/kg/day protein for recovery; monitor renal (CKD G2); address low total protein (59.6 g/L).""",
"""**Логопедия (3 языка):** Сессии 30 мин 5×/нед. Опора на русский (родной); ввод английского; суахили пассивно. Зеркальная + мелодико-интонационная терапия.
**Моторная реаб.:** Правая рука пассивно→активно-ассистир.→активно; захват; правая нога — ходьба с опорой.
**Сердечно-сосуд.:** Контроль ЧСС при ФП (бисопролол); АД <140/90 (валсартан+амлодипин); статин.
**Питание:** Белок 1,2–1,5 г/кг/сут; контроль почек (ХБП G2); коррекция низкого белка (59,6 г/л)."""))
        with rc:
            st.markdown(T(
"""**Maintenance:** Lifelong AF anticoagulation decision (CHA₂DS₂-VASc 4 — high stroke risk); secondary prevention bundle.
**Secondary prevention:** Statin + BP control + smoking cessation (critical — heavy smoker); right-ICA plaque surveillance (35-40%).
**Longevity goals:** Regain independent transfers (Rankin 5→3 target); home-based CV-tracked exercise; quarterly neuro review.""",
"""**Поддержка:** Решение о пожизненной антикоагуляции при ФП (CHA₂DS₂-VASc 4 — высокий риск); вторичная профилактика.
**Вторичная профилактика:** Статин + контроль АД + отказ от курения (критично); наблюдение бляшки П-ВСА (35-40%).
**Цели долголетия:** Самостоятельные перемещения (Рэнкин 5→3); домашние упражнения с CV-трекингом; неврологический контроль ежеквартально."""))
    else:
        st.subheader(T("Recovery & Longevity Roadmap","Маршрут восстановления"))
        phases = recovery.get("phases", {})
        sub_a,sub_b,sub_c = st.tabs([
            T("⚡ Acute (W1)","⚡ Острый (Н1)"),
            T("📈 Subacute (W2-12)","📈 Подострый (2-12н)"),
            T("♾️ Chronic (3m+)","♾️ Хронический (3м+)"),
        ])
        with sub_a:
            acute = phases.get("acute_week1", {})
            for key in ["neuro","speech","mobility","infection","nursing"]:
                val = acute.get(f"{key}_ru" if RU else f"{key}_en") or acute.get(key,"")
                if val: st.markdown(f"**{key.title()}:** {val}")
        with sub_b:
            sub = phases.get("subacute_weeks2_to_12", {})
            speech = sub.get("speech_therapy", {})
            if speech:
                st.markdown(f"#### 🗣️ {T('Speech Therapy','Речевая терапия')}")
                s1,s2 = st.columns(2)
                with s1:
                    st.markdown(f"**{T('Method','Метод')}:** {speech.get('method_ru' if RU else 'method_en','—')}")
                    st.markdown(f"**{T('Frequency','Частота')}:** {speech.get('frequency','—')}")
                with s2:
                    st.markdown(f"**Swahili:** {speech.get('swahili_note_ru' if RU else 'swahili_note_en','—')}")
            for key in ["motor_rehab","cardiovascular","nutrition"]:
                val = sub.get(f"{key}_ru" if RU else f"{key}_en","")
                if val: st.markdown(f"**{key.replace('_',' ').title()}:** {val}")
        with sub_c:
            chron = phases.get("chronic_3months_plus", {})
            for key in ["maintenance","secondary_prevention","longevity_goals"]:
                val = chron.get(f"{key}_ru" if RU else f"{key}_en","")
                if val: st.markdown(f"**{key.replace('_',' ').title()}:** {val}")

        fam = recovery.get("family_guide", {})
        if fam:
            st.divider()
            st.subheader(T("👨‍👩‍👧 Family Guide","👨‍👩‍👧 Руководство для семьи"))
            f1,f2 = st.columns(2)
            with f1:
                for tip in fam.get("communication_tips_ru" if RU else "communication_tips_en", []):
                    st.markdown(f"- {tip}")
            with f2:
                for sign in fam.get("warning_signs_ru" if RU else "warning_signs_en", []):
                    st.markdown(f"- ⚠️ {sign}")

        actions = recovery.get("priority_actions", [])
        if actions:
            import pandas as pd
            st.subheader(T("🎯 Priority Actions","🎯 Приоритетные действия"))
            rows = [{T("#","№"): a.get("rank"),
                     T("Action","Действие"): a.get("action_ru" if RU else "action_en", "?"),
                     T("Timeline","Сроки"): a.get("timeline",""),
                     T("Owner","Ответственный"): a.get("owner","")} for a in actions]
            import pandas as pd
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

# ━━ TAB 6 — PHYSICAL REHAB (AGENT 5) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab6:
    res = _get_results()
    rehab = res["rehab"]

    st.subheader(T("💪 Physical Rehabilitation — Right Arm & Leg",
                   "💪 ЛФК — Правая рука и нога"))

    if not rehab or "error" in rehab:
        st.info(T("Click ▶ Run Analysis to generate the physiotherapy protocol.",
                  "Нажмите ▶ Анализ для получения программы ЛФК."))
        # Show static fallback
        st.markdown(T("""
**Current status (from clinical notes):**
- Right arm: paresis persists — makes fist, limited active movement
- Right leg: nearly recovered — active movements present
- NIHSS 12, Rankin 5, Rivermead 2

**Planned exercises:**
- Passive ROM for right shoulder/elbow/wrist (3× daily, 10 min)
- Active-assisted hand opening (every 2 hours)
- Leg raises from supine position
- Seated balance training (with physio support)
- Mirror therapy for arm (once daily)

*Run Analysis to get AI-generated full protocol with Russian translation.*
""", """
**Текущий статус (из клинических записей):**
- Правая рука: парез сохраняется — сжимает кулак, ограниченные активные движения
- Правая нога: практически восстановлена — активные движения есть
- NIHSS 12, Рэнкин 5, Ривермид 2

**Запланированные упражнения:**
- Пассивная разработка правого плеча/локтя/запястья (3× в день, 10 мин)
- Активно-ассистированное раскрытие кисти (каждые 2 часа)
- Подъёмы ног из положения лёжа
- Тренировка баланса сидя (с поддержкой физиотерапевта)
- Зеркальная терапия для руки (1 раз в день)

*Запустите анализ для получения полного протокола ЛФК.*
"""))
    else:
        arm = rehab.get("right_arm_protocol", {})
        leg = rehab.get("right_leg_protocol", {})

        a_tab, l_tab, sched_tab, fam_tab = st.tabs([
            T("🦾 Right Arm","🦾 Правая рука"),
            T("🦿 Right Leg","🦿 Правая нога"),
            T("📅 Schedule","📅 Расписание"),
            T("👨‍👩‍👧 Family","👨‍👩‍👧 Семья"),
        ])
        with a_tab:
            st.markdown(f"**{T('Goal','Цель')}:** {arm.get('goal_ru' if RU else 'goal_en','—')}")
            st.markdown(f"**{T('Status','Статус')}:** {arm.get('current_status_ru' if RU else 'current_status_en','—')}")
            exercises = arm.get("exercises", [])
            if exercises:
                import pandas as pd
                rows = [{T("Exercise","Упражнение"): e.get("name_ru" if RU else "name_en","?"),
                         T("Description","Описание"): e.get("description_ru" if RU else "description_en","?")[:80],
                         T("Frequency","Частота"): e.get("frequency","?"),
                         T("Level","Уровень"): e.get("level","?"),
                         T("Physio?","Физио?"): "✅" if e.get("requires_physio") else "🏠"} for e in exercises]
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        with l_tab:
            st.markdown(f"**{T('Goal','Цель')}:** {leg.get('goal_ru' if RU else 'goal_en','—')}")
            exercises = leg.get("exercises", [])
            if exercises:
                import pandas as pd
                rows = [{T("Exercise","Упражнение"): e.get("name_ru" if RU else "name_en","?"),
                         T("Description","Описание"): e.get("description_ru" if RU else "description_en","?")[:80],
                         T("Level","Уровень"): e.get("level","?")} for e in exercises]
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            st.markdown(f"**{T('Balance','Баланс')}:** {leg.get('balance_training_ru' if RU else 'balance_training_en','—')}")
        with sched_tab:
            sched = rehab.get("weekly_schedule", {})
            st.markdown(sched.get("routine_ru" if RU else "routine_en","—"))
        with fam_tab:
            fam_i = rehab.get("family_instructions", {})
            for tip in fam_i.get("ru" if RU else "en", []):
                st.markdown(f"- {tip}")
            centers = rehab.get("rehab_centers", {})
            if centers:
                st.subheader(T("🏥 Moscow Rehab Centers","🏥 Реабилитационные центры Москвы"))
                st.markdown(centers.get("moscow_options_ru" if RU else "moscow_options_en","—"))

# ━━ TAB 7 — COMPUTER VISION TRACKER (AGENT 6) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab7:
    res = _get_results()
    cv = res["cv"]
    from patient_sim.agents.vision_agent import get_design_spec
    spec = cv if cv else get_design_spec()

    st.subheader(T("📷 Computer Vision Movement Tracker — Agent 6",
                   "📷 Трекер движений (компьютерное зрение) — Агент 6"))
    st.info(T(f"Status: {spec.get('status','DESIGN_PHASE')} — {spec.get('description_en','')}",
              f"Статус: {spec.get('status','DESIGN_PHASE')} — {spec.get('description_ru','')}"))

    c1v,c2v = st.columns(2)
    with c1v:
        st.markdown(f"### {T('Architecture','Архитектура')}")
        arch = spec.get("architecture", {})
        st.markdown(f"**{T('Input','Вход')}:** {arch.get('input','—')}")
        st.markdown(f"**{T('Models','Модели')}:**")
        for m in arch.get("models", []):
            st.markdown(f"- {m}")
        st.markdown(f"**{T('Output','Выход')}:**")
        for o in arch.get("output", []):
            st.markdown(f"- {o}")

    with c2v:
        st.markdown(f"### {T('Tracked Exercises','Отслеживаемые упражнения')}")
        for ex in spec.get("tracked_exercises", []):
            st.markdown(f"- **{ex['name']}** → {ex['metric']}")
        st.markdown(f"\n### {T('Hardware Needed','Оборудование')}")
        for hw in spec.get("hardware_needed", []):
            st.markdown(f"- {hw}")

    st.markdown(f"### {T('Implementation Roadmap','Дорожная карта внедрения')}")
    import pandas as pd
    roadmap = spec.get("implementation_roadmap", [])
    if roadmap:
        rows = [{T("Phase","Фаза"): r["phase"], T("Weeks","Недели"): r["weeks"],
                 T("Task","Задача"): r.get("task_ru" if RU else "task_en","?")} for r in roadmap]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    di = spec.get("data_integration", {})
    st.markdown(f"### {T('Data Integration → Patient Model','Интеграция данных → Модель пациента')}")
    st.markdown(f"""
- **{T('Feeds into','Питает')}:** `{di.get('feeds_into','PatientModel.rehab_sessions[]')}`
- **{T('Updates','Обновляет')}:** {', '.join(di.get('updates', []))}
- **{T('Reporting','Отчётность')}:** {di.get('reporting','Auto session report')}
""")

    st.markdown(f"### {T('Simulation Model — Where it all leads','Симуляционная модель — куда всё ведёт')}")
    st.markdown(T("""
**End-to-end vision:**

```
Camera → Pose detection → ROM/reps data
     ↓
Patient Model update (daily sessions)
     ↓
NIHSS trajectory prediction
     ↓
Discharge readiness forecast
     ↓
Rehab centre recommendation
     ↓
Family progress dashboard
```

**Simulation goal:** Predict NIHSS at D30/D90 based on exercise compliance, medication adherence, and lab trends.
When NIHSS prediction reaches threshold → automated alert to neurology team for Stage 3 transition.
""", """
**Сквозной сценарий:**

```
Камера → Определение позы → данные ROM/повторений
     ↓
Обновление модели пациента (ежедневные сессии)
     ↓
Прогноз динамики NIHSS
     ↓
Прогноз готовности к выписке
     ↓
Рекомендация реабилитационного центра
     ↓
Дашборд прогресса для семьи
```

**Цель симуляции:** Прогноз NIHSS на 30/90 день на основе соблюдения упражнений, приёма лекарств и лабораторных трендов.
При достижении порогового значения NIHSS → автоматическое уведомление неврологической команде о переходе на этап 3.
"""))

    st.warning(T("🔒 Privacy: All video processed locally on device — no video stored or transmitted",
                 "🔒 Конфиденциальность: Всё видео обрабатывается локально — никакое видео не хранится и не передаётся"))

# ━━ TAB 8 — EXPORT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab8:
    res = _get_results()
    report_md = res["report"]

    st.subheader(T("Clinical Report — Ready to Export","Клинический отчёт — готов к экспорту"))

    b1,b2,b3 = st.columns(3)
    with b1:
        if report_md:
            st.download_button(T("⬇ Download Full Report (.md)","⬇ Скачать отчёт (.md)"),
                data=report_md.encode(), file_name="CureForge_OIT_ENRU.md", mime="text/markdown")
    with b2:
        patient_json = patient.model_dump_json(indent=2)
        st.download_button(T("⬇ Patient Model (.json)","⬇ Модель пациента (.json)"),
            data=patient_json.encode(), file_name="CureForge_OIT_PatientModel.json", mime="application/json")
    with b3:
        st.markdown(T("""**🔗 Brain Institutes**
- [Scientific Center of Neurology](https://nsi.ru) — Moscow
- [Burnasyan Medical Center](https://fmbcfmba.ru) — Moscow
- [Sklifosovsky Institute](https://sklif.mos.ru) — Stroke unit
- [FMBA Rehab Center](https://fmba.ru) — Post-stroke rehab""",
"""**🔗 Институты (неврология)**
- [НЦН РАН](https://nsi.ru) — Москва
- [ФМБЦ им. Бурназяна](https://fmbcfmba.ru)
- [Институт Склифосовского](https://sklif.mos.ru) — Инсультный центр
- [Реабилитация ФМБА](https://fmba.ru) — Пост-инсультная реаб."""))

    if report_md:
        st.divider()
        if "🇷🇺" in report_md and "🇬🇧" in report_md:
            parts = report_md.split("---")
            shown = parts[1].strip() if RU and len(parts)>1 else parts[0].strip()
        else:
            shown = report_md
        st.markdown(shown)
    else:
        st.info(T("Run Analysis to generate the full bilingual report.",
                  "Запустите анализ для создания полного двуязычного отчёта."))
