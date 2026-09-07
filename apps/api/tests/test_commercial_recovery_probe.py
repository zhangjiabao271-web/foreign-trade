import copy
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import commercial_recovery_probe as probe  # noqa: E402
from commercial_recovery_probe import canonical_check, database_url, difference_paths  # noqa: E402


def test_probe_only_uses_named_isolated_targets():
    assert "127.0.0.1:25432/trade_workbench_e2e" in database_url("source")
    assert "127.0.0.1:25433/trade_workbench_e2e" in database_url("restored")
    with pytest.raises(ValueError):
        database_url("production")


def test_difference_paths_report_changed_values_and_missing_fields():
    assert difference_paths({"a": [1, 2], "b": True}, {"a": [1, 3]}) == ["root.a[1]", "root.b"]
    assert difference_paths([1], []) == ["root.length"]
    assert difference_paths({"a": 1}, {"a": 1}) == []


@pytest.mark.integration
def test_postgres_reparse_preserves_constraint_meaning_and_leaves_no_schema(test_database_url):
    engine = create_engine(test_database_url)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE sample (status varchar(40) NOT NULL)")
    before = (
        "CHECK (((status)::text = ANY ((ARRAY['PENDING'::character varying, "
        "'DONE'::character varying])::text[])))"
    )
    after = (
        "CHECK (((status)::text = ANY (ARRAY[('PENDING'::character varying)::text, "
        "('DONE'::character varying)::text])))"
    )
    with engine.connect() as connection:
        assert canonical_check(connection, "sample", before) == canonical_check(
            connection, "sample", after
        )
        assert canonical_check(
            connection, "sample", after.replace("DONE", "APPROVED")
        ) != canonical_check(connection, "sample", before)
        with pytest.raises(ValueError):
            canonical_check(connection, "sample", "CHECK (TRUE); DROP TABLE sample")
    with engine.connect() as connection:
        assert inspect(connection).get_table_names(schema="public") == ["sample"]
        assert not connection.exec_driver_sql(
            "SELECT count(*) FROM pg_class WHERE starts_with(relname, 'recovery_check_')"
        ).scalar_one()
    engine.dispose()


@pytest.mark.integration
def test_manifest_comparison_rejects_changes_and_preserves_original(test_database_url, monkeypatch):
    engine = create_engine(test_database_url)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE sample (status varchar(40) NOT NULL)")
    monkeypatch.setattr(probe, "database_url", lambda target: test_database_url)
    expected = {
        "database": {
            "schema": {"constraints": [["sample", "status_check", "c", True, "CHECK (TRUE)"]]},
            "tables": {"sample": {"rows": 1, "sha256": "original"}},
        }
    }
    original = copy.deepcopy(expected)
    assert probe.compare_manifests(expected, copy.deepcopy(expected)) == []
    changed = copy.deepcopy(expected)
    changed["database"]["schema"]["constraints"][0][4] = "CHECK (FALSE)"
    with pytest.raises(RuntimeError, match="Restore differs"):
        probe.compare_manifests(expected, changed)
    changed = copy.deepcopy(expected)
    changed["database"]["tables"]["sample"]["sha256"] = "altered"
    with pytest.raises(RuntimeError, match="sha256"):
        probe.compare_manifests(expected, changed)
    assert expected == original
    engine.dispose()
