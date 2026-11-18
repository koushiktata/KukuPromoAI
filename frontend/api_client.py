"""Thin HTTP client for the FastAPI backend. The frontend holds no business logic."""
from __future__ import annotations

import os

import requests
import streamlit as st

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = 30


class APIError(Exception):
    pass


def _req(method: str, path: str, timeout: float = TIMEOUT, **kw):
    try:
        r = requests.request(method, f"{BACKEND}{path}", timeout=timeout, **kw)
    except requests.RequestException as e:
        raise APIError(f"Backend not reachable at {BACKEND}. Start it with: uvicorn backend.main:app --port 8000") from e
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = r.text[:200]
        raise APIError(f"{r.status_code}: {detail}")
    return r


@st.cache_data(ttl=4, show_spinner=False)
def get(path: str, params: tuple = ()) -> dict:
    return _req("GET", path, params=dict(params)).json()


@st.cache_data(ttl=4, show_spinner=False)
def download(path: str, params: tuple = ()) -> tuple[bytes, dict]:
    r = _req("GET", path, params=dict(params))
    return r.content, dict(r.headers)


def post(path: str, json: dict | None = None, timeout: float = TIMEOUT) -> dict:
    out = _req("POST", path, timeout=timeout, json=json or {}).json()
    get.clear()
    download.clear()
    return out


def put(path: str, json: dict | None = None) -> dict:
    out = _req("PUT", path, json=json or {}).json()
    get.clear()
    return out


def delete(path: str) -> dict:
    out = _req("DELETE", path).json()
    get.clear()
    return out


def upload_show(name: str, files) -> dict:
    """Create a new show from several uploaded episode screenplays."""
    try:
        r = requests.post(f"{BACKEND}/api/shows", data={"name": name}, timeout=120,
                          files=[("files", (f.name, f.getvalue(), "text/plain")) for f in files])
    except requests.RequestException as e:
        raise APIError(f"Backend not reachable at {BACKEND}") from e
    if r.status_code >= 400:
        try:
            d = r.json().get("detail")
        except ValueError:
            d = r.text[:200]
        if isinstance(d, dict):
            d = d.get("message", "") + "; " + "; ".join(f"{x['file']}: {x['reason']}" for x in d.get("rejected", [])[:5])
        raise APIError(f"{r.status_code}: {d}")
    get.clear()
    return r.json()


def upload(files) -> dict:
    out = _req("POST", "/api/episodes/upload",
               files=[("files", (f.name, f.getvalue(), "text/plain")) for f in files]).json()
    get.clear()
    return out


def safe_get(path: str, params: dict | None = None, default=None):
    try:
        return get(path, tuple(sorted((params or {}).items())))
    except APIError as e:
        st.session_state["_api_error"] = str(e)
        return default
