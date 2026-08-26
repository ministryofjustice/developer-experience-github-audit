from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from core.github_client import GitHubHttpClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Print installation details and permissions for a GitHub App "
            "installed in an organisation. Pass an app_slug to check one "
            "app, or --all to check every installed app."
        )
    )
    parser.add_argument(
        "app_slug",
        nargs="?",
        default=None,
        help="GitHub App slug to look up, for example: slack",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Print permissions for every installed app instead of one",
    )
    parser.add_argument(
        "--output",
        help=(
            "Path to write --all results as CSV, for example: "
            "outputs/check_app_permissions/2026-08-25.csv. "
            "Only used with --all; ignored for single app_slug lookups."
        ),
    )
    parser.add_argument(
        "--org",
        default="ministryofjustice",
        help="GitHub organization name (default: ministryofjustice)",
    )
    parser.add_argument(
        "--auth",
        choices=["pat", "app", "cli"],
        help="Authentication method for GitHub API (default: auto)",
    )
    args = parser.parse_args()

    if args.all and args.app_slug:
        parser.error("app_slug and --all are mutually exclusive")
    if not args.all and not args.app_slug:
        parser.error("provide an app_slug, or use --all to check every app")

    return args


def fetch_installations(client: GitHubHttpClient, org: str) -> list[dict[str, Any]]:
    """Return all GitHub App installations for an organisation."""
    try:
        installations = client.get_paginated(
            f"/orgs/{org}/installations", items_key="installations"
        )
    except Exception as exc:
        print(f"Failed to fetch installations for {org}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    return [item for item in installations if isinstance(item, dict)]


def find_installation(
    installations: list[dict[str, Any]], app_slug: str
) -> dict[str, Any] | None:
    """Return the installation matching app_slug (case-insensitive), or None."""
    target = app_slug.strip().lower()
    for installation in installations:
        if (installation.get("app_slug") or "").lower() == target:
            return installation
    return None


def print_single_app(installation: dict[str, Any]) -> None:
    """Print full raw response plus a quick field summary for one app."""
    print(f"=== Full raw response for '{installation.get('app_slug')}' ===\n")
    print(json.dumps(installation, indent=2))

    print("\n=== Quick field check ===")
    print(f"app_slug: {installation.get('app_slug')}")
    print(f"installation_id: {installation.get('id')}")
    print(f"repository_selection: {installation.get('repository_selection')}")
    print("permissions:")
    print(json.dumps(installation.get("permissions", {}), indent=2))


def print_all_apps(installations: list[dict[str, Any]]) -> None:
    """Print a summary block per installed app."""
    print(f"Installed apps ({len(installations)}):\n")
    for installation in installations:
        permissions = installation.get("permissions") or {}
        print(f"app_slug: {installation.get('app_slug')}")
        print(f"installation_id: {installation.get('id')}")
        print(f"repository_selection: {installation.get('repository_selection')}")
        if not permissions:
            print("permissions: none reported")
        else:
            print(f"permissions ({len(permissions)}):")
            for name in sorted(permissions):
                print(f"  {name}: {permissions[name]}")
        print()


def write_all_apps_csv(installations: list[dict[str, Any]], output_path: str) -> None:
    """Write --all results as real CSV rows, one app per row.

    Permissions are flattened to a single "scope: level, ..." string per
    row, matching the flattening already used in
    core/presenters.py::build_org_webhook_rows.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["app_slug", "installation_id", "repository_selection", "permissions"]

    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for installation in installations:
            permissions = installation.get("permissions") or {}
            writer.writerow(
                {
                    "app_slug": installation.get("app_slug"),
                    "installation_id": installation.get("id"),
                    "repository_selection": installation.get("repository_selection"),
                    "permissions": ", ".join(
                        f"{scope}:{level}"
                        for scope, level in sorted(permissions.items())
                    ),
                }
            )

    print(f"Wrote {len(installations)} app(s) to {path}")


def print_not_found(
    installations: list[dict[str, Any]], app_slug: str, org: str
) -> None:
    """Print a clear not-found message with the available app slugs."""
    print(f"No GitHub App with slug '{app_slug}' is installed in {org}.")
    slugs = sorted(
        installation.get("app_slug")
        for installation in installations
        if installation.get("app_slug")
    )
    print(f"Installed apps in {org} ({len(slugs)}):")
    for slug in slugs:
        print(f"- {slug}")


def main() -> None:
    args = parse_args()

    client = GitHubHttpClient(auth_method=args.auth)
    installations = fetch_installations(client, args.org)

    if not installations:
        print(f"No GitHub App installations returned for {args.org}.")
        return

    if args.all:
        if args.output:
            write_all_apps_csv(installations, args.output)
        else:
            print_all_apps(installations)
        return

    installation = find_installation(installations, args.app_slug)
    if installation is None:
        print_not_found(installations, args.app_slug, args.org)
        raise SystemExit(1)

    print_single_app(installation)


if __name__ == "__main__":
    main()
