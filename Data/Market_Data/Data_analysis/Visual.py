from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from Services.app.config import load_storage_config, load_supabase_config
from Services.app.storage import DataStorage

st.subheader("📊 Visual Data Analysis")
storage = DataStorage(supabase_config=load_supabase_config(), local_root=Path('.'), storage_config=load_storage_config())

saved_files = storage.list_analysis_files()

if saved_files:
    selected_file = st.selectbox("Select Data File for Visualization:", saved_files)
    if selected_file:
        df = storage.get_analysis_data(selected_file)
        if df.empty:
            st.warning("File is empty.")
        else:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.sort_values("Date").reset_index(drop=True)
            df["Net_Qty"] = df["Buy_Qty"] - df["Sell_Qty"]
            df["Cum_Net_Qty"] = df["Net_Qty"].cumsum()

            c1, c2 = st.columns(2)
            c1.plotly_chart(px.line(df, x="Date", y="Net_Qty", markers=True, title="Daily Net Qty"), use_container_width=True)
            c2.plotly_chart(px.line(df, x="Date", y="Cum_Net_Qty", markers=True, title="Cumulative Net Qty"), use_container_width=True)
            st.plotly_chart(px.bar(df, x="Date", y=["Buy_Qty", "Sell_Qty"], barmode="group", title="Buy/Sell Qty by Date"), use_container_width=True)
            st.dataframe(df.tail(200), use_container_width=True)
else:
    st.info("No saved files found. Use Data Studio to save one first.")