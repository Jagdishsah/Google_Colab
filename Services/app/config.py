from dataclasses import dataclass

import streamlit as st

from Services.app.supabase_store import SupabaseConfig


@dataclass
class AuthConfig:
    username: str
    password: str


@dataclass
class StorageConfig:
    backend: str = "supabase"  # supabase | csv | sqlite
    sqlite_path: str = "data/terminal.db"


def load_auth_config() -> AuthConfig | None:
    try:
        if "auth" in st.secrets:
            return AuthConfig(
                username=st.secrets["auth"]["username"],
                password=st.secrets["auth"]["password"],
            )
        return AuthConfig(
            username=st.secrets["app_username"],
            password=st.secrets["app_password"],
        )
    except Exception:
        return None


def load_supabase_config() -> SupabaseConfig | None:
    try:
        cfg = st.secrets.get("supabase", {})
        key = cfg.get("service_key") or cfg.get("service_role_key") or cfg.get("key")
        if not cfg.get("url") or not key:
            return None
        return SupabaseConfig(
            url=str(cfg["url"]),
            key=str(key),
            table=str(cfg.get('table') or 'app_files'),
        )
    except Exception:
        return None


def load_github_config() -> dict[str, str] | None:
    try:
        cfg = st.secrets.get("github", {})
        return {"token": str(cfg["token"]), "repo_name": str(cfg["repo_name"])}
    except Exception:
        return None


def load_storage_config() -> StorageConfig:
    try:
        cfg = st.secrets.get("storage", {})
        return StorageConfig(
            backend=str(cfg.get("backend", "supabase")).lower(),
            sqlite_path=str(cfg.get("sqlite_path", "data/terminal.db")),
        )
    except Exception:
        return StorageConfig()