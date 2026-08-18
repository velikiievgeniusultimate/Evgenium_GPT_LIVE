from __future__ import annotations

import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path


def ensure_vosk_model(url: str, destination: Path) -> Path:
    if destination.exists() and (destination / "conf").exists():
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="egl-model-") as td:
        archive = Path(td) / "model.zip"
        print(f"Downloading Russian Vosk model: {url}")
        urllib.request.urlretrieve(url, archive)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(td)
        candidates = [p for p in Path(td).iterdir() if p.is_dir() and (p / "conf").exists()]
        if not candidates:
            raise RuntimeError("Downloaded archive does not contain a Vosk model")
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(candidates[0]), str(destination))
    return destination
