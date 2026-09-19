import os
from datetime import UTC, datetime

import pytest

from src.operations.report_inventory import inventory_reports


def test_references_missing_files_and_interrupted_publication_are_distinct(tmp_path):
    retained = tmp_path / "report_owned.pdf"
    retained.write_bytes(b"retained")
    (tmp_path / "report_commit_failed.pdf").write_bytes(b"uncommitted")
    (tmp_path / ".report-interrupted").write_bytes(b"partial")
    (tmp_path / "unrelated.txt").write_bytes(b"other")
    result = inventory_reports(tmp_path, [str(retained), str(tmp_path / "report_missing.pdf")])
    assert result["status"] == "observed"
    assert result["missing_reference_count"] == 1
    assert sorted(item["category"] for item in result["files"]) == [
        "referenced", "unmanaged", "unreferenced", "unreferenced"
    ]
    assert result["deletion_authorized"] is False
    assert result["consistency"] == "non_atomic_observation"
    assert "report_owned" not in str(result)
    assert retained.read_bytes() == b"retained"
    assert len(list(tmp_path.iterdir())) == 4


def test_symlink_and_nested_directory_not_followed(tmp_path):
    outside = tmp_path / "nested"
    outside.mkdir()
    (outside / "private.pdf").write_bytes(b"private")
    (tmp_path / "report_link.pdf").symlink_to(outside / "private.pdf")
    result = inventory_reports(tmp_path, [str(tmp_path / "report_link.pdf")])
    assert result["reasons"] == ["NON_REGULAR_ENTRY"]
    assert result["files"] == []
    assert result["missing_reference_count"] is None
    link = tmp_path / "directory-link"
    link.symlink_to(outside, target_is_directory=True)
    assert inventory_reports(link, [])["reasons"] == ["STORAGE_INVENTORY_UNAVAILABLE"]


@pytest.mark.parametrize("limited", ["references", "files"])
def test_truncation_never_claims_complete_missing_references(tmp_path, limited):
    for index in range(3):
        (tmp_path / f"report_{index}.pdf").write_bytes(b"fixture")
    result = inventory_reports(
        tmp_path,
        (str(tmp_path / f"report_{index}.pdf") for index in range(3)),
        reference_limit=1 if limited == "references" else 10,
        file_limit=1 if limited == "files" else 10,
    )
    assert result["status"] == "partial"
    assert result["missing_reference_count"] is None
    assert len(result["files"]) <= (1 if limited == "files" else 10)
    assert result["deletion_authorized"] is False


def test_outside_reference_missing_root_and_clock_anomaly_fail_partial(tmp_path):
    assert inventory_reports(tmp_path, [str(tmp_path.parent / "outside.pdf")])["reasons"] == [
        "REFERENCE_OUTSIDE_ROOT"
    ]
    assert inventory_reports(tmp_path / "missing", [])["status"] == "partial"
    target = tmp_path / "report_future.pdf"
    target.write_bytes(b"fixture")
    os.utime(target, (2000000000, 2000000000))
    result = inventory_reports(tmp_path, [], now=datetime(2020, 1, 1, tzinfo=UTC))
    assert result["reasons"] == ["FILE_CLOCK_AHEAD"]
    assert result["files"][0]["age_seconds"] == 0
    with pytest.raises(ValueError, match="timezone"):
        inventory_reports(tmp_path, [], now=datetime(2020, 1, 1))
