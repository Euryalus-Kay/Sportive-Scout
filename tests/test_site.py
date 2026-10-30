import importlib.util
import io
import zipfile

import pytest

import streamlit as st

from src import config, pack
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


def test_browser_shows_the_demo_until_an_analysis_is_opened(project, monkeypatch):
    monkeypatch.setattr(config, "IN_BROWSER", True)
    st.session_state.clear()
    st.session_state.use_sample = False
    assert common.use_sample()
    config.save_raw({"matchup": {"our_team": "A", "opponent": "B"},
                     "games": [{"id": "g1", "file": "g1.mp4", "analyzed_team_name": "A"}]})
    config.LOGS_DIR.mkdir(exist_ok=True)
    (config.LOGS_DIR / "g1.json").write_text('[{"timestamp": "00:04"}]')
    data = pack.build_pack(project / "p.zip").read_bytes()
    (config.LOGS_DIR / "g1.json").unlink()
    config.GAMES_FILE.unlink()
    assert pack.open_pack(data) == 1 and (config.LOGS_DIR / "g1.json").exists()
    assert not common.use_sample()


def test_a_pack_only_writes_games_and_logs(project):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("games.yaml", "matchup: {our_team: A, opponent: B}\ngames: []\n")
        z.writestr("logs/../../evil.json", "[]")
        z.writestr("app.py", "print('no')")
    assert pack.open_pack(buf.getvalue()) == 0
    assert not (project.parent / "evil.json").exists()
    with pytest.raises(ValueError):
        pack.open_pack(_zip_without_games())


def _zip_without_games():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("notes.txt", "hi")
    return buf.getvalue()
