from pathlib import Path

import pandas as pd

from Services.app.config import StorageConfig
from Services.app.storage import DataStorage
from Services.app.supabase_store import SupabaseConfig


class DummySupabase:
    def __init__(self):
        self.writes = []
        self.reads = {}

    def enabled(self):
        return True

    def read_csv(self, path, columns):
        return self.reads.get(path, pd.DataFrame(columns=columns))

    def write_csv(self, path, data):
        self.writes.append((path, data.copy()))
        self.reads[path] = data.copy()

    def list_paths(self, prefix):
        return []


def test_csv_backend_uses_supabase_when_configured(tmp_path: Path):
    storage = DataStorage(
        supabase_config=SupabaseConfig(url="https://x.supabase.co", key="k", table="app_files"),
        local_root=tmp_path,
        storage_config=StorageConfig(backend="csv"),
    )
    storage.supabase = DummySupabase()

    ledger = pd.DataFrame(
        [
            {
                "Date": "2026-01-01",
                "Type": "TMS",
                "Category": "DEPOSIT",
                "Amount": 1000,
                "Status": "Cleared",
                "Due_Date": "2026-01-01",
                "Ref_ID": "r1",
                "Description": "test",
                "Is_Non_Cash": "No",
                "Dispute_Note": "",
                "Fiscal_Year": "2082/83",
            }
        ]
    )
    storage.save_ledger(ledger)
    assert storage.active_backend() == "supabase"
    assert storage.last_write_ok() is True
    assert any("tms_ledger_master.csv" in path for path, _ in storage.supabase.writes)


def test_import_legacy_csv_is_idempotent(tmp_path: Path):
    storage = DataStorage(
        supabase_config=SupabaseConfig(url="https://x.supabase.co", key="k", table="app_files"),
        local_root=tmp_path,
        storage_config=StorageConfig(backend="supabase"),
    )
    storage.supabase = DummySupabase()

    df = pd.DataFrame([{"A": 1, "B": 2}])
    assert storage.import_legacy_csv("Data/User_Data/portfolio.csv", df, skip_if_same=True) is True
    assert storage.import_legacy_csv("Data/User_Data/portfolio.csv", df, skip_if_same=True) is False