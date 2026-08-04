from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest

from cleantech_finance import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_source_package_versions_are_aligned() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', pyproject, flags=re.MULTILINE)

    assert match is not None
    assert match.group(1) == __version__ == "0.5.0"


def test_installed_distribution_metadata_matches_runtime_when_available() -> None:
    try:
        installed = version("cleantech-finance")
    except PackageNotFoundError:
        pytest.skip("distribution metadata is unavailable in this source-only test run")

    assert installed == __version__
