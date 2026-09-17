from qqbot.util import load_dotenv


def test_parsing(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "# 注释\n"
        "DATABASE_URL=postgresql+asyncpg://u:p@h/db\n"
        "EMPTY=\n"
        "QUOTED=\"hello world\"\n"
        "NO_EQUALS_SIGN\n",
        encoding="utf-8",
    )
    values = load_dotenv(path)
    assert values["DATABASE_URL"] == "postgresql+asyncpg://u:p@h/db"
    assert values["EMPTY"] == ""
    assert values["QUOTED"] == "hello world"
    assert "NO_EQUALS_SIGN" not in values


def test_missing_file(tmp_path):
    assert load_dotenv(tmp_path / "nope.env") == {}
