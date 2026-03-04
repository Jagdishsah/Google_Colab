import os
from dataclasses import dataclass
import streamlit as st
from Services.app.supabase_store import SupabaseConfig

@dataclass
class AuthConfig:
    username: str
    password: str

@dataclass
class StorageConfig:
    backend: str = "supabase"
    sqlite_path: str = "data/terminal.db"

def load_auth_config() -> AuthConfig | None:
    try:
        if "auth" in st.secrets:
            return AuthConfig(username=st.secrets["auth"]["username"], password=st.secrets["auth"]["password"])
        return AuthConfig(username=st.secrets["app_username"], password=st.secrets["app_password"])
    except Exception:
        return None

def load_supabase_config() -> SupabaseConfig | None:
    try:
        cfg = st.secrets.get("supabase", {})
        url = cfg.get("url") or os.getenv("SUPABASE_URL")
        key = cfg.get("service_key") or cfg.get("service_role_key") or cfg.get("key") or os.getenv("SUPABASE_KEY")
        if not url or not key:
            return None
        return SupabaseConfig(url=str(url), key=str(key), table=str(cfg.get('table') or 'app_Files'))
    except Exception:
        return None

def load_github_config() -> dict[str, str] | None:
    try:
        cfg = st.secrets.get("github", {})
        token = cfg.get("token") or os.getenv("GITHUB_TOKEN")
        repo = cfg.get("repo_name") or os.getenv("REPO_NAME")
        if not token or not repo:
            return None
        return {"token": str(token), "repo_name": str(repo)}
    except Exception:
        return None

def load_storage_config() -> StorageConfig:
    try:
        cfg = st.secrets.get("storage", {})
        return StorageConfig(backend=str(cfg.get("backend", "supabase")).lower(), sqlite_path=str(cfg.get("sqlite_path", "data/terminal.db")))
    except Exception:
        return StorageConfig()