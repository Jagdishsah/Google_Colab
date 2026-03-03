from __future__ import annotations
import streamlit as st
import hashlib
import sqlite3
from pathlib import Path
import pandas as pd
from Services.app.config import StorageConfig
from Services.app.logger import log_event
from Services.app.supabase_store import SupabaseConfig, SupabaseFileStore

LEDGER_COLUMNS = ["Date", "Type", "Category", "Amount", "Status", "Due_Date", "Ref_ID", "Description", "Is_Non_Cash", "Dispute_Note", "Fiscal_Year"]
HOLDINGS_COLUMNS = ["Symbol", "Total_Qty", "Pledged_Qty", "LTP", "Haircut"]

PATHS = {
    "ledger": "Data/TMS_Data/tms_ledger_master.csv",
    "holdings": "Data/TMS_Data/tms_holdings.csv",
    "tms_trx": "Data/TMS_Data/tms_trx.csv",
    "portfolio": "Data/User_Data/portfolio.csv",
    "watchlist": "Data/User_Data/watchlist.csv",
    "history": "Data/User_Data/history.csv",
    "diary": "Data/User_Data/diary.csv",
    "wealth": "Data/User_Data/wealth.csv",
    "data_metrics": "Data/User_Data/Data.csv",
    "activity_log": "Data/Logs/activity_log.csv",
    "stock_data_dir": "Data/Market_Data/Stock_Data",
    "data_analysis_dir": "Data/Market_Data/Data_analysis",
}

TERMINAL_SCHEMAS = {
    "portfolio": ["Symbol", "Sector", "Units", "Total_Cost", "WACC", "Buy_Date", "Stop_Loss", "Notes"],
    "watchlist": ["Symbol", "Target", "Remark"],
    "activity_log": ["Timestamp", "Category", "Symbol", "Action", "Details", "Amount"],
    "history": ["Date", "Buy_Date", "Symbol", "Units", "Buy_Price", "Sell_Price", "Invested_Amount", "Received_Amount", "Net_PL", "PL_Pct", "Reason"],
    "diary": ["Date", "Symbol", "Note", "Emotion", "Mistake", "Strategy"],
    "wealth": ["Date", "Total_Investment", "Current_Value", "Total_PL", "Day_Change", "Sold_Volume"],
    "tms_trx": ["Date", "Stock", "Type", "Medium", "Amount", "Charge", "Remark", "Reference"]
}

class DataStorage:
    def __init__(self, supabase_config: SupabaseConfig | None, local_root: Path, storage_config: StorageConfig | None = None):
        self.local_root = local_root
        self.storage_config = storage_config or StorageConfig()
        self.sqlite_path = (local_root / self.storage_config.sqlite_path).resolve()
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.supabase = SupabaseFileStore(supabase_config)
        self.last_write_status = {"ok": True, "backend": "", "path": "", "remote_ok": True, "local_ok": True, "error": ""}

    def _get_target_table(self, rel_path: str) -> str:
        return "public_Files" if "Market_Data" in rel_path else "app_Files"

    def _use_supabase(self) -> bool:
        return self.supabase.enabled() and self.storage_config.backend in {"supabase", "csv"}

    def _read(self, logical_key: str, columns: list[str]) -> pd.DataFrame:
        rel_path = PATHS.get(logical_key, logical_key)
        if self.storage_config.backend == "sqlite":
            table = logical_key.replace("/", "__")
            try:
                with sqlite3.connect(self.sqlite_path) as conn:
                    return pd.read_sql_query(f'SELECT * FROM "{table}"', conn)
            except: return pd.DataFrame(columns=columns)

        if self._use_supabase():
            df = self.supabase.read_csv(rel_path, columns, table=self._get_target_table(rel_path), 
                                        user_id=st.session_state.get('user_id'), access_token=st.session_state.get('access_token'))
            if not df.empty: return df

        path = self.local_root / rel_path
        return pd.read_csv(path) if path.exists() else pd.DataFrame(columns=columns)

    def _save(self, logical_key: str, data: pd.DataFrame, message: str) -> None:
        rel_path = PATHS.get(logical_key, logical_key)
        remote_ok, local_ok, err = True, True, ""
        if self._use_supabase():
            try: self.supabase.write_csv(rel_path, data, table=self._get_target_table(rel_path), 
                                         user_id=st.session_state.get('user_id'), access_token=st.session_state.get('access_token'))
            except Exception as ex: remote_ok, err = False, str(ex)
        try:
            path = self.local_root / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data.to_csv(index=False), encoding="utf-8")
        except Exception as ex: local_ok, err = False, f"{err} | {ex}".strip(" | ")
        self.last_write_status = {"ok": remote_ok and local_ok, "path": rel_path, "remote_ok": remote_ok, "local_ok": local_ok, "error": err}
        if not self.last_write_status['ok']: raise RuntimeError(err)

    def get_ledger(self) -> pd.DataFrame:
        df = self._read("ledger", LEDGER_COLUMNS)
        for c in ["Date", "Due_Date"]:
            if c in df.columns: df[c] = pd.to_datetime(df[c], errors="coerce").dt.date
        return df[LEDGER_COLUMNS]

    def get_holdings(self) -> pd.DataFrame:
        return self._read("holdings", HOLDINGS_COLUMNS)

    def save_ledger(self, data: pd.DataFrame) -> None: self._save("ledger", data, "Update Ledger")
    def save_holdings(self, data: pd.DataFrame) -> None: self._save("holdings", data, "Update Holdings")
    def active_backend(self) -> str: return "supabase" if self._use_supabase() else self.storage_config.backend
    def login(self, e, p): return self.supabase.login(e, p)
    def logout(self, t): self.supabase.logout(t)
    def get_storage_health(self) -> dict: 
        return self.last_write_status

    def list_stock_data_files(self) -> list[str]:
        rel_dir = PATHS["stock_data_dir"]
        if self._use_supabase():
            return self.supabase.list_paths(rel_dir + "/", table="public_Files")
        path = self.local_root / rel_dir
        return [f.name for f in path.glob("*.csv")] if path.exists() else []

    def get_stock_data(self, symbol: str) -> pd.DataFrame:
        rel_path = f"{PATHS['stock_data_dir']}/{symbol}.csv"
        return self._read(rel_path, [])

    def list_analysis_files(self) -> list[str]:
        rel_dir = PATHS["data_analysis_dir"]
        if self._use_supabase():
            return self.supabase.list_paths(rel_dir + "/", table="public_Files")
        path = self.local_root / rel_dir
        return [f.name for f in path.glob("*.csv")] if path.exists() else []

    def get_analysis_data(self, filename: str) -> pd.DataFrame:
        rel_path = f"{PATHS['data_analysis_dir']}/{filename}"
        return self._read(rel_path, [])

    def save_analysis_data(self, filename: str, data: pd.DataFrame) -> None:
        rel_path = f"{PATHS['data_analysis_dir']}/{filename}"
        self._save(rel_path, data, f"Update Analysis {filename}")


    def get_terminal_data(self, category: str) -> pd.DataFrame:
        if category not in TERMINAL_SCHEMAS:
            return pd.DataFrame()
        return self._read(category, TERMINAL_SCHEMAS[category])

    def save_terminal_data(self, category: str, data: pd.DataFrame) -> None:
        if category in TERMINAL_SCHEMAS:
            self._save(category, data, f"Update Terminal {category}")
