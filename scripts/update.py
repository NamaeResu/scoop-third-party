#!/usr/bin/env python3
"""Detect upstream versions for every manifest in ./bucket and rewrite version/url/hash.

Standard library only, no Windows/Scoop dependency, so it runs on any Linux runner.
Reads the same `checkver` / `autoupdate` blocks a normal Scoop manifest uses, so
manifests stay valid for `scoop install` and for `scoop update`.

Supported checkver forms:
    {"github": "https://github.com/<owner>/<repo>"}     GitHub API, falls back to the atom feed
    {"url": "...", "regex": "..."}                       plain page + regex (group 1 = version)

Supported autoupdate forms:
    {"architecture": {"64bit": {"url": "..."}}, "hash": {"url": "$baseurl/SHA256SUMS"}}
    {"url": "...", "hash": {"url": "...", "regex": "..."}}
    missing/plain hash  -> artifact is downloaded and its sha256 computed

Usage:
    python3 scripts/update.py                 # check and write
    python3 scripts/update.py --dry-run       # report only
    python3 scripts/update.py --app aoci      # one manifest
    python3 scripts/update.py --token $GH_TOKEN
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUCKET = os.path.join(ROOT, "bucket")
UA = "scoop-third-party-updater/1.0 (+https://gitcode.com/NamaeResu/scoop-third-party)"
TOKEN = ""


# --------------------------------------------------------------------------- net
def fetch(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    if TOKEN and "api.github.com" in url:
        req.add_header("Authorization", "Bearer " + TOKEN)
    if TOKEN and "api.github.com" in url:
        req.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_text(url: str, timeout: int = 60) -> str:
    return fetch(url, timeout).decode("utf-8", "replace")


# ----------------------------------------------------------------------- version
def _pre_key(pre: str):
    """Natural, numeric-aware ordering for prerelease tags: rc2 < rc10, alpha < beta < rc."""
    parts = re.findall(r"\d+|\D+", pre.lower())
    key = []
    for p in parts:
        key.append((0, int(p), "") if p.isdigit() else (1, 0, p))
    return key


def version_key(version: str):
    """Sortable key. A release outranks its own prereleases (0.2.0 > 0.2.0-rc2)."""
    m = re.match(r"^[vV]?(\d+(?:[._]\d+)*)(?:[-._+~]?(.*))?$", version.strip())
    if not m:
        return ((0,), (1,), ())
    nums = tuple(int(x) for x in re.split(r"[._]", m.group(1)))
    pre = (m.group(2) or "").strip("-_+~")
    # pad so 1.2 == 1.2.0
    nums = nums + (0,) * (8 - len(nums))
    # prereleases get 0, bare releases get 1, so 0.2.0 outranks 0.2.0-rc2
    return (nums, (0,) if pre else (1,), _pre_key(pre))


def is_newer(candidate: str, current: str) -> bool:
    return version_key(candidate) > version_key(current)


# ------------------------------------------------------------------- detection
def detect_github(repo: str):
    """Latest release tag from the GitHub API; falls back to the atom feed (includes prereleases)."""
    repo = repo.rstrip("/")
    m = re.search(r"github\.com/([^/]+)/([^/#?]+)", repo)
    if not m:
        raise SystemExit(f"cannot parse github repo: {repo}")
    owner, name = m.group(1), m.group(2).removesuffix(".git")

    api = f"https://api.github.com/repos/{owner}/{name}/releases?per_page=10"
    try:
        for rel in json.loads(fetch(api)):
            if rel.get("draft"):
                continue
            tag = (rel.get("tag_name") or "").lstrip("vV")
            if tag:
                return tag
    except (urllib.error.HTTPError, json.JSONDecodeError, OSError) as exc:
        print(f"    github api unavailable ({exc}); falling back to releases.atom", file=sys.stderr)

    atom = fetch_text(f"https://github.com/{owner}/{name}/releases.atom")
    tags = re.findall(r"/releases/tag/([^\"'<]+)", atom)
    if not tags:
        raise SystemExit(f"no release tags found for {owner}/{name}")
    return tags[0].lstrip("vV")


def detect(app: str, manifest: dict) -> str | None:
    cv = manifest.get("checkver")
    if isinstance(cv, str):
        cv = {"github": cv}
    if not cv:
        print(f"  {app}: no checkver, skipped")
        return None

    if cv.get("github"):
        version = detect_github(cv["github"])
    elif cv.get("url"):
        text = fetch_text(cv["url"])
        pattern = cv.get("regex")
        if not pattern:
            raise SystemExit(f"{app}: checkver.url without regex")
        m = re.search(pattern, text, re.MULTILINE)
        if not m:
            print(f"  {app}: regex did not match {cv['url']}")
            return None
        version = m.group(1)
    else:
        raise SystemExit(f"{app}: checkver needs 'github' or 'url'+'regex'")

    # {"replace": {"^v": ""}} or {"replace": ["^v"]} — same shapes Scoop accepts
    replace = cv.get("replace")
    if isinstance(replace, dict):
        for pattern, repl in replace.items():
            version = re.sub(pattern, repl, version)
    elif isinstance(replace, list):
        for pattern in replace:
            version = re.sub(pattern, "", version)
    return version.strip()


# ------------------------------------------------------------------ substitutes
def substitutions(version: str) -> dict[str, str]:
    head = version.split("-")[0]
    tail = version.split("-")[-1]
    parts = head.split(".")
    subs = {
        "$version": version,
        "$dotVersion": re.sub(r"[._-]", ".", version),
        "$underscoreVersion": re.sub(r"[._-]", "_", version),
        "$dashVersion": re.sub(r"[._-]", "-", version),
        "$cleanVersion": re.sub(r"[._-]", "", version),
        "$majorVersion": parts[0] if parts else "",
        "$minorVersion": parts[1] if len(parts) > 1 else "",
        "$patchVersion": parts[2] if len(parts) > 2 else "",
        "$buildVersion": parts[3] if len(parts) > 3 else "",
        "$preReleaseVersion": tail,
    }
    m = re.match(r"^(\d+\.\d+(?:\.\d+)?)(.*)$", version)
    if m:
        subs["$matchHead"] = m.group(1)
        subs["$matchTail"] = m.group(2)
    return subs


def substitute(template: str, subs: dict[str, str]) -> str:
    out = template
    for key in sorted(subs, key=len, reverse=True):
        out = out.replace(key, subs[key])
    return out


def baseurl(url: str) -> str:
    return url.rsplit("/", 1)[0] if "/" in url else url


# ------------------------------------------------------------------------ hash
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_from_checksum(url: str, artifact_url: str) -> str | None:
    """Extract the artifact's digest out of a checksum file (SHA256SUMS, *.sha256, ...)."""
    body = fetch_text(url)
    name = artifact_url.rsplit("/", 1)[-1]
    for line in body.splitlines():
        if name in line:
            m = re.search(r"\b([a-fA-F0-9]{64})\b", line)
            if m:
                return m.group(1).lower()
    m = re.search(r"\b([a-fA-F0-9]{64})\b", body)
    return m.group(1).lower() if m else None


def resolve_hash(spec, artifact_url: str, subs: dict[str, str] | None = None) -> str | None:
    """spec is the manifest `hash` value (string) or an autoupdate hash object."""
    if isinstance(spec, str) and len(spec) == 64:
        return spec.lower()
    if isinstance(spec, dict) and spec.get("url"):
        url = spec["url"]
        if subs:
            expanded = dict(subs)
            expanded["$baseurl"] = baseurl(artifact_url)
            url = substitute(url, expanded)
        if spec.get("regex"):
            body = fetch_text(url)
            m = re.search(spec["regex"], body, re.MULTILINE)
            if m:
                return m.group(1).lower()
            return None
        found = hash_from_checksum(url, artifact_url)
        if found:
            return found
        print(f"    checksum file did not list {artifact_url.rsplit('/', 1)[-1]}, downloading artifact", file=sys.stderr)
    print(f"    downloading {artifact_url}", file=sys.stderr)
    return sha256_bytes(fetch(artifact_url, timeout=300))


# ------------------------------------------------------------------------ main
def update_one(path: str, dry_run: bool) -> tuple[str, str, str] | None:
    app = os.path.splitext(os.path.basename(path))[0]
    with open(path, encoding="utf-8") as fh:
        manifest = json.load(fh)

    current = manifest.get("version", "0")
    latest = detect(app, manifest)
    if not latest:
        return None
    if not is_newer(latest, current):
        print(f"  {app}: {current} (up to date)")
        return None

    print(f"  {app}: {current} -> {latest}")
    auto = manifest.get("autoupdate")
    if not auto:
        print(f"    no autoupdate block, cannot rewrite url/hash", file=sys.stderr)
        return None

    subs = substitutions(latest)

    def apply(entry: dict, url_template: str):
        new_url = substitute(url_template, subs)
        hash_spec = entry.get("hash")
        new_hash = resolve_hash(hash_spec, new_url, subs) if hash_spec is not None else None
        if new_hash is None:
            new_hash = resolve_hash(auto.get("hash"), new_url, subs)
        if new_hash is None:
            raise SystemExit(f"{app}: could not determine hash for {new_url}")
        return new_url, new_hash

    if "architecture" in auto:
        for arch, entry in auto["architecture"].items():
            if not entry.get("url"):
                continue
            if arch not in manifest.get("architecture", {}):
                continue
            new_url, new_hash = apply(entry, entry["url"])
            target = manifest["architecture"][arch]
            if "url" in target:
                target["url"] = new_url
            if "hash" in target:
                target["hash"] = new_hash
    else:
        new_url, new_hash = apply(auto, auto["url"])
        if "url" in manifest:
            manifest["url"] = new_url
        if "hash" in manifest:
            manifest["hash"] = new_hash

    manifest["version"] = latest

    if dry_run:
        print(f"    (dry-run) would write {path}")
        return (app, current, latest)

    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, indent=4, ensure_ascii=False)
        fh.write("\n")
    print(f"    wrote {path}")
    return (app, current, latest)


def main() -> int:
    global TOKEN
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", default="*", help="only this manifest (file stem)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--token", default=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "")
    args = ap.parse_args()
    TOKEN = args.token

    if not os.path.isdir(BUCKET):
        print(f"bucket directory not found: {BUCKET}", file=sys.stderr)
        return 1

    names = sorted(f for f in os.listdir(BUCKET) if f.endswith(".json"))
    if args.app != "*":
        wanted = {args.app if args.app.endswith(".json") else args.app + ".json"}
        names = [n for n in names if n in wanted]
        if not names:
            print(f"no manifest named {args.app} in {BUCKET}", file=sys.stderr)
            return 1

    print(f"checking {len(names)} manifest(s) in {BUCKET}")
    changed = []
    for name in names:
        if name.startswith("."):
            continue
        try:
            result = update_one(os.path.join(BUCKET, name), args.dry_run)
        except urllib.error.URLError as exc:
            print(f"  {name}: network error: {exc}", file=sys.stderr)
            continue
        if result:
            changed.append(result)

    if not changed:
        print("no updates found")
        return 0

    print(f"\n{len(changed)} update(s):")
    for app, old, new in changed:
        print(f"  {app}: {old} -> {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
