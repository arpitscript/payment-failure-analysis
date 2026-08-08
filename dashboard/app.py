"""
Streamlit dashboard for the payment failure analysis.

Reads the CSVs in ../data (the same files loaded into Postgres) so it runs
anywhere without a live DB connection - handy for deploying to Streamlit Cloud.

Run:  streamlit run dashboard/app.py
"""

import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
ACCENT = "#2f5d8a"
DANGER = "#c0392b"

st.set_page_config(page_title="Payment Failure Analysis", layout="wide")


@st.cache_data
def load_data():
    txn = pd.read_csv(os.path.join(DATA_DIR, "transactions.csv"),
                      parse_dates=["txn_time"])
    banks = pd.read_csv(os.path.join(DATA_DIR, "banks.csv"))
    modes = pd.read_csv(os.path.join(DATA_DIR, "payment_modes.csv"))
    devices = pd.read_csv(os.path.join(DATA_DIR, "devices.csv"))
    reasons = pd.read_csv(os.path.join(DATA_DIR, "failure_reasons.csv"))

    df = (txn
          .merge(banks, on="bank_id")
          .merge(modes, on="mode_id")
          .merge(devices, on="device_id")
          .merge(reasons, on="reason_id", how="left"))
    df["device"] = df["device_type"] + " " + df["os_version"].astype(str)
    df["hour"] = df["txn_time"].dt.hour
    df["weekday"] = df["txn_time"].dt.day_name().str[:3]
    df["month"] = df["txn_time"].dt.to_period("M").dt.to_timestamp()
    df["is_failed"] = df["status"].eq("FAILED")
    return df


def inr(x):
    """Format rupees the way people actually read them here."""
    if x >= 1e7:
        return f"₹{x / 1e7:.2f} Cr"
    if x >= 1e5:
        return f"₹{x / 1e5:.2f} L"
    return f"₹{x:,.0f}"


def fail_rate(frame, by):
    g = frame.groupby(by).agg(
        total=("txn_id", "count"),
        failed=("is_failed", "sum"),
    ).reset_index()
    g["failure_rate"] = (g["failed"] / g["total"] * 100).round(2)
    return g


df = load_data()

# ---- sidebar filters --------------------------------------------------------
st.sidebar.header("Filters")
bank_opts = sorted(df["bank_name"].unique())
mode_opts = sorted(df["mode_name"].unique())
sel_banks = st.sidebar.multiselect("Bank", bank_opts, default=bank_opts)
sel_modes = st.sidebar.multiselect("Payment mode", mode_opts, default=mode_opts)
st.sidebar.caption(
    "Synthetic data — failure patterns are injected for analysis practice and "
    "do not reflect any real institution."
)

view = df[df["bank_name"].isin(sel_banks) & df["mode_name"].isin(sel_modes)]
if view.empty:
    st.warning("No transactions match the current filters.")
    st.stop()

# ---- header + KPIs ----------------------------------------------------------
st.title("Payment Success & Failure-Rate Analysis")
st.caption("Where are online payments failing, and how much revenue does it cost?")

total = len(view)
failed = int(view["is_failed"].sum())
success_rate = (1 - failed / total) * 100
revenue_lost = view.loc[view["is_failed"], "amount"].sum()
worst = fail_rate(view, "bank_name").sort_values("failure_rate", ascending=False).iloc[0]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total transactions", f"{total:,}")
c2.metric("Success rate", f"{success_rate:.1f}%")
c3.metric("Revenue lost (failed)", inr(revenue_lost))
c4.metric("Worst bank", worst["bank_name"], f"{worst['failure_rate']:.1f}% fail")

st.divider()

# ---- failure rate by bank ---------------------------------------------------
left, right = st.columns(2)

with left:
    st.subheader("Failure rate by bank")
    g = fail_rate(view, "bank_name").sort_values("failure_rate")
    colors = [DANGER if v == g["failure_rate"].max() else ACCENT
              for v in g["failure_rate"]]
    fig = go.Figure(go.Bar(
        x=g["failure_rate"], y=g["bank_name"], orientation="h",
        marker_color=colors,
        text=g["failure_rate"].map(lambda v: f"{v:.1f}%"), textposition="outside",
    ))
    fig.update_layout(xaxis_title="Failure rate (%)", yaxis_title="",
                      height=420, margin=dict(l=0, r=20, t=10, b=0))
    st.plotly_chart(fig, width='stretch')

with right:
    st.subheader("Failure rate by payment mode")
    g = fail_rate(view, "mode_name").sort_values("failure_rate")
    fig = px.bar(g, x="failure_rate", y="mode_name", orientation="h",
                 text=g["failure_rate"].map(lambda v: f"{v:.1f}%"))
    fig.update_traces(marker_color=ACCENT, textposition="outside")
    fig.update_layout(xaxis_title="Failure rate (%)", yaxis_title="",
                      height=420, margin=dict(l=0, r=20, t=10, b=0))
    st.plotly_chart(fig, width='stretch')

# ---- device + hour ----------------------------------------------------------
left, right = st.columns(2)

with left:
    st.subheader("Failure rate by device")
    g = fail_rate(view, "device").sort_values("failure_rate")
    colors = [DANGER if v == g["failure_rate"].max() else ACCENT
              for v in g["failure_rate"]]
    fig = go.Figure(go.Bar(
        x=g["failure_rate"], y=g["device"], orientation="h", marker_color=colors,
        text=g["failure_rate"].map(lambda v: f"{v:.1f}%"), textposition="outside",
    ))
    fig.update_layout(xaxis_title="Failure rate (%)", yaxis_title="",
                      height=420, margin=dict(l=0, r=20, t=10, b=0))
    st.plotly_chart(fig, width='stretch')

with right:
    st.subheader("Failure rate by hour of day")
    g = fail_rate(view, "hour")
    fig = px.line(g, x="hour", y="failure_rate", markers=True)
    fig.update_traces(line_color=ACCENT)
    fig.add_vrect(x0=-0.5, x1=2.5, fillcolor=DANGER, opacity=0.12, line_width=0,
                  annotation_text="12-3am", annotation_position="top left")
    fig.update_layout(xaxis_title="Hour of day", yaxis_title="Failure rate (%)",
                      height=420, margin=dict(l=0, r=20, t=10, b=0),
                      xaxis=dict(dtick=2))
    st.plotly_chart(fig, width='stretch')

# ---- heatmap ----------------------------------------------------------------
st.subheader("Failure rate heatmap — hour vs weekday")
order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
pivot = (view.groupby(["weekday", "hour"])["is_failed"].mean()
         .mul(100).round(1).reset_index()
         .pivot(index="weekday", columns="hour", values="is_failed")
         .reindex(order))
fig = px.imshow(pivot, color_continuous_scale="Reds", aspect="auto",
                labels=dict(x="Hour of day", y="", color="Fail %"))
fig.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0))
st.plotly_chart(fig, width='stretch')

# ---- monthly trend + reasons ------------------------------------------------
left, right = st.columns(2)

with left:
    st.subheader("Monthly failure-rate trend")
    g = fail_rate(view, "month")
    fig = px.line(g, x="month", y="failure_rate", markers=True)
    fig.update_traces(line_color=ACCENT)
    fig.update_layout(xaxis_title="", yaxis_title="Failure rate (%)",
                      height=380, margin=dict(l=0, r=20, t=10, b=0))
    st.plotly_chart(fig, width='stretch')

with right:
    st.subheader("What's causing the failures")
    g = (view[view["is_failed"]].groupby("reason_text")["txn_id"].count()
         .reset_index(name="count").sort_values("count"))
    fig = px.bar(g, x="count", y="reason_text", orientation="h")
    fig.update_traces(marker_color=ACCENT)
    fig.update_layout(xaxis_title="Failed transactions", yaxis_title="",
                      height=380, margin=dict(l=0, r=20, t=10, b=0))
    st.plotly_chart(fig, width='stretch')

# ---- the pocket worth calling out -------------------------------------------
pocket = view[(view["bank_name"] == "IndusInd Bank") &
              (view["device_type"] == "Android") &
              (view["hour"].isin([0, 1, 2]))]
if len(pocket) > 0:
    rate = pocket["is_failed"].mean() * 100
    lost = pocket.loc[pocket["is_failed"], "amount"].sum()
    st.error(
        f"**Worst pocket:** IndusInd Bank on Android between 12-3am fails "
        f"**{rate:.0f}%** of the time ({len(pocket):,} txns, {inr(lost)} lost) — "
        f"vs ~9% across the rest of the platform."
    )
