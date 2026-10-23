#!/usr/bin/env python3
"""
sync-upstream.py - Sync upstream branch to fork branch

A general-purpose script for keeping a forked repository in sync with its
upstream source. Works with any git repository that has an upstream remote.

Usage:
    python sync-upstream.py                          # sync current branch from upstream
    python sync-upstream.py --branch main            # sync specific branch
    python sync-upstream.py --strategy rebase        # use rebase instead of merge
    python sync-upstream.py --dry-run                # preview what will happen
    python sync-upstream.py --upstream-url <url>     # set upstream remote url

Examples:
    python sync-upstream.py
    python sync-upstream.py --branch main --strategy rebase
    python sync-upstream.py --dry-run --branch develop
"""

import argparse
import subprocess
import sys
import os
from typing import Optional


def run_git(args: list[str], cwd: Optional[str] = None, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a git command and return the result."""
    cmd = ["git"] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return result
    except FileNotFoundError:
        print("[ERROR] git is not installed or not found in PATH.")
        sys.exit(1)


def git_output(args: list[str], cwd: Optional[str] = None) -> str:
    """Run a git command and return stdout stripped, or empty string on failure."""
    result = run_git(args, cwd=cwd, capture=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def git_success(args: list[str], cwd: Optional[str] = None) -> bool:
    """Run a git command and return True if it succeeded."""
    result = run_git(args, cwd=cwd, capture=True)
    return result.returncode == 0


def is_git_repo(path: str) -> bool:
    """Check if the given path is inside a git repository."""
    return git_success(["rev-parse", "--is-inside-work-tree"], cwd=path)


def get_current_branch(repo_path: str) -> str:
    """Get the current branch name."""
    return git_output(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)


def has_remote(remote_name: str, repo_path: str) -> bool:
    """Check if a remote exists."""
    result = run_git(["remote", "get-url", remote_name], cwd=repo_path, capture=True)
    return result.returncode == 0


def get_remote_url(remote_name: str, repo_path: str) -> str:
    """Get the URL of a remote."""
    return git_output(["remote", "get-url", remote_name], cwd=repo_path)


def has_branch(branch_name: str, repo_path: str) -> bool:
    """Check if a local branch exists."""
    result = run_git(
        ["rev-parse", "--verify", branch_name],
        cwd=repo_path,
        capture=True,
    )
    return result.returncode == 0


def fetch_remote(remote_name: str, repo_path: str) -> bool:
    """Fetch all branches from a remote. Returns True on success."""
    print(f"[INFO] Fetching from remote '{remote_name}'...")
    result = run_git(["fetch", remote_name], cwd=repo_path, capture=False)
    if result.returncode != 0:
        print(f"[ERROR] Failed to fetch from '{remote_name}'.")
        return False
    print(f"[INFO] Fetch from '{remote_name}' completed.")
    return True


def is_dirty(repo_path: str) -> bool:
    """Check if the working tree has uncommitted changes."""
    result = git_output(["status", "--porcelain"], cwd=repo_path)
    return bool(result)


def stash_changes(repo_path: str) -> bool:
    """Stash uncommitted changes. Returns True if stash was created."""
    if not is_dirty(repo_path):
        return False
    print("[INFO] Stashing uncommitted changes...")
    result = run_git(["stash", "push", "-m", "sync-upstream: auto stash before sync"], cwd=repo_path, capture=False)
    if result.returncode != 0:
        print("[ERROR] Failed to stash changes.")
        sys.exit(1)
    print("[INFO] Changes stashed.")
    return True


def pop_stash(repo_path: str) -> None:
    """Pop the most recent stash."""
    print("[INFO] Restoring stashed changes...")
    result = run_git(["stash", "pop"], cwd=repo_path, capture=False)
    if result.returncode != 0:
        print("[WARNING] Failed to pop stash. Your changes are still in the stash.")
        print("          Run 'git stash list' and 'git stash pop' manually to recover.")
    else:
        print("[INFO] Stashed changes restored.")


def merge_upstream(
    upstream: str,
    branch: str,
    repo_path: str,
    strategy: str,
    dry_run: bool,
) -> bool:
    """
    Merge or rebase upstream/branch into the current local branch.

    Returns True if sync was successful (or would be, in dry-run mode).
    """
    upstream_ref = f"{upstream}/{branch}"

    if not has_branch(branch, repo_path):
        print(f"[ERROR] Local branch '{branch}' does not exist.")
        return False

    print(f"[INFO] Target local branch: {branch}")
    print(f"[INFO] Upstream reference: {upstream_ref}")

    if dry_run:
        print("[DRY-RUN] Would checkout branch and perform sync.")
        print(f"[DRY-RUN] Sync strategy: {strategy}")
        return True

    current_branch = get_current_branch(repo_path)
    need_checkout = current_branch != branch

    if need_checkout:
        print(f"[INFO] Switching from '{current_branch}' to '{branch}'...")
        result = run_git(["checkout", branch], cwd=repo_path, capture=False)
        if result.returncode != 0:
            print(f"[ERROR] Failed to checkout branch '{branch}'.")
            return False

    if strategy == "rebase":
        print(f"[INFO] Rebasing '{branch}' onto '{upstream_ref}'...")
        result = run_git(["rebase", upstream_ref], cwd=repo_path, capture=False)
    else:
        print(f"[INFO] Merging '{upstream_ref}' into '{branch}'...")
        result = run_git(["merge", upstream_ref], cwd=repo_path, capture=False)

    if result.returncode != 0:
        print(f"[ERROR] {strategy.capitalize()} failed. You may need to resolve conflicts manually.")
        if strategy == "rebase":
            print("        Run 'git rebase --abort' to cancel, or resolve conflicts and run 'git rebase --continue'.")
        else:
            print("        Run 'git merge --abort' to cancel, or resolve conflicts and then commit.")
        return False

    print(f"[INFO] {strategy.capitalize()} completed successfully.")
    return True


def push_to_origin(branch: str, repo_path: str, force: bool, dry_run: bool) -> bool:
    """Push the synced branch to origin (the fork)."""
    if dry_run:
        print(f"[DRY-RUN] Would push '{branch}' to origin.")
        return True

    push_args = ["push", "origin", branch]
    if force:
        push_args.append("--force-with-lease")
        print("[WARNING] Using --force-with-lease for push.")

    print(f"[INFO] Pushing '{branch}' to origin...")
    result = run_git(push_args, cwd=repo_path, capture=False)
    if result.returncode != 0:
        print("[ERROR] Failed to push to origin.")
        return False

    print("[INFO] Push completed successfully.")
    return True


def add_upstream_remote(upstream_url: str, repo_path: str, remote_name: str = "upstream") -> bool:
    """Add an upstream remote if it doesn't already exist."""
    if has_remote(remote_name, repo_path):
        existing_url = get_remote_url(remote_name, repo_path)
        if existing_url != upstream_url:
            print(f"[WARNING] Remote '{remote_name}' already exists with URL: {existing_url}")
            print(f"          Requested URL: {upstream_url}")
            response = input("          Update the URL? [y/N]: ").strip().lower()
            if response == "y":
                print(f"[INFO] Updating remote '{remote_name}' URL...")
                result = run_git(
                    ["remote", "set-url", remote_name, upstream_url],
                    cwd=repo_path,
                    capture=False,
                )
                if result.returncode != 0:
                    print(f"[ERROR] Failed to update remote '{remote_name}' URL.")
                    return False
                print(f"[INFO] Remote '{remote_name}' URL updated.")
        else:
            print(f"[INFO] Remote '{remote_name}' already exists: {existing_url}")
        return True

    print(f"[INFO] Adding remote '{remote_name}' -> {upstream_url}")
    result = run_git(["remote", "add", remote_name, upstream_url], cwd=repo_path, capture=False)
    if result.returncode != 0:
        print(f"[ERROR] Failed to add remote '{remote_name}'.")
        return False
    print(f"[INFO] Remote '{remote_name}' added.")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Sync upstream branch to fork branch in a git repository.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s
  %(prog)s --branch main --strategy rebase
  %(prog)s --dry-run --branch develop
  %(prog)s --upstream-url https://github.com/original/repo.git
  %(prog)s --repo /path/to/repo --branch main
        """,
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Path to the git repository (default: current directory).",
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="Branch name to sync (default: current branch).",
    )
    parser.add_argument(
        "--upstream",
        default="upstream",
        help="Name of the upstream remote (default: upstream).",
    )
    parser.add_argument(
        "--upstream-url",
        default=None,
        help="URL of the upstream repository. If provided, the upstream remote will be added/updated.",
    )
    parser.add_argument(
        "--strategy",
        choices=["merge", "rebase"],
        default="merge",
        help="Sync strategy: merge (default) or rebase.",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        default=True,
        help="Push the synced branch to origin after sync (default: enabled).",
    )
    parser.add_argument(
        "--no-push",
        action="store_false",
        dest="push",
        help="Do not push to origin after sync.",
    )
    parser.add_argument(
        "--force-push",
        action="store_true",
        default=False,
        help="Use --force-with-lease when pushing (use with caution).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview actions without making any changes.",
    )
    parser.add_argument(
        "--no-stash",
        action="store_true",
        default=False,
        help="Do not auto-stash uncommitted changes (script will abort if dirty).",
    )

    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo)
    if not os.path.isdir(repo_path):
        print(f"[ERROR] Repository path does not exist: {repo_path}")
        sys.exit(1)

    if not is_git_repo(repo_path):
        print(f"[ERROR] Not a git repository: {repo_path}")
        sys.exit(1)

    print("=" * 60)
    print("  Sync Upstream → Fork")
    print("=" * 60)
    print(f"  Repository : {repo_path}")
    if args.dry_run:
        print("  Mode       : DRY-RUN (no changes will be made)")
    print("-" * 60)

    branch = args.branch or get_current_branch(repo_path)
    if not branch:
        print("[ERROR] Could not determine the current branch and --branch was not specified.")
        sys.exit(1)
    print(f"[INFO] Target branch: {branch}")

    if args.upstream_url:
        if not add_upstream_remote(args.upstream_url, repo_path, args.upstream):
            sys.exit(1)

    if not has_remote(args.upstream, repo_path):
        print(f"[ERROR] Upstream remote '{args.upstream}' does not exist.")
        print(f"        Use --upstream-url to add it, or set it up manually:")
        print(f"        git remote add {args.upstream} <upstream-repo-url>")
        sys.exit(1)

    upstream_url = get_remote_url(args.upstream, repo_path)
    print(f"[INFO] Upstream remote: {args.upstream} -> {upstream_url}")

    if not fetch_remote(args.upstream, repo_path):
        sys.exit(1)

    if is_dirty(repo_path) and not args.dry_run:
        if args.no_stash:
            print("[ERROR] Working tree has uncommitted changes.")
            print("        Commit or stash them first, or remove --no-stash to auto-stash.")
            sys.exit(1)
        stash_created = stash_changes(repo_path)
    else:
        stash_created = False

    try:
        if not merge_upstream(args.upstream, branch, repo_path, args.strategy, args.dry_run):
            sys.exit(1)

        if args.push:
            if not push_to_origin(branch, repo_path, args.force_push, args.dry_run):
                sys.exit(1)
    finally:
        if stash_created and not args.dry_run:
            pop_stash(repo_path)

    print()
    print("=" * 60)
    if args.dry_run:
        print("  DRY-RUN completed. No changes were made.")
    else:
        print("  Sync completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()