from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from presse_agrumes.config import read_config_file


def test_read_config_file(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[server]
port = 9090

[auth]
user = "testeur"
password = "secret-config"
""",
        encoding="utf-8",
    )
    data = read_config_file(path)
    assert data["server"]["port"] == 9090
    assert data["auth"]["password"] == "secret-config"


def test_invalid_config_file(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text("[server\nport = 1", encoding="utf-8")
    with pytest.raises(RuntimeError):
        read_config_file(path)


def test_config_password_source(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[server]
port = 9091

[paths]
data_dir = "./data-test"
allowed_roots = ["./media"]

[auth]
user = "config-user"
password = "config-password"
disabled = false
""",
        encoding="utf-8",
    )
    env = os.environ.copy()
    for name in (
        "PA_AUTH_DISABLED", "PA_AUTH_USER", "PA_AUTH_PASSWORD",
        "PA_HOST", "PA_PORT", "PA_DATA_DIR", "PA_ALLOWED_ROOTS",
    ):
        env.pop(name, None)
    env["PA_CONFIG_FILE"] = str(path)
    code = (
        "from presse_agrumes import config; "
        "print(config.AUTH_PASSWORD_SOURCE); "
        "print(config.AUTH_PASSWORD); "
        "print(config.PORT); "
        "print(config.AUTH_USER); "
        "print(config.DATA_DIR)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parent.parent,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "config"
    assert lines[1] == "config-password"
    assert lines[2] == "9091"
    assert lines[3] == "config-user"
    assert lines[4] == str((tmp_path / "data-test").resolve())
