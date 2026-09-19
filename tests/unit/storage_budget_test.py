from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.operations.storage import StorageUnavailable, write_report


def test_low_space_refuses_render_and_does_not_create_directory(tmp_path):
    renderer = Mock()
    target = tmp_path / "new" / "report.pdf"
    with (
        patch("src.operations.storage.shutil.disk_usage", return_value=SimpleNamespace(free=109)),
        pytest.raises(StorageUnavailable, match="DISK_LOW"),
    ):
        write_report(str(target), renderer, minimum_free_bytes=100, maximum_bytes=10)
    renderer.assert_not_called()
    assert not target.parent.exists()


def test_report_limit_and_renderer_failure_leave_no_partial_file(tmp_path):
    def oversized(output):
        output.write(b"12345")
        output.write(b"678901")

    def broken(output):
        output.write(b"prefix")
        raise RuntimeError("fixture renderer failure")

    for renderer, exception in [(oversized, StorageUnavailable), (broken, RuntimeError)]:
        with pytest.raises(exception):
            write_report(str(tmp_path / "report.pdf"), renderer, minimum_free_bytes=0, maximum_bytes=10)
        assert list(tmp_path.iterdir()) == []


def test_complete_file_is_private_and_existing_destination_is_preserved(tmp_path):
    target = tmp_path / "report.pdf"
    write_report(str(target), lambda output: output.write(b"fixture"), minimum_free_bytes=0, maximum_bytes=10)
    assert target.read_bytes() == b"fixture"
    assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(StorageUnavailable, match="STORAGE_WRITE_FAILED"):
        write_report(str(target), lambda output: output.write(b"other"), minimum_free_bytes=0, maximum_bytes=10)
    assert target.read_bytes() == b"fixture"
    assert list(tmp_path.iterdir()) == [target]
    link = tmp_path / "link.pdf"
    link.symlink_to(target)
    with pytest.raises(StorageUnavailable, match="STORAGE_WRITE_FAILED"):
        write_report(str(link), lambda output: output.write(b"other"), minimum_free_bytes=0, maximum_bytes=10)
    assert Path(link).read_bytes() == b"fixture"
