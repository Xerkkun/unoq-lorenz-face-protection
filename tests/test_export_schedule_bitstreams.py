from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


SOFTWARE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SOFTWARE_ROOT / "scripts" / "export_schedule_bitstreams.py"


def _run_export(output_dir: Path) -> dict[str, object]:
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output-dir",
            str(output_dir),
            "--seed-label",
            "pytest-public-label",
            "--stream-count",
            "3",
            "--bytes-per-stream",
            "4096",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))


def test_exported_teaching_streams_are_distinct_and_reproducible(tmp_path: Path):
    first = _run_export(tmp_path / "first")
    second = _run_export(tmp_path / "second")

    assert first == second
    assert first["stream_count"] == 3
    assert first["bytes_per_stream"] == 4096
    hashes = []
    for entry in first["streams"]:
        path = tmp_path / "first" / entry["path"]
        payload = path.read_bytes()
        assert len(payload) == 4096
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"]
        hashes.append(entry["sha256"])
    assert len(set(hashes)) == 3
