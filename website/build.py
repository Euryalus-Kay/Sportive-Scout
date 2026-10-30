"""Builds the website (landing page plus the in-browser demo) into _site/.

    python website/build.py

The demo is the real app, run in the browser by stlite (Streamlit on Pyodide),
so it always matches the code it was built from. GitHub Actions runs this on
every push to main and publishes _site/ to the gh-pages branch.
"""
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "website"
OUT = ROOT / "_site"

# What the demo needs: the app, its theme and the demo games (their logs are made on load).
APP_FILES = ["app.py", ".streamlit/config.toml", "sample/games.yaml"]
APP_DIRS = ["src"]


def app_files():
    yield from (ROOT / name for name in APP_FILES)
    for folder in APP_DIRS:
        yield from sorted(p for p in (ROOT / folder).rglob("*.py") if "__pycache__" not in p.parts)


def build(out=OUT):
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(SITE, out, ignore=shutil.ignore_patterns("build.py", "build_game.py", "game_template", "__pycache__", "*.pyc"))
    with zipfile.ZipFile(out / "demo" / "app.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in app_files():
            archive.write(path, path.relative_to(ROOT).as_posix())
    (out / ".nojekyll").touch()          # serve files as they are, no Jekyll
    return out


if __name__ == "__main__":
    print(f"Built {build().relative_to(ROOT)}/")
