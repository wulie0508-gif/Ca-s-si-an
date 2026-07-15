"""Download public demo filings into the git-ignored .cache directory."""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import urllib.request
from pathlib import Path

CASES = {
    "sungrow": {
        "url": "https://static.cninfo.com.cn/finalpage/2026-06-08/1225358186.PDF",
        "path": ".cache/sungrow/sungrow-2025-annual-report-en-abridged.pdf",
        "sha256": "99fafd6ddceb5d64a4ce15a18d4addddebe2badcc68c8ba7acd5c91146c0d3fc",
    },
    "enphase": {
        "url": "https://www.sec.gov/Archives/edgar/data/1463101/000146310126000030/annualreport2025.pdf",
        "path": ".cache/enphase/enphase-2025-annual-report.pdf",
        "sha256": "a2d95a0e48be5621e2f3e37e78c7812982f9fb4cb745aee0b3d336f610bf7fc3",
        "user_agent_env": "SEC_USER_AGENT",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(case: str, force: bool = False) -> Path:
    item = CASES[case]
    destination = Path(item["path"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        actual = sha256(destination)
        if actual == item["sha256"]:
            print(f"Already verified: {destination}")
            return destination
        raise RuntimeError(f"Existing file has unexpected SHA-256: {destination}")

    temporary = destination.with_suffix(destination.suffix + ".part")
    user_agent = "cleantech-finance/0.2 public-research-demo"
    if environment_name := item.get("user_agent_env"):
        user_agent = os.environ.get(environment_name, "").strip()
        if not user_agent:
            raise RuntimeError(
                f"Set {environment_name} to a truthful SEC user agent, for example "
                "'Your Name your-email@example.com'. Do not commit personal contact details."
            )
    request = urllib.request.Request(item["url"], headers={"User-Agent": user_agent})
    try:
        with (
            urllib.request.urlopen(request, timeout=90) as response,
            temporary.open("wb") as output,
        ):
            while block := response.read(1024 * 1024):
                output.write(block)
        actual = sha256(temporary)
        if actual != item["sha256"]:
            raise RuntimeError(f"Checksum mismatch: expected {item['sha256']}, got {actual}")
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(f"Downloaded and verified: {destination}")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", choices=sorted(CASES))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        download(args.case, args.force)
    except (OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
