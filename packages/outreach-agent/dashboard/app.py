"""
Streamlit dashboard — Investor Outreach Status Board.

Privacy: email addresses are NEVER shown in the UI.

Run with:
    streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.database import OutreachRecord, SessionLocal, init_db

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LongevityInTime — Investor Outreach",
    page_icon="🧬",
    layout="wide",
)

init_db()

STATUS_COLORS = {
    "pending":        "#808080",
    "interested":     "#22c55e",
    "not_interested": "#ef4444",
    "needs_info":     "#f59e0b",
    "other":          "#6366f1",
}

PIPELINE_COLORS = {
    "queued":   "#64748b",
    "sent":     "#3b82f6",
    "replied":  "#8b5cf6",
    "closed":   "#22c55e",
}


@st.cache_data(ttl=30)
def load_records() -> pd.DataFrame:
    db = SessionLocal()
    try:
        rows = db.query(OutreachRecord).all()
        data = [
            {
                "Firm":           r.firm or r.name or "—",
                "Focus Area":     r.focus_area or "—",
                "Pipeline":       r.pipeline_status or "queued",
                "Reply":          r.reply_status.value if r.reply_status else "pending",
                "Follow-up #":    r.follow_up_stage or 0,
                "Sent At":        r.sent_at,
                "Next Follow-up": r.next_follow_up_at,
                "Reply Received": r.reply_received_at,
                # internal only — not shown in table
                "_id": r.id,
            }
            for r in rows
        ]
        return pd.DataFrame(data)
    finally:
        db.close()


# ── Header ────────────────────────────────────────────────────────────────────
st.title("🧬 LongevityInTime — Investor Outreach")
st.caption("Live campaign tracker · contact details are private")

col_refresh, col_sync = st.columns([1, 6])
with col_refresh:
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()

df = load_records()

# ── Top-level Metrics ────────────────────────────────────────────────────────
if df.empty:
    st.info("No outreach records yet. Run `scripts/import_from_sheet.py` to import from Google Sheet.")
    st.stop()

total       = len(df)
sent        = int((df["Pipeline"] == "sent").sum() + (df["Sent At"].notna()).sum())
sent        = min(sent, total)  # cap
replied     = int(df["Reply Received"].notna().sum())
interested  = int((df["Reply"] == "interested").sum())
followups   = int((df["Follow-up #"] > 0).sum())

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Tracked",   total)
c2.metric("Emails Sent",     sent)
c3.metric("Replies",         replied, f"{replied/sent*100:.0f}%" if sent else "—")
c4.metric("Interested 🔥",   interested)
c5.metric("Follow-ups Sent", followups)

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📋 Pipeline", "📊 Stats", "🔗 Google Sheet Sync"])

with tab1:
    # Filters
    fc1, fc2, fc3 = st.columns(3)
    all_replies  = sorted(df["Reply"].unique().tolist())
    sel_replies  = fc1.multiselect("Reply status", all_replies, default=all_replies)
    all_pipe     = sorted(df["Pipeline"].unique().tolist())
    sel_pipe     = fc2.multiselect("Pipeline stage", all_pipe, default=all_pipe)
    search       = fc3.text_input("Search firm / focus area", "")

    filtered = df[df["Reply"].isin(sel_replies) & df["Pipeline"].isin(sel_pipe)]
    if search:
        mask = (
            filtered["Firm"].str.contains(search, case=False, na=False)
            | filtered["Focus Area"].str.contains(search, case=False, na=False)
        )
        filtered = filtered[mask]

    display_cols = [
        "Firm", "Focus Area", "Pipeline", "Reply",
        "Follow-up #", "Sent At", "Next Follow-up", "Reply Received",
    ]

    def _color_reply(val):
        return f"color: {STATUS_COLORS.get(val, '#ccc')}; font-weight: bold;"

    def _color_pipe(val):
        return f"color: {PIPELINE_COLORS.get(val, '#ccc')}; font-weight: 600;"

    def _fmt_dt(x):
        return x.strftime("%b %d %H:%M") if pd.notna(x) else "—"

    styled = (
        filtered[display_cols]
        .style
        .map(_color_reply, subset=["Reply"])
        .map(_color_pipe,  subset=["Pipeline"])
        .format({"Sent At": _fmt_dt, "Next Follow-up": _fmt_dt, "Reply Received": _fmt_dt})
    )
    st.subheader(f"{len(filtered)} contacts")
    st.dataframe(styled, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Reply breakdown")
    reply_counts = df["Reply"].value_counts().reset_index()
    reply_counts.columns = ["Status", "Count"]
    st.bar_chart(reply_counts.set_index("Status"))

    st.subheader("Pipeline breakdown")
    pipe_counts = df["Pipeline"].value_counts().reset_index()
    pipe_counts.columns = ["Stage", "Count"]
    st.bar_chart(pipe_counts.set_index("Stage"))

    st.subheader("Follow-up stages")
    fu_counts = df["Follow-up #"].value_counts().reset_index()
    fu_counts.columns = ["Follow-up Stage", "Count"]
    st.bar_chart(fu_counts.set_index("Follow-up Stage"))

with tab3:
    st.subheader("Google Sheet → Database Sync")
    st.info(
        "Sheet: **Лагун Е.С.** (investor outreach tracker)\n\n"
        "Sync imports contacts with email addresses and updates their pipeline status. "
        "Contact emails are stored in the database only — never displayed here."
    )

    import subprocess, sys as _sys
    if st.button("▶ Run sync now"):
        with st.spinner("Syncing from Google Sheet…"):
            result = subprocess.run(
                [_sys.executable, "scripts/import_from_sheet.py"],
                capture_output=True, text=True, cwd=str(Path(__file__).parent.parent)
            )
            if result.returncode == 0:
                st.success(result.stdout or "Sync complete.")
                st.cache_data.clear()
            else:
                st.error(f"Sync failed:\n{result.stderr}")

    st.divider()
    st.caption(
        "To enable two-way sync (write status back to sheet), place your Google service account "
        "JSON at `secrets/gcp_service_account.json` and share the sheet with "
        "`aminisouissi@airy-timing-497013-r3.iam.gserviceaccount.com`."
    )
