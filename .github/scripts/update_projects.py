#!/usr/bin/env python3
"""Regenerate the Projects block of README.md.

Lists the public repositories owned by GH_USER that carry the PROJECT_TOPIC
topic, sorts them by stars, and rewrites everything between
``<!-- PROJECTS START -->`` and ``<!-- PROJECTS END -->``.

Only ``/users/<login>/repos?type=owner`` is queried, so repositories from other
namespaces (organisation or collaborator repos) can never leak in, and
renamed-repository redirects cannot produce duplicate entries.

Configuration (environment variables):
  GH_USER           GitHub login to list                    (default: iphysresearch)
  GITHUB_TOKEN      token, only needed for a higher rate limit (optional)
  PROJECT_TOPIC     topic that marks a repository as a project (default: project)
  MAX_REPOS         maximum number of entries                (default: 30)
  MAX_DESC          description length before truncation    (default: 60)
  INCLUDE_FORKS     true/false                              (default: true)
  INCLUDE_ARCHIVED  true/false                              (default: true)
  README_PATH       file to rewrite                         (default: README.md)
"""

import json
import os
import re
import sys
import urllib.request

API = "https://api.github.com"
START = "<!-- PROJECTS START -->"
END = "<!-- PROJECTS END -->"


def env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes")


USER = os.environ.get("GH_USER", "iphysresearch").strip()
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
TOPIC = os.environ.get("PROJECT_TOPIC", "project").strip()
MAX_REPOS = int(os.environ.get("MAX_REPOS", "30"))
MAX_DESC = int(os.environ.get("MAX_DESC", "60"))
INCLUDE_FORKS = env_bool("INCLUDE_FORKS", True)
INCLUDE_ARCHIVED = env_bool("INCLUDE_ARCHIVED", True)
README = os.environ.get("README_PATH", "README.md")


def get_json(url: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USER}-readme-projects",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp), resp.headers.get("Link", "")


def owned_repos():
    """Yield every public repository owned by USER (follows pagination)."""
    url = f"{API}/users/{USER}/repos?type=owner&per_page=100"
    while url:
        page, link = get_json(url)
        yield from page
        match = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = match.group(1) if match else None


def wanted(repo: dict) -> bool:
    if TOPIC not in (repo.get("topics") or []):
        return False
    if repo.get("fork") and not INCLUDE_FORKS:
        return False
    if repo.get("archived") and not INCLUDE_ARCHIVED:
        return False
    return True


def format_entry(repo: dict) -> str:
    desc = (repo.get("description") or "").strip()
    if len(desc) > MAX_DESC:
        desc = desc[:MAX_DESC].rstrip() + "..."
    entry = (
        f"* [{repo['name']}]({repo['html_url']}) "
        f"**{repo['stargazers_count']}⭐, {repo['forks_count']}** forks"
    )
    if desc:
        entry += f" ({desc})"
    if repo.get("archived"):
        entry += " _(archived)_"
    return entry


def main() -> int:
    # Key by full_name so one repository can only ever appear once.
    repos = {r["full_name"]: r for r in owned_repos() if wanted(r)}
    ordered = sorted(
        repos.values(),
        key=lambda r: (-r["stargazers_count"], -r["forks_count"], r["name"].lower()),
    )[:MAX_REPOS]

    block = "\n".join([START, *(format_entry(r) for r in ordered), END])

    with open(README, encoding="utf-8") as fh:
        original = fh.read()

    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    updated, count = pattern.subn(lambda _: block, original, count=1)
    if count == 0:
        print(f"error: markers {START!r} / {END!r} not found in {README}", file=sys.stderr)
        return 1

    print(f"{len(repos)} repositories carry topic '{TOPIC}'; listing {len(ordered)} (max {MAX_REPOS}):")
    for repo in ordered:
        print(f"  {repo['stargazers_count']:>5}⭐  {repo['name']}")

    if updated == original:
        print("No change to README.")
        return 0

    with open(README, "w", encoding="utf-8") as fh:
        fh.write(updated)
    print("README updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
