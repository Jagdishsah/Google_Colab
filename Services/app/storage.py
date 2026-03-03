from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pandas as pd

from Services.app.config import StorageConfig
from Services.app.logger import log_event
from Services.app.supabase_store import SupabaseConfig, SupabaseFileStore

LEDGER_COLUMNS = [
    "Date",
    "Type",
    "Category",
    "Amount",
    "Status",
    "Due_Date",
    "Ref_ID",
    "Description",
    "Is_Non_Cash",
    "Dispute_Note",
    "Fiscal_Year",
]
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
    "cache": "Data/Logs/cache.csv",
    "price_log": "Data/Logs/price_log.csv",
    "error_log": "Data/Logs/error_log.csv",
    "stock_data_dir": "Data/Market_Data/Stock_Data",
    "data_analysis_dir": "Data/Market_Data/Data_analysis",
}

TERMINAL_SCHEMAS = {
    "portfolio": ["Symbol", "Sector", "Units", "Total_Cost", "WACC", "Buy_Date", "Stop_Loss", "Notes"],
    "watchlist": ["Symbol", "Target", "Remark"],
    "activity_log": ["Timestamp", "Category", "Symbol", "Action", "Details", "Amount"],
    "history": ["Date", "Buy_Date", "Symbol", "Units", "Buy_Price", "Sell_Price", "Invested_Amount", "Received_Amount", "Net_PL", "PL_Pct", "Reason"],
    "diary": ["Date", "Symbol", "Note", "Emotion", "Mistake", "Strategy"],
    "cache": ["Symbol", "LTP", "Change", "High52", "Low52", "LastUpdated"],
    "wealth": ["Date", "Total_Investment", "Current_Value", "Total_PL", "Day_Change", "Sold_Volume"],
    "price_log": ["Date", "Symbol", "LTP"],
    "data_metrics": ["Date", "Realized_PL", "Realized_PL_Pct", "Unrealized_PL", "Unrealized_PL_Pct"],
    "error_log": ["Date", "Time", "Context", "Error_Message", "Traceback"],
    "tms_trx": ["Date", "Stock", "Type", "Medium", "Amount", "Charge", "Remark", "Reference"],
}


class DataStorage:
    def __init__(self, supabase_config: SupabaseConfig | None, local_root: Path, storage_config: StorageConfig | None = None):
        self.local_root = local_root
        self.storage_config = storage_config or StorageConfig()
        self.sqlite_path = (local_root / self.storage_config.sqlite_path).resolve()
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.supabase = SupabaseFileStore(supabase_config)
        self.last_write_status: dict[str, str | bool] = {
            "ok": True,
            "backend": self.active_backend(),
            "path": "",
            "remote_ok": True,
            "local_ok": True,
            "error": "",
        }

    def _table_name(self, logical_key: str) -> str:
        return logical_key.replace("/", "__")

    def _use_supabase(self) -> bool:
        if not self.supabase.enabled():
            return False
        return self.storage_config.backend in {"supabase", "csv"}

    def _resolve(self, logical_key: str) -> str:
        return PATHS.get(logical_key, logical_key)

    def _read_sqlite(self, logical_key: str, columns: list[str]) -> pd.DataFrame:
        table = self._table_name(logical_key)
        if not self.sqlite_path.exists():
            return pd.DataFrame(columns=columns)
        try:
            with sqlite3.connect(self.sqlite_path) as conn:
                return pd.read_sql_query(f'SELECT * FROM "{table}"', conn)
        except Exception:
            return pd.DataFrame(columns=columns)

    def _save_sqlite(self, logical_key: str, data: pd.DataFrame) -> None:
        table = self._table_name(logical_key)
        with sqlite3.connect(self.sqlite_path) as conn:
            data.to_sql(table, conn, if_exists="replace", index=False)

    def _read(self, logical_key: str, columns: list[str]) -> pd.DataFrame:
        rel_path = self._resolve(logical_key)
        if self.storage_config.backend == "sqlite":
            return self._read_sqlite(logical_key, columns)

        if self._use_supabase():
            df = self.supabase.read_csv(rel_path, columns)
            if not df.empty:
                return df

        path = self.local_root / rel_path
        if path.exists():
            return pd.read_csv(path)
        return pd.DataFrame(columns=columns)

    def _set_status(self, *, ok: bool, path: str, remote_ok: bool, local_ok: bool, error: str = "") -> None:
        self.last_write_status = {
            "ok": ok,
            "backend": self.active_backend(),
            "path": path,
            "remote_ok": remote_ok,
            "local_ok": local_ok,
            "error": error,
        }

    def _save(self, logical_key: str, data: pd.DataFrame, message: str) -> None:
        rel_path = self._resolve(logical_key)
        remote_ok = True
        local_ok = True
        err = ""

        if self.storage_config.backend == "sqlite":
            self._save_sqlite(logical_key, data)

        if self._use_supabase():
            try:
                self.supabase.write_csv(rel_path, data)
            except Exception as ex:
                remote_ok = False
                err = f"Supabase write failed: {ex}"

        try:
            path = self.local_root / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data.to_csv(index=False), encoding="utf-8")
        except Exception as ex:
            local_ok = False
            err = f"{err} | Local mirror write failed: {ex}".strip(" |")

        ok = remote_ok and local_ok if self._use_supabase() else local_ok
        self._set_status(ok=ok, path=rel_path, remote_ok=remote_ok, local_ok=local_ok, error=err)

        log_event(
            "storage_write",
            {
                "path": rel_path,
                "message": message,
                "backend": self.active_backend(),
                "ok": ok,
                "remote_ok": remote_ok,
                "local_ok": local_ok,
                "error": err,
            },
        )

        if not ok:
            raise RuntimeError(err or "Storage write failed")

    def active_backend(self) -> str:
        if self._use_supabase():
            return "supabase"
        return self.storage_config.backend

    def get_storage_health(self) -> dict[str, str | bool]:
        return self.last_write_status

    def last_write_ok(self) -> bool:
        return bool(self.last_write_status.get("ok", False))

    def import_legacy_csv(self, rel_path: str, data: pd.DataFrame, skip_if_same: bool = True) -> bool:
        existing = self._read(rel_path, list(data.columns))
        if skip_if_same and not existing.empty:
            old = existing.to_csv(index=False)
            new = data.to_csv(index=False)
            if hashlib.sha256(old.encode()).hexdigest() == hashlib.sha256(new.encode()).hexdigest():
                return False
        self._save(rel_path, data, "Import legacy CSV")
        return True

    def get_ledger(self) -> pd.DataFrame:
        df = self._read("ledger", LEDGER_COLUMNS)
        if df.empty:
            return pd.DataFrame(columns=LEDGER_COLUMNS)
        for c in ["Date", "Due_Date"]:
            if c in df.columns:
                df[c] = pd.to_datetime(df[c], errors="coerce").dt.date
        for col in LEDGER_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df[LEDGER_COLUMNS]

    def save_ledger(self, data: pd.DataFrame) -> None:
        save_df = data.copy()
        save_df["Date"] = pd.to_datetime(save_df["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
        save_df["Due_Date"] = pd.to_datetime(save_df["Due_Date"], errors="coerce").dt.strftime("%Y-%m-%d")
        self._save("ledger", save_df[LEDGER_COLUMNS], "Update Ledger Master")

    def get_holdings(self) -> pd.DataFrame:
        df = self._read("holdings", HOLDINGS_COLUMNS)
        for col in HOLDINGS_COLUMNS:
            if col not in df.columns:
                df[col] = 0 if col != "Symbol" else ""
        return df[HOLDINGS_COLUMNS]

    def save_holdings(self, data: pd.DataFrame) -> None:
        self._save("holdings", data[HOLDINGS_COLUMNS], "Update Holdings")

    def get_terminal_data(self, logical_key: str) -> pd.DataFrame:
        cols = TERMINAL_SCHEMAS.get(logical_key, [])
        df = self._read(logical_key, cols)
        for col in cols:
            if col not in df.columns:
                df[col] = ""
        return df[cols] if cols else df

    def save_terminal_data(self, logical_key: str, data: pd.DataFrame) -> None:
        cols = TERMINAL_SCHEMAS.get(logical_key)
        if cols:
            for col in cols:
                if col not in data.columns:
                    data[col] = ""
            data = data[cols]
        self._save(logical_key, data, f"Update {logical_key}")

    def list_stock_data_files(self) -> list[str]:
        rel_dir = PATHS["stock_data_dir"]
        if self._use_supabase():
            files = self.supabase.list_paths(rel_dir + "/")
            if files:
                return sorted([Path(p).name for p in files])
        local_dir = self.local_root / rel_dir
        if local_dir.exists():
            return sorted([f.name for f in local_dir.glob("*.csv")])
        return []

    def get_stock_data(self, filename: str) -> pd.DataFrame:
        safe = filename if filename.endswith(".csv") else f"{filename}.csv"
        return self._read(f"{PATHS['stock_data_dir']}/{safe}", ["Date", "Open", "High", "Low", "Close", "Volume"])

    def save_stock_data(self, filename: str, data: pd.DataFrame) -> None:
        safe = filename if filename.endswith(".csv") else f"{filename}.csv"
        self._save(f"{PATHS['stock_data_dir']}/{safe}", data, f"Update stock data {safe}")

    def list_analysis_files(self) -> list[str]:
        rel_dir = PATHS["data_analysis_dir"]
        if self._use_supabase():
            files = self.supabase.list_paths(rel_dir + "/")
            if files:
                return sorted([Path(p).name for p in files])
        local_dir = self.local_root / rel_dir
        if local_dir.exists():
            return sorted([f.name for f in local_dir.glob("*.csv")])
        return []

    def get_analysis_data(self, filename: str) -> pd.DataFrame:
        safe = filename if filename.endswith(".csv") else f"{filename}.csv"
        return self._read(f"{PATHS['data_analysis_dir']}/{safe}", [])

    def save_analysis_data(self, filename: str, data: pd.DataFrame) -> None:
        safe = filename if filename.endswith(".csv") else f"{filename}.csv"
        self._save(f"{PATHS['data_analysis_dir']}/{safe}", data, f"Update analysis data {safe}")