#!/usr/bin/env python3
"""Update bucket/flutter-ohos-341.json from the CPF-Flutter GitCode releases.

This package has no downloadable artifact: the installer clones the SDK into the
persist dir and checks out the release tag, so the only thing an update rewrites
is `version`. There is no `url` expansion and no hash to compute.

Two details make the generic updater unfit for this package:

* Upstream tags the same 3.41 line in two shapes -- `3.41.9+ohos-1.0.2` and
  `3.41.10-ohos-1.0.0` -- on separate maintenance branches, so the highest
  number is not the newest release. "Newest" here means newest `created_at`,
  which is what the manifest's original PowerShell checkver did.
* Upstream only sets the release `prerelease` flag on some tags, so `-beta`,
  `-canary`, `-pre`, `-rc` have to be filtered out by name.

The current version's base number acts as a floor: the script never moves the
package to an older Flutter base, so a branch that lags behind cannot drag it
back down.

Usage:
    python3 scripts/flutter-ohos-341.py            # check and write
    python3 scripts/flutter-ohos-341.py --dry-run  # report only
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "bucket", "flutter-ohos-341.json")
API = "https://gitcode.com/api/v5/repos/CPF-Flutter/flutter_flutter/releases?per_page=100"
UA = "scoop-third-party-updater/1.0 (+https://gitcode.com/NamaeResu/scoop-third-party)"
LINE = "3.41"
PRERELEASE = re.compile(r"(?i)(?:^|[-._+])(?:alpha|beta|rc|canary|pre|preview|dev|nightly|snapshot)\d*(?:$|[-._+])")
BASE = re.compile(r"^v?(\d+\.\d+(?:\.\d+)?)")


# --------------------------------------------------------------------------- net
def fetch_text(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


# ------------------------------------------------------------------- detection
def base_of(tag: str) -> tuple[int, ...] | None:
    """`3.41.9+ohos-1.0.2` -> (3, 41, 9); the part that must keep moving forward."""
    m = BASE.match(tag or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def is_this_line(tag: str) -> bool:
    b = base_of(tag)
    return b is not None and f"{b[0]}.{b[1]}" == LINE


def is_stable(rel: dict) -> bool:
    """Upstream flags only some prereleases, so the tag name has the final say."""
    tag = rel.get("tag_name") or ""
    return not rel.get("prerelease") and not PRERELEASE.search(tag)


def created(rel: dict) -> str:
    return rel.get("created_at") or rel.get("released_at") or ""


def candidates() -> list[dict]:
    releases = json.loads(fetch_text(API))
    found = [r for r in releases if is_this_line(r.get("tag_name") or "") and is_stable(r)]
    if not found:
        raise SystemExit(f"no stable {LINE} release found at {API}")
    return sorted(found, key=created, reverse=True)


# ------------------------------------------------------------------------ main
def update(dry_run: bool) -> bool:
    with open(MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)

    current = manifest.get("version", "0")
    floor = base_of(current)

    eligible = [r for r in candidates() if floor is None or (base_of(r["tag_name"]) or (0,)) >= floor]
    if not eligible:
        print(f"  flutter-ohos-341: {current} (up to date)")
        return False

    latest = eligible[0]
    new = latest["tag_name"]
    if new == current:
        print(f"  flutter-ohos-341: {current} (up to date)")
        return False

    print(f"  flutter-ohos-341: {current} -> {new} (released {created(latest)[:10]})")
    manifest["version"] = new

    if dry_run:
        print(f"    (dry-run) would write {MANIFEST}")
        return True

    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, indent=4, ensure_ascii=False)
        fh.write("\n")
    print(f"    wrote {MANIFEST}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(MANIFEST):
        print(f"manifest not found: {MANIFEST}", file=sys.stderr)
        return 1
    try:
        update(args.dry_run)
    except urllib.error.URLError as exc:
        print(f"  flutter-ohos-341: network error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
