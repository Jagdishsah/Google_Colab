from pathlib import Path
import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from Services.app.config import load_storage_config, load_supabase_config
from Services.app.storage import DataStorage

st.markdown("### 🌊 Institutional Elliott Wave Engine")
st.caption("Advanced EW analysis with replay mode.")
storage = DataStorage(supabase_config=load_supabase_config(), local_root=Path('.'), storage_config=load_storage_config())


def run_ew_analysis(df_full, replay_date, sensitivity, wave_type):
    df = df_full[df_full["Date"].dt.date <= replay_date].copy().reset_index(drop=True)
    future_df = df_full[df_full["Date"].dt.date > replay_date].copy()
    if len(df) < 50:
        st.error("Not enough data to analyze. Need at least 50 days.")
        return

    swings_high = df["High"].rolling(sensitivity, min_periods=1).max()
    swings_low = df["Low"].rolling(sensitivity, min_periods=1).min()

    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df["Date"], open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Price", opacity=0.8))
    fig.add_trace(go.Scatter(x=df["Date"], y=swings_high, name="Swing High", line=dict(color="#2ecc71")))
    fig.add_trace(go.Scatter(x=df["Date"], y=swings_low, name="Swing Low", line=dict(color="#e74c3c")))

    if not future_df.empty:
        fig.add_trace(go.Candlestick(x=future_df["Date"], open=future_df["Open"], high=future_df["High"], low=future_df["Low"], close=future_df["Close"], increasing_line_color='rgba(128,128,128,0.3)', decreasing_line_color='rgba(128,128,128,0.3)', name='Future (Replay)'))

    fig.update_layout(height=650, template="plotly_dark", title=f"{wave_type} Structure")
    st.plotly_chart(fig, use_container_width=True)


saved_stocks = [f.replace(".csv", "") for f in storage.list_stock_data_files()]
if not saved_stocks:
    st.info("No stock files available.")
else:
    c_stock, c_sens, c_mode = st.columns([2, 1, 1])
    selected_stock = c_stock.selectbox("Select Stock:", saved_stocks)
    sensitivity = c_sens.number_input("Degree (Sensitivity)", 2, 20, 4)
    wave_type = c_mode.selectbox("Scan Mode:", ["Auto-Predict (Last 6 Months)", "Motive (1-2-3-4-5)", "Correction (A-B-C)"])

    df_master = storage.get_stock_data(selected_stock)
    if not df_master.empty:
        df_master["Date"] = pd.to_datetime(df_master["Date"])
        df_master = df_master[(df_master["High"] >= df_master["Low"]) & (df_master["High"] >= df_master["Close"])].sort_values("Date").reset_index(drop=True)

        if wave_type == "Auto-Predict (Last 6 Months)":
            df_master = df_master[df_master["Date"] >= df_master["Date"].max() - pd.DateOffset(months=6)].reset_index(drop=True)

        tab_live, tab_replay = st.tabs(["🔴 Live Market Scanner", "⏪ Replay & Backtester Mode"])
        with tab_live:
            run_ew_analysis(df_master, df_master["Date"].max().date(), sensitivity, wave_type)

        with tab_replay:
            min_d = df_master["Date"].min().date()
            max_d = df_master["Date"].max().date()
            default_date = max(min_d, max_d - datetime.timedelta(days=30))
            replay_date = st.slider("Select Replay Date:", min_value=min_d, max_value=max_d, value=default_date, step=datetime.timedelta(days=1), format="YYYY-MM-DD")
            run_ew_analysis(df_master, replay_date, sensitivity, wave_type)