from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_REPO_URL = "https://github.com/Merrick1307/identity-access-management-system.git"


def run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=str(cwd) if cwd else None, check=True)


def copy_if_missing(source: Path, target: Path) -> None:
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clone or refresh HexIAM into .hexiam/hexalgon-iam-system for the bundled self-host stack.",
    )
    parser.add_argument(
        "--source",
        default=DEFAULT_REPO_URL,
        help="Git remote URL or local repository path to clone from.",
    )
    parser.add_argument(
        "--ref",
        default="",
        help="Optional git branch, tag, or commit to checkout after clone or fetch.",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Fetch and fast-forward the existing checkout when the target already exists.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    target = repo_root / ".hexiam" / "hexalgon-iam-system"
    source = args.source
    env_template = repo_root / "hexiam.env.bundle.example"
    bundle_env = target / ".env.bundle"

    if target.exists():
        if not (target / ".git").exists():
            print(f"Target exists but is not a git repository: {target}", file=sys.stderr)
            return 1
        if args.update:
            run(["git", "fetch", "--all", "--tags"], cwd=target)
            if args.ref:
                run(["git", "checkout", args.ref], cwd=target)
            else:
                run(["git", "pull", "--ff-only"], cwd=target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", source, str(target)])
        if args.ref:
            run(["git", "checkout", args.ref], cwd=target)

    copy_if_missing(env_template, bundle_env)

    print(f"HexIAM bundle prepared at: {target}")
    print(f"Bundle env file: {bundle_env}")
    print("Next step: edit .env and .hexiam/hexalgon-iam-system/.env.bundle, then run:")
    print("  docker compose -f docker-compose.yaml -f docker-compose.with-hexiam.yaml up -d --build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
