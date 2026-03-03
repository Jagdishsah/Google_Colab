from __future__ import annotations

from io import StringIO

import pandas as pd
import requests
import streamlit as st

from Services.app.config import load_github_config
from Services.app.storage import DataStorage, PATHS


def _github_get_csv(repo: str, token: str, path: str) -> pd.DataFrame | None:
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    resp = requests.get(url, headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.raw+json"}, timeout=30)
    if resp.status_code >= 300:
        return None
    return pd.read_csv(StringIO(resp.text))


def _github_list_dir(repo: str, token: str, path: str) -> list[str]:
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    resp = requests.get(url, headers={"Authorization": f"token {token}"}, timeout=30)
    if resp.status_code >= 300:
        return []
    rows = resp.json() or []
    return [item["name"] for item in rows if item.get("name", "").endswith(".csv")]


def _import_one(storage: DataStorage, rel_path: str, repo: str, token: str, failed: list[str]) -> tuple[int, int]:
    df = _github_get_csv(repo, token, rel_path)
    if df is None:
        failed.append(rel_path)
        return 0, 0
    try:
        changed = storage.import_legacy_csv(rel_path, df, skip_if_same=True)
        return (1, 0) if changed else (0, 1)
    except Exception:
        failed.append(rel_path)
        return 0, 0


def render_restore(storage: DataStorage) -> None:
    st.header("♻️ GitHub to Supabase Restore")
    st.caption("Idempotent migration tool for legacy GitHub CSV files.")

    gh = load_github_config()
    if not gh:
        st.warning("GitHub credentials not configured in Streamlit secrets.")
        return

    if st.button("Restore all GitHub CSV data into Supabase", type="primary"):
        migrated = 0
        skipped = 0
        failed: list[str] = []
        token = gh["token"]
        repo = gh["repo_name"]

        for key, rel_path in PATHS.items():
            if key.endswith("_dir"):
                continue
            c, s = _import_one(storage, rel_path, repo, token, failed)
            migrated += c
            skipped += s

        for name in _github_list_dir(repo, token, PATHS["stock_data_dir"]):
            rel = f"{PATHS['stock_data_dir']}/{name}"
            c, s = _import_one(storage, rel, repo, token, failed)
            migrated += c
            skipped += s

        for name in _github_list_dir(repo, token, PATHS["data_analysis_dir"]):
            rel = f"{PATHS['data_analysis_dir']}/{name}"
            c, s = _import_one(storage, rel, repo, token, failed)
            migrated += c
            skipped += s

        st.success(f"Migration complete. Imported: {migrated}, Skipped(unchanged): {skipped}.")
        if failed:
            st.warning(f"Failed to migrate {len(failed)} files: {', '.join(failed[:8])}")