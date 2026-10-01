import os


def test_project_env_loads_all_provider_keys(monkeypatch, tmp_path):
    from engine.env_config import API_KEYS, load_environment
    for key in API_KEYS:
        monkeypatch.delenv(key, raising=False)
    (tmp_path / ".env").write_text(
        "GEMINI_API_KEY=gemini-test\n"
        "GROQ_API_KEY=groq-test\n"
        "ELEVENLABS_API_KEY=eleven-test\n",
        encoding="utf-8",
    )
    report = load_environment(tmp_path)
    assert report["present"]["GEMINI_API_KEY"]
    assert report["present"]["GROQ_API_KEY"]
    assert report["present"]["ELEVENLABS_API_KEY"]
    assert str(tmp_path / ".env") in report["files_found"]


def test_google_key_alias_is_normalized(monkeypatch, tmp_path):
    from engine.env_config import load_environment
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    (tmp_path / ".env").write_text("GOOGLE_API_KEY=google-test\n", encoding="utf-8")
    report = load_environment(tmp_path)
    assert os.environ["GEMINI_API_KEY"] == "google-test"
    assert "GOOGLE_API_KEY->GEMINI_API_KEY" in report["aliases_used"]


def test_empty_shell_variable_does_not_block_env(monkeypatch, tmp_path):
    from engine.env_config import load_environment
    monkeypatch.setenv("GEMINI_API_KEY", "")
    (tmp_path / ".env").write_text("GEMINI_API_KEY=valid-test\n", encoding="utf-8")
    report = load_environment(tmp_path)
    assert report["present"]["GEMINI_API_KEY"]
    assert os.environ["GEMINI_API_KEY"] == "valid-test"
