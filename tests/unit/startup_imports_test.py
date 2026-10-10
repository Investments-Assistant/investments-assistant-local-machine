"""Service recovery must not wait for unused market-data analysis libraries."""

import sys
import subprocess


def test_service_import_does_not_load_market_data_stack():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import src.app; assert not {'pandas', 'yfinance', 'ta'} & sys.modules.keys()",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
