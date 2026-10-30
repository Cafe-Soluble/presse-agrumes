from __future__ import annotations

from pathlib import Path

import pytest

from presse_agrumes import config
from tests.conftest import TEST_CONFIG


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
    data = config.read_config_file(path)
    assert data["server"]["port"] == 9090
    assert data["auth"]["password"] == "secret-config"


def test_invalid_config_file(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text("[server\nport = 1", encoding="utf-8")
    with pytest.raises(RuntimeError):
        config.read_config_file(path)


def test_config_password_and_paths(tmp_path: Path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[server]
host = "127.0.0.1"
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
    try:
        config.apply_config_file(config_file)
        assert config.AUTH_PASSWORD_SOURCE == "config"
        assert config.AUTH_PASSWORD == "config-password"
        assert config.PORT == 9091
        assert config.AUTH_USER == "config-user"
        assert config.DATA_DIR == (tmp_path / "data-test").resolve()
        assert config.ALLOWED_ROOTS == [(tmp_path / "media").resolve()]
        assert config.AUTH_ENABLED
    finally:
        config.apply_config_file(TEST_CONFIG)


def test_missing_password_is_rejected(tmp_path: Path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[auth]
disabled = false
""",
        encoding="utf-8",
    )
    try:
        with pytest.raises(RuntimeError):
            config.apply_config_file(config_file)
    finally:
        config.apply_config_file(TEST_CONFIG)
