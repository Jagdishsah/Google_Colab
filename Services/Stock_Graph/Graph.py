from pathlib import Path
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from Services.app.config import load_storage_config, load_supabase_config
from Services.app.storage import DataStorage

st.markdown("### 📈 Pro Interactive Stock Chart")
storage = DataStorage(supabase_config=load_supabase_config(), local_root=Path('.'), storage_config=load_storage_config())

with st.expander("📁 Data Management (Upload & Save)", expanded=False):
    uploaded_file = st.file_uploader("Upload OHLCV Data (TXT/JSON)", type=["txt", "json"])

    if uploaded_file is not None:
        try:
            raw_data = json.load(uploaded_file)
            if raw_data.get("s") == "ok" and "t" in raw_data:
                up_df = pd.DataFrame({
                    "Date": pd.to_datetime(raw_data["t"], unit="s"),
                    "Open": raw_data["o"],
                    "High": raw_data["h"],
                    "Low": raw_data["l"],
                    "Close": raw_data["c"],
                    "Volume": raw_data["v"],
                })
                st.success(f"✅ Loaded {len(up_df)} rows from file.")

                c1, c2 = st.columns([3, 1])
                stock_symbol = c1.text_input("Stock Symbol to Save/Merge (e.g., NABIL):").upper().strip()
                if c2.button("💾 Save to Supabase", use_container_width=True):
                    if stock_symbol:
                        existing_df = storage.get_stock_data(stock_symbol)
                        if not existing_df.empty:
                            existing_df["Date"] = pd.to_datetime(existing_df["Date"], errors="coerce")
                        combined_df = pd.concat([existing_df, up_df], ignore_index=True).drop_duplicates(subset=["Date"], keep="last").sort_values("Date")
                        storage.save_stock_data(stock_symbol, combined_df)
                        st.success(f"🎉 Merged and saved `{stock_symbol}.csv`!")
                    else:
                        st.error("Please enter a stock symbol.")
            else:
                st.error("Invalid TradingView JSON format.")
        except Exception as e:
            st.error(f"Error parsing file: {e}")

st.write("---")
saved_stocks = [f.replace(".csv", "") for f in storage.list_stock_data_files()]

c_load, c_ind1, c_ind2 = st.columns([2, 1, 1])
selected_stock = c_load.selectbox("Select Stock to Chart:", ["-- Select --"] + saved_stocks)
show_sma = c_ind1.checkbox("Show Moving Averages", value=True)
show_rsi = c_ind2.checkbox("Show RSI (14)", value=True)

if selected_stock != "-- Select --":
    df = storage.get_stock_data(selected_stock)
    if df.empty:
        st.warning("No data for selected stock.")
    else:
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date").reset_index(drop=True)

        df["SMA_20"] = df["Close"].rolling(window=20).mean()
        df["SMA_50"] = df["Close"].rolling(window=50).mean()
        df["Vol_SMA_30"] = df["Volume"].rolling(window=30).mean()
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df["RSI_14"] = 100 - (100 / (1 + rs))

        rows = 3 if show_rsi else 2
        row_heights = [0.6, 0.2, 0.2] if show_rsi else [0.7, 0.3]
        fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=row_heights)

        fig.add_trace(go.Candlestick(x=df["Date"], open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Price"), row=1, col=1)
        if show_sma:
            fig.add_trace(go.Scatter(x=df["Date"], y=df["SMA_20"], name="SMA 20"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df["Date"], y=df["SMA_50"], name="SMA 50"), row=1, col=1)

        colors = ["#26a69a" if row["Close"] >= row["Open"] else "#ef5350" for _, row in df.iterrows()]
        fig.add_trace(go.Bar(x=df["Date"], y=df["Volume"], marker_color=colors, name="Volume", opacity=0.8), row=2, col=1)
        fig.add_trace(go.Scatter(x=df["Date"], y=df["Vol_SMA_30"], name="Vol SMA 30"), row=2, col=1)

        if show_rsi:
            fig.add_trace(go.Scatter(x=df["Date"], y=df["RSI_14"], name="RSI 14"), row=3, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)
            fig.update_yaxes(range=[0, 100], row=3, col=1)

        dt_breaks = pd.date_range(start=df["Date"].min(), end=df["Date"].max()).difference(df["Date"])
        fig.update_xaxes(rangebreaks=[dict(values=dt_breaks)], rangeslider_visible=False)
        fig.update_layout(height=800 if show_rsi else 650, template="plotly_dark", hovermode="x unified", margin=dict(l=10, r=10, t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)