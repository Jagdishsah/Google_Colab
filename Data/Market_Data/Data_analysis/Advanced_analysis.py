from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from Services.app.config import load_storage_config, load_supabase_config
from Services.app.storage import DataStorage

st.subheader("🚀 Advanced Quantitative Analysis")
storage = DataStorage(supabase_config=load_supabase_config(), local_root=Path('.'), storage_config=load_storage_config())

saved_files = storage.list_analysis_files()

if saved_files:
    selected_file = st.selectbox("Select Broker Data to Analyze:", saved_files, key="advanced_broker_source")
    if selected_file:
        raw_df = storage.get_analysis_data(selected_file)
        raw_df["Date"] = pd.to_datetime(raw_df["Date"])

        min_date, max_date = raw_df["Date"].min().date(), raw_df["Date"].max().date()
        date_range = st.date_input("🗓️ Select Range (Calculations adjust to range)", value=(min_date, max_date), min_value=min_date, max_value=max_date, key="advanced_date_range")

        if len(date_range) == 2:
            mask = (raw_df["Date"].dt.date >= date_range[0]) & (raw_df["Date"].dt.date <= date_range[1])
            df = raw_df.loc[mask].copy().reset_index(drop=True)

            if not df.empty:
                df["Net_Qty"] = df["Buy_Qty"] - df["Sell_Qty"]
                df["Cum_Net_Qty"] = df["Net_Qty"].cumsum()
                df["Total_Vol"] = df["Buy_Qty"] + df["Sell_Qty"]
                df["Daily_VWAP"] = np.where(df["Total_Vol"] > 0, (df["Buy_Amount"] + df["Sell_Amount"]) / df["Total_Vol"], 0)

                total_buy_qty = df["Buy_Qty"].sum()
                total_buy_amt = df["Buy_Amount"].sum()
                total_sell_qty = df["Sell_Qty"].sum()
                total_sell_amt = df["Sell_Amount"].sum()
                current_inventory = df["Cum_Net_Qty"].iloc[-1]

                buy_wacc = (total_buy_amt / total_buy_qty) if total_buy_qty > 0 else 0
                sell_wacc = (total_sell_amt / total_sell_qty) if total_sell_qty > 0 else 0
                realized_pl = total_sell_qty * (sell_wacc - buy_wacc)
                net_capital_flow = total_buy_amt - total_sell_amt
                break_even = (net_capital_flow / current_inventory) if current_inventory > 0 else 0

                m1, m2, m3 = st.columns(3)
                m1.metric("Average Buy WACC", f"Rs {buy_wacc:,.2f}")
                m2.metric("Average Sell WACC", f"Rs {sell_wacc:,.2f}")
                m3.metric("Inventory Left", f"{current_inventory:,.0f} Units")
                m4, m5 = st.columns(2)
                m4.metric("Realized P/L", f"Rs {realized_pl:,.2f}", delta="Profit" if realized_pl > 0 else "Loss")
                m5.metric("Remaining Break-Even", f"Rs {break_even:,.2f}" if current_inventory > 0 else "N/A")

                df_heat = df.copy()
                nepse_days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"]
                df_heat["Day"] = pd.Categorical(df_heat["Date"].dt.day_name(), categories=nepse_days, ordered=True)
                df_heat["Month"] = df_heat["Date"].dt.strftime("%b %Y")
                heat_pivot = df_heat.groupby(["Month", "Day"], observed=False)["Net_Qty"].sum().unstack().fillna(0)
                fig_heat = px.imshow(heat_pivot, aspect="auto", color_continuous_scale="RdYlGn", title="Broker Activity Heatmap")
                st.plotly_chart(fig_heat, use_container_width=True)
else:
    st.info("No data files available yet. Upload and save from Data Studio first.")