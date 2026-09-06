"""
The pipeline, without Redshift or S3.

The original ``main.py`` ran the whole pipeline at import -- reproduced: an
``import main`` with a fake ``.env`` tried to connect to Redshift. There were
no tests, and nothing could have been tested.
"""

from __future__ import annotations

import ast
import os
import pathlib

import pandas as pd
import pytest

os.environ.setdefault("REDSHIFT_DB", "d")
os.environ.setdefault("REDSHIFT_HOST", "h")
os.environ.setdefault("REDSHIFT_USER", "u")
os.environ.setdefault("REDSHIFT_PASSWORD", "p")
os.environ.setdefault("S3_BUCKET", "test-bucket")

import main
from src.config import Settings
from src.extract import COLUMNS, rows_to_frame
from src.load import frame_to_csv_bytes, upload_frame, write_local
from src.transform import identify_and_remove_duplicated_data, remove_duplicates

ROOT = pathlib.Path(__file__).resolve().parents[1]


def frame(rows):
    return rows_to_frame(rows, COLUMNS)


ROW = ("536365", "85123A", "WHITE HANGING HEART", 2.55, 6, 15.3, "2010-12-01 08:26:00", "17850", "United Kingdom")


class FakeS3:
    def __init__(self):
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)


class TestImportHasNoSideEffects:
    def test_main_has_a_main_guard_and_no_top_level_pipeline_calls(self):
        """Every statement at module level is an import, a definition, or the __main__ guard."""
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.If):
                test = node.test
                assert isinstance(test, ast.Compare) and getattr(test.left, "id", "") == "__name__"
                continue
            assert isinstance(
                node,
                ast.Import | ast.ImportFrom | ast.FunctionDef | ast.ClassDef | ast.Assign | ast.Expr | ast.AnnAssign,
            ), ast.dump(node)[:80]
            if isinstance(node, ast.Expr):
                assert isinstance(node.value, ast.Constant), "a call at module level"
            if isinstance(node, ast.Assign):
                assert not isinstance(node.value, ast.Call) or getattr(node.value.func, "attr", "") == "getLogger"


class TestTransform:
    def test_exact_duplicates_are_removed_and_counted(self):
        result = remove_duplicates(frame([ROW, ROW, ROW]))
        assert result.rows_before == 3 and result.rows_after == 1 and result.removed == 2

    def test_nothing_to_remove(self):
        other = (*ROW[:1], "22423", *ROW[2:])
        result = remove_duplicates(frame([ROW, other]))
        assert result.removed == 0
        assert len(result.frame) == 2

    def test_the_index_is_reset(self):
        result = remove_duplicates(frame([ROW, ROW, (*ROW[:1], "x", *ROW[2:])]))
        assert list(result.frame.index) == [0, 1]

    def test_the_old_name_still_works(self):
        assert len(identify_and_remove_duplicated_data(frame([ROW, ROW]))) == 1

    def test_the_input_is_not_mutated(self):
        original = frame([ROW, ROW])
        remove_duplicates(original)
        assert len(original) == 2


class TestExtractShape:
    def test_invoice_date_becomes_a_datetime(self):
        assert pd.api.types.is_datetime64_any_dtype(frame([ROW])["invoice_date"])

    def test_columns_match_the_query(self):
        assert list(frame([ROW]).columns) == COLUMNS


class TestLoad:
    def test_upload_sends_csv_with_a_content_type(self):
        client = FakeS3()
        uri = upload_frame(frame([ROW]), "bucket", "path/file.csv", client)
        assert uri == "s3://bucket/path/file.csv"
        call = client.calls[0]
        assert call["Bucket"] == "bucket" and call["Key"] == "path/file.csv"
        assert call["ContentType"] == "text/csv"
        assert call["Body"].startswith(b"invoice,stock_code")

    def test_csv_has_no_index_column(self):
        text = frame_to_csv_bytes(frame([ROW])).decode()
        assert text.splitlines()[0] == ",".join(COLUMNS)

    def test_local_write_creates_parent_directories(self, tmp_path):
        target = write_local(frame([ROW]), tmp_path / "a" / "b" / "out.csv")
        assert target.exists()
        assert target.read_bytes().startswith(b"invoice,")


class TestRun:
    def test_dry_run_writes_locally_and_uploads_nothing(self, tmp_path):
        client = FakeS3()
        summary = main.run(
            Settings(_env_file=None, S3_BUCKET="b"),
            dry_run=True,
            output=str(tmp_path / "out.csv"),
            extract=lambda settings, limit=None: frame([ROW, ROW, ROW]),
            client_factory=lambda settings: client,
        )
        assert summary.rows_extracted == 3 and summary.duplicates_removed == 2 and summary.rows_loaded == 1
        assert summary.destination.endswith("out.csv")
        assert client.calls == []

    def test_a_live_run_uploads_to_the_configured_destination(self):
        client = FakeS3()
        summary = main.run(
            Settings(_env_file=None, S3_BUCKET="my-bucket", S3_KEY="etl/x.csv"),
            extract=lambda settings, limit=None: frame([ROW]),
            client_factory=lambda settings: client,
        )
        assert summary.destination == "s3://my-bucket/etl/x.csv"
        assert client.calls[0]["Bucket"] == "my-bucket"

    def test_the_limit_reaches_the_extractor(self):
        seen = {}

        def extract(settings, limit=None):
            seen["limit"] = limit
            return frame([ROW])

        main.run(Settings(_env_file=None, S3_BUCKET="b"), dry_run=True, limit=50, extract=extract, output="out/x.csv")
        assert seen["limit"] == 50


class TestCli:
    def test_missing_configuration_exits_78(self, monkeypatch):
        for name in ("REDSHIFT_DB", "REDSHIFT_HOST", "REDSHIFT_USER", "REDSHIFT_PASSWORD", "S3_BUCKET"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setattr(main, "Settings", lambda: Settings(_env_file=None))
        assert main.main([]) == 78

    def test_dry_run_does_not_need_a_bucket(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            main,
            "Settings",
            lambda: Settings(
                _env_file=None, REDSHIFT_DB="d", REDSHIFT_HOST="h", REDSHIFT_USER="u", REDSHIFT_PASSWORD="p"
            ),
        )
        monkeypatch.setattr(main, "extract_transaction_data", lambda settings, limit=None: frame([ROW]))
        assert main.main(["--dry-run", "--output", str(tmp_path / "o.csv")]) == 0

    def test_a_failing_extraction_exits_1_not_with_a_traceback(self, monkeypatch):
        def boom(settings, limit=None):
            raise ConnectionError("redshift unreachable")

        monkeypatch.setattr(
            main,
            "Settings",
            lambda: Settings(
                _env_file=None,
                REDSHIFT_DB="d",
                REDSHIFT_HOST="h",
                REDSHIFT_USER="u",
                REDSHIFT_PASSWORD="p",
                S3_BUCKET="b",
            ),
        )
        monkeypatch.setattr(main, "extract_transaction_data", boom)
        assert main.main([]) == 1


class TestSettings:
    def test_the_old_lowercase_names_are_accepted(self, monkeypatch):
        for name in ("REDSHIFT_DB", "REDSHIFT_HOST", "REDSHIFT_USER", "REDSHIFT_PASSWORD", "AWS_SECRET_ACCESS_KEY"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("dbname", "legacydb")
        monkeypatch.setenv("host", "legacyhost")
        monkeypatch.setenv("port", "5555")
        monkeypatch.setenv("aws_secret_access_key_id", "legacysecret")
        s = Settings(_env_file=None)
        assert s.REDSHIFT_DB == "legacydb" and s.REDSHIFT_HOST == "legacyhost" and s.REDSHIFT_PORT == 5555
        assert s.AWS_SECRET_ACCESS_KEY == "legacysecret"

    def test_problems_name_what_is_missing(self):
        problems = Settings(
            _env_file=None, REDSHIFT_DB="", REDSHIFT_HOST="", REDSHIFT_USER="", REDSHIFT_PASSWORD="", S3_BUCKET=""
        ).problems()
        assert any("S3_BUCKET" in p for p in problems)
        assert any("REDSHIFT_HOST" in p for p in problems)

    def test_no_destination_is_hardcoded(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8") + (ROOT / "src" / "load.py").read_text(encoding="utf-8")
        assert "waia-data-dump" not in source
        assert "daniellopez882" not in source

    @pytest.mark.parametrize("key_id,secret,expected", [("", "", False), ("a", "", False), ("a", "b", True)])
    def test_explicit_credentials_need_both_halves(self, key_id, secret, expected):
        assert (
            Settings(
                _env_file=None, AWS_ACCESS_KEY_ID=key_id, AWS_SECRET_ACCESS_KEY=secret
            ).has_explicit_aws_credentials
            is expected
        )
