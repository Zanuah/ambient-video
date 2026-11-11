"""Keep each test on its own data and output folders."""

import pytest


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("AMBIENT_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("AMBIENT_OUTPUT", str(tmp_path / "output"))
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", str(tmp_path / "client_secret.json"))
    monkeypatch.setenv("YOUTUBE_TOKEN", str(tmp_path / "token.json"))
