import importlib.util
import zipfile

import streamlit as st

from src import config
from src.ui import common


def load_build():
    spec = importlib.util.spec_from_file_location("website_build", config.ROOT / "website" / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_website_build_packs_the_whole_app(tmp_path):
    out = load_build().build(tmp_path / "_site")
    assert (out / "index.html").exists() and (out / "demo" / "index.html").exists() and (out / ".nojekyll").exists()
    assert not (out / "build.py").exists()
    names = set(zipfile.ZipFile(out / "demo" / "app.zip").namelist())
    assert {"app.py", ".streamlit/config.toml", "sample/games.yaml", "src/ui/pages/analyze.py"} <= names
    assert not any("__pycache__" in n or n.startswith(("tests/", "logs/", "film/")) for n in names)


def test_browser_demo_always_shows_the_demo_data(monkeypatch):
    monkeypatch.setattr(config, "IN_BROWSER", True)
    st.session_state.clear()
    st.session_state.use_sample = False
    assert common.use_sample()
