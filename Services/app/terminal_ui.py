from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from Services.app.storage import DataStorage
from Services.app.services import drawdown_stats, medium_exposure, portfolio_var_95, recommended_position_size, sector_exposure
from Services.scrape import get_market_data


def _now_np() -> str:
    return (datetime.utcnow() + pd.Timedelta(hours=5, minutes=45)).strftime("%Y-%m-%d %H:%M:%S")


def _compute_integrated_metrics(ledger_df: pd.DataFrame, holdings_df: pd.DataFrame, cache_df: pd.DataFrame, history_df: pd.DataFrame) -> dict:
    data = holdings_df.copy()
    if data.empty:
        return {"invested": 0.0, "market": 0.0, "unrealized": 0.0, "realized": 0.0}

    cache_view = cache_df[["Symbol", "LTP"]] if (not cache_df.empty and "Symbol" in cache_df.columns and "LTP" in cache_df.columns) else pd.DataFrame(columns=["Symbol", "LTP"])
    data = pd.merge(data, cache_view, on="Symbol", how="left", suffixes=("", "_cache"))
    data["LTP"] = pd.to_numeric(data.get("LTP_cache", data.get("LTP", 0)), errors="coerce").fillna(pd.to_numeric(data.get("LTP", 0), errors="coerce").fillna(0))

    payables = ledger_df[ledger_df["Category"] == "PAYABLE"]["Amount"].sum() if not ledger_df.empty else 0.0
    receivables = ledger_df[ledger_df["Category"] == "RECEIVABLE"]["Amount"].sum() if not ledger_df.empty else 0.0
    invested = max(float(payables - receivables), 0.0)

    market = float((pd.to_numeric(data["Total_Qty"], errors="coerce").fillna(0) * pd.to_numeric(data["LTP"], errors="coerce").fillna(0)).sum())
    unrealized = market - invested
    realized = float(history_df["Net_PL"].sum()) if (not history_df.empty and "Net_PL" in history_df.columns) else 0.0
    return {"invested": invested, "market": market, "unrealized": unrealized, "realized": realized}


def _log_activity(storage: DataStorage, category: str, symbol: str, action: str, details: str, amount: float = 0.0) -> None:
    log_df = storage.get_terminal_data("activity_log")
    new_row = pd.DataFrame(
        [
            {
                "Timestamp": _now_np(),
                "Category": category,
                "Symbol": symbol,
                "Action": action,
                "Details": details,
                "Amount": amount,
            }
        ]
    )
    out_df = pd.concat([new_row, log_df], ignore_index=True)
    storage.save_terminal_data("activity_log", out_df)


def _sync_market_cache(storage: DataStorage, holdings_df: pd.DataFrame, watchlist_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    symbols = set(holdings_df["Symbol"].dropna().astype(str).str.upper().tolist())
    symbols.update(watchlist_df["Symbol"].dropna().astype(str).str.upper().tolist() if not watchlist_df.empty else [])
    symbols = {s for s in symbols if s}

    if not symbols:
        return storage.get_terminal_data("cache"), storage.get_terminal_data("price_log")

    market_data = get_market_data(sorted(symbols))
    now = _now_np()

    cache_rows = []
    price_entries = []
    for sym in sorted(symbols):
        info = market_data.get(sym, {"price": 0.0, "change": 0.0, "high": 0.0, "low": 0.0})
        cache_rows.append(
            {
                "Symbol": sym,
                "LTP": float(info.get("price", 0.0) or 0.0),
                "Change": float(info.get("change", 0.0) or 0.0),
                "High52": float(info.get("high", 0.0) or 0.0),
                "Low52": float(info.get("low", 0.0) or 0.0),
                "LastUpdated": now,
            }
        )
        price_entries.append({"Date": now, "Symbol": sym, "LTP": float(info.get("price", 0.0) or 0.0)})

    new_cache = pd.DataFrame(cache_rows)
    old_log = storage.get_terminal_data("price_log")
    out_log = pd.concat([old_log, pd.DataFrame(price_entries)], ignore_index=True)

    storage.save_terminal_data("cache", new_cache)
    storage.save_terminal_data("price_log", out_log)
    _log_activity(storage, "SYSTEM", "MARKET", "SYNC", f"Synced {len(symbols)} symbols from Merolagani", 0.0)
    return new_cache, out_log


def _render_tms_hub(storage: DataStorage) -> None:
    st.subheader("🧾 TMS Transaction Hub")
    trx_df = storage.get_terminal_data("tms_trx")
    t1, t2, t3, t4 = st.tabs(["Add", "View", "Manage", "Export"])

    with t1:
        with st.form("tms_trx_add"):
            c1, c2, c3, c4 = st.columns(4)
            dt = c1.date_input("Date")
            stock = c2.text_input("Stock").upper().strip()
            ttype = c3.selectbox("Type", ["DEPOSIT", "WITHDRAW", "BUY", "SELL", "FINE", "IPO"])
            medium = c4.selectbox("Medium", ["Global", "Collateral", "Bank", "Other"])

            c5, c6, c7 = st.columns(3)
            amount = c5.number_input("Amount", step=1.0, value=0.0)
            charge = c6.number_input("Charge", step=1.0, value=0.0)
            reference = c7.text_input("Reference")
            remark = st.text_input("Remark")

            if st.form_submit_button("Save TMS Transaction"):
                final_amount = amount if ttype in {"DEPOSIT", "SELL"} else -abs(amount)
                row = pd.DataFrame([
                    {
                        "Date": dt,
                        "Stock": stock,
                        "Type": ttype,
                        "Medium": medium,
                        "Amount": final_amount,
                        "Charge": charge,
                        "Remark": remark,
                        "Reference": reference,
                    }
                ])
                out = pd.concat([trx_df, row], ignore_index=True)
                storage.save_terminal_data("tms_trx", out)
                _log_activity(storage, "TMS", stock or "N/A", "ADD", f"Recorded {ttype} via {medium}", final_amount)
                st.success("Saved TMS transaction")
                st.rerun()

    with t2:
        if trx_df.empty:
            st.info("No TMS transactions yet.")
        else:
            view = trx_df.copy()
            view["Date"] = pd.to_datetime(view["Date"], errors="coerce")
            view = view.sort_values("Date")
            view["Net_Balance"] = pd.to_numeric(view["Amount"], errors="coerce").fillna(0).cumsum()

            def _trx_color(row):
                t = str(row.get("Type", "")).upper()
                if "DEPOSIT" in t:
                    return ["background-color:#e8f7ee"] * len(row)
                if "SELL" in t:
                    return ["background-color:#eaf2ff"] * len(row)
                if "BUY" in t or "WITHDRAW" in t or "FINE" in t:
                    return ["background-color:#fdecec"] * len(row)
                return [""] * len(row)

            styled = view.style.apply(_trx_color, axis=1).format({"Amount": "{:.2f}", "Charge": "{:.2f}", "Net_Balance": "{:.2f}"})
            st.dataframe(styled, width="stretch", height=350)

    with t3:
        edited = st.data_editor(trx_df, width="stretch", num_rows="dynamic")
        if st.button("Force Save TMS Edits"):
            storage.save_terminal_data("tms_trx", edited)
            _log_activity(storage, "TMS", "SYSTEM", "FORCE_EDIT", "Edited raw tms/tms_trx.csv", 0.0)
            st.success("Saved")

    with t4:
        if not trx_df.empty:
            st.download_button(
                "Download TMS Ledger CSV",
                trx_df.to_csv(index=False).encode("utf-8"),
                file_name=f"TMS_Trx_Ledger_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )


def render_terminal_hub(storage: DataStorage, ledger_df: pd.DataFrame, holdings_df: pd.DataFrame) -> None:
    st.header("🖥️ NEPSE Terminal Hub")
    st.caption("Absorbed from Nepse_Terminal and integrated with your ledger + holdings.")

    portfolio_df = storage.get_terminal_data("portfolio")
    watchlist_df = storage.get_terminal_data("watchlist")
    history_df = storage.get_terminal_data("history")
    diary_df = storage.get_terminal_data("diary")
    cache_df = storage.get_terminal_data("cache")
    activity_df = storage.get_terminal_data("activity_log")
    wealth_df = storage.get_terminal_data("wealth")

    top1, top2 = st.columns([3, 1])
    with top2:
        if st.button("⚡ Sync Live Market Cache", type="primary"):
            with st.spinner("Syncing market data..."):
                cache_df, _ = _sync_market_cache(storage, holdings_df, watchlist_df)
            st.success("Market cache synced")

    metrics = _compute_integrated_metrics(ledger_df, holdings_df, cache_df, history_df)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Integrated Invested", f"Rs {metrics['invested']:,.2f}")
    m2.metric("Integrated Market Value", f"Rs {metrics['market']:,.2f}")
    m3.metric("Unrealized P/L", f"Rs {metrics['unrealized']:,.2f}")
    m4.metric("Realized P/L", f"Rs {metrics['realized']:,.2f}")

    tabs = st.tabs(["Portfolio", "Watchlist", "History", "Diary", "Cache", "Activity", "Wealth Curve", "TMS Hub", "Risk Engine"])

    with tabs[0]:
        edited = st.data_editor(portfolio_df, width="stretch", num_rows="dynamic")
        if st.button("Save Portfolio"):
            storage.save_terminal_data("portfolio", edited)
            _log_activity(storage, "SYSTEM", "PORTFOLIO", "SAVE", "Portfolio updated", 0.0)
            st.success("Portfolio saved")

    with tabs[1]:
        edited = st.data_editor(watchlist_df, width="stretch", num_rows="dynamic")
        if st.button("Save Watchlist"):
            storage.save_terminal_data("watchlist", edited)
            _log_activity(storage, "SYSTEM", "WATCHLIST", "SAVE", "Watchlist updated", 0.0)
            st.success("Watchlist saved")

    with tabs[2]:
        st.dataframe(history_df.sort_values("Date", ascending=False) if "Date" in history_df.columns else history_df, width="stretch")

    with tabs[3]:
        edited = st.data_editor(diary_df, width="stretch", num_rows="dynamic")
        if st.button("Save Diary"):
            storage.save_terminal_data("diary", edited)
            _log_activity(storage, "NOTE", "DIARY", "SAVE", "Diary updated", 0.0)
            st.success("Diary saved")

    with tabs[4]:
        edited = st.data_editor(cache_df, width="stretch", num_rows="dynamic")
        if st.button("Save Cache"):
            storage.save_terminal_data("cache", edited)
            st.success("Cache saved")

    with tabs[5]:
        led = ledger_df[["Date", "Category", "Description", "Amount"]].copy() if not ledger_df.empty else pd.DataFrame(columns=["Date", "Category", "Description", "Amount"])
        if not led.empty:
            led["Timestamp"] = pd.to_datetime(led["Date"]).astype(str)
            led["Action"] = "LEDGER"
            led["Symbol"] = led["Description"].astype(str).str.split("|").str[0].str.strip()
            led["Details"] = led["Description"]
            led = led[["Timestamp", "Category", "Symbol", "Action", "Details", "Amount"]]

        merged = pd.concat([activity_df, led], ignore_index=True) if not led.empty else activity_df
        merged = merged.sort_values("Timestamp", ascending=False) if "Timestamp" in merged.columns else merged

        def _act_color(row):
            c = str(row.get("Category", "")).upper()
            if c in {"SYSTEM"}:
                return ["background-color:#eef3ff"] * len(row)
            if c in {"TRADE", "TMS"}:
                return ["background-color:#fff8e6"] * len(row)
            if c in {"ALERT"}:
                return ["background-color:#fdecec"] * len(row)
            return [""] * len(row)

        st.dataframe(merged.style.apply(_act_color, axis=1), width="stretch", height=420)

        if st.button("Snapshot activity from ledger"):
            storage.save_terminal_data("activity_log", merged)
            st.success("Activity log synced")

    with tabs[6]:
        if wealth_df.empty:
            wealth_df = pd.DataFrame(columns=["Date", "Total_Investment", "Current_Value", "Total_PL", "Day_Change", "Sold_Volume"])

        today = _now_np().split(" ")[0]
        new_row = pd.DataFrame([
            {
                "Date": today,
                "Total_Investment": round(metrics["invested"], 2),
                "Current_Value": round(metrics["market"], 2),
                "Total_PL": round(metrics["unrealized"] + metrics["realized"], 2),
                "Day_Change": 0.0,
                "Sold_Volume": float(history_df["Received_Amount"].sum()) if (not history_df.empty and "Received_Amount" in history_df.columns) else 0.0,
            }
        ])
        wealth_df = wealth_df[wealth_df["Date"] != today] if "Date" in wealth_df.columns else wealth_df
        wealth_df = pd.concat([wealth_df, new_row], ignore_index=True)

        c1, c2 = st.columns([1, 2])
        if c1.button("Update Wealth Snapshot"):
            storage.save_terminal_data("wealth", wealth_df)
            _log_activity(storage, "SYSTEM", "WEALTH", "SNAPSHOT", "Updated wealth snapshot", 0.0)
            st.success("Wealth snapshot saved")

        if not wealth_df.empty:
            plot_df = wealth_df.copy()
            plot_df["Date"] = pd.to_datetime(plot_df["Date"], errors="coerce")
            c2.plotly_chart(px.line(plot_df.sort_values("Date"), x="Date", y="Total_PL", markers=True, title="Total P/L Trajectory"), width="stretch")
            st.dataframe(plot_df.sort_values("Date", ascending=False), width="stretch")

    with tabs[7]:
        _render_tms_hub(storage)

    with tabs[8]:
        st.subheader("🛡️ Portfolio Risk Engine")
        trx_df = storage.get_terminal_data("tms_trx")
        med = medium_exposure(trx_df)
        sec = sector_exposure(portfolio_df)

        c1, c2, c3 = st.columns(3)
        capital = c1.number_input("Risk Capital", min_value=0.0, value=100000.0, step=1000.0, key="risk_capital")
        entry = c2.number_input("Entry Price", min_value=0.0, value=100.0, step=0.1, key="risk_entry")
        stop = c3.number_input("Stop Price", min_value=0.0, value=95.0, step=0.1, key="risk_stop")
        risk_pct = st.slider("Risk per Trade %", min_value=0.1, max_value=5.0, value=1.0, step=0.1)
        qty = recommended_position_size(capital, risk_pct, entry, stop)
        st.metric("Suggested Position Size", f"{qty:,.2f} units")

        wealth_curve = pd.to_numeric(wealth_df.get("Total_PL", pd.Series(dtype=float)), errors="coerce")
        dd = drawdown_stats(wealth_curve)
        if not cache_df.empty and "LTP" in cache_df.columns:
            var95 = portfolio_var_95(pd.to_numeric(cache_df["LTP"], errors="coerce"), max(metrics["market"], 0.0))
        else:
            var95 = 0.0

        r1, r2 = st.columns(2)
        r1.metric("Current Drawdown %", f"{dd['current_drawdown_pct']:.2f}%")
        r2.metric("Max Drawdown %", f"{dd['max_drawdown_pct']:.2f}%")
        st.metric("Parametric VaR(95)", f"Rs {var95:,.2f}")

        c_med, c_sec = st.columns(2)
        c_med.dataframe(med, width="stretch")
        c_sec.dataframe(sec, width="stretch")
