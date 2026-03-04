from __future__ import annotations
import time
from dataclasses import dataclass
from io import StringIO
from typing import Any
import pandas as pd
import requests

@dataclass
class SupabaseConfig:
    url: str
    key: str
    table: str = "app_Files"

class SupabaseFileStore:
    def __init__(self, config: SupabaseConfig | None, retry_count: int = 3, retry_backoff_s: float = 0.4):
        self.config = config
        self.retry_count = max(1, retry_count)
        self.retry_backoff_s = max(0.0, retry_backoff_s)

    def enabled(self) -> bool:
        return bool(self.config and self.config.url and self.config.key)

    def _headers(self, access_token: str | None = None, require_auth: bool = False) -> dict[str, str]:
        assert self.config is not None
        if require_auth and not access_token:
            raise ValueError("Access token required for this operation to enforce RLS integrity.")
        
        token = access_token or self.config.key
        return {
            "apikey": self.config.key,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def login(self, email: str, password: str) -> dict[str, Any]:
        endpoint = f"{self.config.url.rstrip('/')}/auth/v1/token?grant_type=password"
        resp = requests.post(endpoint, headers=self._headers(), json={"email": email, "password": password})
        resp.raise_for_status()
        return resp.json()

    def signup(self, email: str, password: str) -> dict[str, Any]:
        endpoint = f"{self.config.url.rstrip('/')}/auth/v1/signup"
        resp = requests.post(endpoint, headers=self._headers(), json={"email": email, "password": password})
        resp.raise_for_status()
        return resp.json()

    def logout(self, access_token: str) -> None:
        endpoint = f"{self.config.url.rstrip('/')}/auth/v1/logout"
        resp = requests.post(endpoint, headers=self._headers(access_token))
        resp.raise_for_status()

    def _endpoint(self, table_override: str | None = None) -> str:
        assert self.config is not None
        table = table_override or self.config.table
        return f"{self.config.url.rstrip('/')}/rest/v1/{table}"

    def _with_retry(self, fn):
        err = None
        for i in range(self.retry_count):
            try: return fn()
            except Exception as ex:
                err = ex
                if i < self.retry_count - 1: time.sleep(self.retry_backoff_s * (2**i))
        if err: raise err

    def read_text(self, path: str, table: str | None = None, user_id: str | None = None, access_token: str | None = None) -> str | None:
        if not self.enabled(): return None
        if user_id and not access_token:
            raise SecurityError("user_id provided without access_token; RLS spoofing blocked.")
            
        def _op():
            params = {"select": "content", "path": f"eq.{path}", "limit": 1}
            if user_id: params["user_id"] = f"eq.{user_id}"
            resp = requests.get(self._endpoint(table), headers=self._headers(access_token, require_auth=bool(user_id)), params=params, timeout=20)
            resp.raise_for_status()
            rows = resp.json() or []
            return rows[0].get("content") if rows else None
        try: return self._with_retry(_op)
        except: return None

    def write_text(self, path: str, content: str, table: str | None = None, user_id: str | None = None, access_token: str | None = None) -> None:
        if not self.enabled(): raise RuntimeError("Supabase not configured")
        if user_id and not access_token:
            raise SecurityError("user_id provided without access_token; RLS spoofing blocked.")

        def _op():
            payload = {"path": path, "content": content}
            if user_id: payload["user_id"] = user_id
            requests.post(
                self._endpoint(table), 
                headers={**self._headers(access_token, require_auth=bool(user_id)), "Prefer": "resolution=merge-duplicates"},
                params={"on_conflict": "path"}, 
                json=[payload], 
                timeout=20
            ).raise_for_status()
        self._with_retry(_op)

    def list_paths(self, prefix: str, table: str | None = None, user_id: str | None = None, access_token: str | None = None) -> list[str]:
        if not self.enabled(): return []
        def _op():
            params = {"select": "path", "path": f"like.{prefix}%"}
            if user_id: params["user_id"] = f"eq.{user_id}"
            resp = requests.get(self._endpoint(table), headers=self._headers(access_token, require_auth=bool(user_id)), params=params, timeout=20)
            resp.raise_for_status()
            rows = resp.json() or []
            return sorted([r.get("path", "") for r in rows if r.get("path", "").endswith(".csv")])
        try: return self._with_retry(_op)
        except: return []

    def read_csv(self, path: str, columns: list[str], table: str | None = None, user_id: str | None = None, access_token: str | None = None) -> pd.DataFrame:
        text = self.read_text(path, table, user_id, access_token)
        return pd.read_csv(StringIO(text)) if text else pd.DataFrame(columns=columns)

    def write_csv(self, path: str, data: pd.DataFrame, table: str | None = None, user_id: str | None = None, access_token: str | None = None) -> None:
        self.write_text(path, data.to_csv(index=False), table, user_id, access_token)

    def delete_user_data(self, path: str, table: str | None = None, user_id: str | None = None, access_token: str | None = None) -> None:
        if not self.enabled(): return
        if user_id and not access_token:
            raise SecurityError("user_id provided without access_token; RLS spoofing blocked.")

        def _op():
            params = {"path": f"eq.{path}"}
            if user_id: params["user_id"] = f"eq.{user_id}"
            resp = requests.delete(self._endpoint(table), headers=self._headers(access_token, require_auth=bool(user_id)), params=params, timeout=20)
            resp.raise_for_status()
        self._with_retry(_op)

class SecurityError(Exception): pass