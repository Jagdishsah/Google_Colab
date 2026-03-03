from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from Services.app.storage import DataStorage


@dataclass
class SignalResult:
    poc_price: float
    latest_close: float
    vpvr_signal: str
    fvg_signal: str
    wyckoff_signal: str


def _prepare_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    req = ["Date", "Open", "High", "Low", "Close", "Volume"]
    work = df.copy()
    for col in req:
        if col not in work.columns:
            work[col] = 0
    work["Date"] = pd.to_datetime(work["Date"], errors="coerce")
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0)
    work = work.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    return work


def _vpvr(df: pd.DataFrame, bins: int = 20) -> tuple[pd.DataFrame, float]:
    prices = df["Close"].fillna(0)
    vols = df["Volume"].fillna(0)
    edges = np.linspace(prices.min(), prices.max(), bins + 1)
    if np.isclose(edges[0], edges[-1]):
        edges[-1] = edges[-1] + 1
    categories = pd.cut(prices, bins=edges, include_lowest=True)
    grouped = (
        pd.DataFrame({"bin": categories, "Volume": vols})
        .groupby("bin", observed=False)["Volume"]
        .sum()
        .reset_index()
    )
    grouped["Price"] = grouped["bin"].apply(lambda x: float(x.mid) if pd.notnull(x) else 0.0)
    poc_idx = grouped["Volume"].idxmax()
    poc = float(grouped.loc[poc_idx, "Price"]) if len(grouped) else 0.0
    grouped["Color"] = np.where(grouped.index == poc_idx, "#FFD700", "#5DADE2")
    return grouped, poc


def _detect_fvg(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    bullish: list[dict] = []
    bearish: list[dict] = []
    if len(df) < 3:
        return bullish, bearish

    for i in range(2, len(df)):
        c1 = df.iloc[i - 2]
        c3 = df.iloc[i]
        if float(c3["Low"]) > float(c1["High"]):
            bullish.append(
                {
                    "x0": c1["Date"],
                    "x1": c3["Date"],
                    "y0": float(c1["High"]),
                    "y1": float(c3["Low"]),
                }
            )
        if float(c3["High"]) < float(c1["Low"]):
            bearish.append(
                {
                    "x0": c1["Date"],
                    "x1": c3["Date"],
                    "y0": float(c3["High"]),
                    "y1": float(c1["Low"]),
                }
            )
    return bullish, bearish


def _signal_engine(df: pd.DataFrame, poc: float, bull_fvg: list[dict], bear_fvg: list[dict]) -> SignalResult:
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    close = float(latest["Close"])
    prev_close = float(prev["Close"])
    open_ = float(latest["Open"])

    if poc > 0 and abs(close - poc) / poc <= 0.02 and close > prev_close:
        vpvr = "🟢 BUY: Price at/near POC support with bounce"
    elif poc > 0 and close < poc * 0.97:
        vpvr = "🔴 SELL: Price broke >3% below POC"
    else:
        vpvr = "🟡 NEUTRAL: No POC trigger"

    bull_hit = any(f["y0"] <= close <= f["y1"] for f in bull_fvg)
    bear_hit = any(f["y0"] <= close <= f["y1"] for f in bear_fvg)
    green_candle = close > open_
    red_candle = close < open_

    if bull_hit and green_candle:
        fvg_signal = "🟢 BUY: Price reacted inside Bullish FVG"
    elif bear_hit and red_candle:
        fvg_signal = "🔴 DUMP: Price rejected inside Bearish FVG"
    else:
        fvg_signal = "🟡 NEUTRAL: No FVG trigger"

    work = df.copy()
    work["SMA200"] = work["Close"].rolling(200).mean()
    work["STD20"] = work["Close"].rolling(20).std()
    std_series = work["STD20"].dropna()
    std_thresh = float(std_series.quantile(0.10)) if not std_series.empty else 0.0
    curr_std = float(work["STD20"].iloc[-1]) if not work["STD20"].isna().all() else 0.0
    sma200 = float(work["SMA200"].iloc[-1]) if not work["SMA200"].isna().all() else 0.0
    near_sma = sma200 > 0 and abs(close - sma200) / sma200 <= 0.05

    if curr_std > 0 and curr_std <= std_thresh and near_sma:
        wyckoff = "🟢 STRONG BUY: Wyckoff Spring Alert — accumulation detected"
    else:
        wyckoff = "🔴 WAIT: Accumulation phase not fully confirmed"

    return SignalResult(
        poc_price=poc,
        latest_close=close,
        vpvr_signal=vpvr,
        fvg_signal=fvg_signal,
        wyckoff_signal=wyckoff,
    )


def _build_chart(df: pd.DataFrame, vpvr_df: pd.DataFrame, poc: float, bull_fvg: list[dict], bear_fvg: list[dict]) -> go.Figure:
    work = df.copy()
    work["SMA200"] = work["Close"].rolling(200).mean()

    fig = make_subplots(
        rows=1,
        cols=2,
        shared_yaxes=True,
        column_widths=[0.78, 0.22],
        horizontal_spacing=0.02,
        specs=[[{"type": "xy"}, {"type": "xy"}]],
    )

    fig.add_trace(
        go.Candlestick(
            x=work["Date"],
            open=work["Open"],
            high=work["High"],
            low=work["Low"],
            close=work["Close"],
            name="Price",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(x=work["Date"], y=work["SMA200"], mode="lines", name="SMA200", line=dict(color="#f39c12", width=2)),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Bar(
            x=vpvr_df["Volume"],
            y=vpvr_df["Price"],
            orientation="h",
            marker_color=vpvr_df["Color"],
            name="VPVR",
            showlegend=True,
        ),
        row=1,
        col=2,
    )

    if poc > 0:
        fig.add_hline(y=poc, line_dash="dot", line_color="#FFD700", annotation_text="POC", row=1, col=1)

    max_date = work["Date"].max() + timedelta(days=30)
    for zone in bull_fvg:
        fig.add_shape(
            type="rect",
            x0=zone["x0"],
            x1=max_date,
            y0=zone["y0"],
            y1=zone["y1"],
            xref="x",
            yref="y",
            fillcolor="rgba(46, 204, 113, 0.2)",
            line=dict(color="rgba(46, 204, 113, 0.4)", width=1),
        )

    for zone in bear_fvg:
        fig.add_shape(
            type="rect",
            x0=zone["x0"],
            x1=max_date,
            y0=zone["y0"],
            y1=zone["y1"],
            xref="x",
            yref="y",
            fillcolor="rgba(231, 76, 60, 0.2)",
            line=dict(color="rgba(231, 76, 60, 0.4)", width=1),
        )

    fig.update_layout(height=700, title="Automated Quantitative Scanner", xaxis_rangeslider_visible=False)
    fig.update_xaxes(title_text="Date", row=1, col=1)
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_xaxes(title_text="Volume Profile", row=1, col=2)
    return fig


def render_market_predictor_tab(storage: DataStorage) -> None:
    st.subheader("🔮 Market Predictor — VPVR + FVG + Wyckoff")
    stock_files = storage.list_stock_data_files()
    if not stock_files:
        st.warning("No stock CSV files found in Data/Market_Data/Stock_Data/")
        return

    selected = st.selectbox("Select Stock Dataset", stock_files, key="market_predictor_stock")

    try:
        raw = storage.get_stock_data(selected)
        df = _prepare_ohlcv(raw)
        if len(df) < 30:
            st.warning("Need at least 30 rows of OHLCV data.")
            return

        vpvr_df, poc = _vpvr(df, bins=20)
        bull_fvg, bear_fvg = _detect_fvg(df)
        result = _signal_engine(df, poc, bull_fvg, bear_fvg)

        c1, c2, c3 = st.columns(3)
        c1.metric("Current Price", f"Rs {result.latest_close:,.2f}")
        c2.metric("POC Level", f"Rs {result.poc_price:,.2f}")
        active = " | ".join([result.vpvr_signal, result.fvg_signal, result.wyckoff_signal])
        c3.metric("Active Signals", "3 Models Ready")

        st.info(active)

        fig = _build_chart(df, vpvr_df, poc, bull_fvg, bear_fvg)
        st.plotly_chart(fig, width="stretch")

        with st.expander("📋 Signal Breakdown"):
            st.write("- VPVR:", result.vpvr_signal)
            st.write("- FVG:", result.fvg_signal)
            st.write("- Wyckoff:", result.wyckoff_signal)
            st.write(f"Detected Bullish FVG zones: {len(bull_fvg)}")
            st.write(f"Detected Bearish FVG zones: {len(bear_fvg)}")

    except Exception as e:
        st.error(f"Market predictor failed: {e}")