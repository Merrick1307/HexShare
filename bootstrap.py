#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path


def _load_env_file(path: Path) -> dict[str, str]:
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def _save_env_file(path: Path, env: dict[str, str]) -> None:
    lines = []
    if path.exists():
        for line in path.read_text().splitlines():
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith("#"):
                lines.append(line)
                continue
            if "=" in line:
                k = line.split("=", 1)[0].strip()
                if k in env:
                    lines.append(f"{k}={env[k]}")
                    del env[k]
                else:
                    lines.append(line)
        lines.append("")
    for k, v in env.items():
        lines.append(f"{k}={v}")
    path.write_text("\n".join(lines))


def _prompt_or_default(prompt: str, default: str | None, secret: bool = False) -> str:
    if default:
        p = f"{prompt} [{default}]: "
    else:
        p = f"{prompt}: "
    try:
        value = input(p).strip()
        if not value and default:
            return default
        return value
    except EOFError:
        if default:
            return default
        raise RuntimeError("Input required but not provided")


def _hexiam_mode() -> dict[str, str]:
    print("\n=== HexIAM Mode Configuration ===")
    env = {}
    env["HEXSHARE_AUTHENTICATOR"] = "hexiam"
    env["HEXSHARE_IAM_POLICY"] = "hexiam"
    env["HEXSHARE_DEFAULT_OIDC_IDP"] = "hexiam"
    env["HEXSHARE_ACCESS_CONTROL"] = "hybrid"
    env["HEXIAM_URL"] = _prompt_or_default("HexIAM URL", "http://localhost:8000")
    env["HEXIAM_PDP_URL"] = _prompt_or_default("HexIAM PDP URL", env["HEXIAM_URL"])
    env["HEXIAM_JWT_SECRET"] = _prompt_or_default("HexIAM JWT Secret", None, secret=True)
    env["HEXSHARE_CLIENT_ID"] = _prompt_or_default("HexShare Client ID", None)
    env["HEXSHARE_CLIENT_SECRET"] = _prompt_or_default("HexShare Client Secret", None, secret=True)
    env["HEXSHARE_PDP_CLIENT_ID"] = _prompt_or_default("HexShare PDP Client ID", env["HEXSHARE_CLIENT_ID"])
    env["HEXSHARE_PDP_CLIENT_SECRET"] = _prompt_or_default("HexShare PDP Client Secret", env["HEXSHARE_CLIENT_SECRET"])
    env["HEXSHARE_JWT_SECRET"] = _prompt_or_default("HexShare JWT Secret", None, secret=True)
    env["HEXSHARE_SESSION_SECRET"] = _prompt_or_default("HexShare Session Secret", None, secret=True)
    env["HEXSHARE_PUBLIC_URL"] = _prompt_or_default("HexShare Public URL", "http://localhost:8099")
    env["HEXSHARE_FRONTEND_URL"] = _prompt_or_default("HexShare Frontend URL", "http://localhost:3000")
    return env


def _local_google_mode() -> dict[str, str]:
    print("\n=== Local Google OIDC Mode Configuration ===")
    env = {}
    env["HEXSHARE_AUTHENTICATOR"] = "local"
    env["HEXSHARE_IAM_POLICY"] = "local"
    env["HEXSHARE_DEFAULT_OIDC_IDP"] = "google"
    env["HEXSHARE_ACCESS_CONTROL"] = "edge"
    env["HEXSHARE_LOCAL_TENANT_ID"] = _prompt_or_default("Local Tenant ID", "local")
    env["HEXSHARE_AUTH_AUDIENCE"] = _prompt_or_default("Auth Audience", "hexshare")
    env["HEXSHARE_JWT_SECRET"] = _prompt_or_default("HexShare JWT Secret", None, secret=True)
    env["HEXSHARE_SESSION_SECRET"] = _prompt_or_default("HexShare Session Secret", None, secret=True)
    env["HEXSHARE_PUBLIC_URL"] = _prompt_or_default("HexShare Public URL", "http://localhost:8099")
    env["HEXSHARE_FRONTEND_URL"] = _prompt_or_default("HexShare Frontend URL", "http://localhost:3000")
    env["GOOGLE_OIDC_CLIENT_ID"] = _prompt_or_default("Google OIDC Client ID", None)
    env["GOOGLE_OIDC_CLIENT_SECRET"] = _prompt_or_default("Google OIDC Client Secret", None, secret=True)
    env["GOOGLE_OIDC_AUTHORIZE_URL"] = _prompt_or_default("Google Authorize URL", "https://accounts.google.com/o/oauth2/v2/auth")
    env["GOOGLE_OIDC_TOKEN_URL"] = _prompt_or_default("Google Token URL", "https://oauth2.googleapis.com/token")
    env["GOOGLE_OIDC_USERINFO_URL"] = _prompt_or_default("Google UserInfo URL", "https://openidconnect.googleapis.com/v1/userinfo")
    return env


def main() -> None:
    parser = argparse.ArgumentParser(description="HexShare environment bootstrap helper")
    parser.add_argument(
        "--with-hexiam",
        action="store_true",
        help="Configure for HexIAM-backed deployment",
    )
    parser.add_argument(
        "--with-local-google",
        action="store_true",
        help="Configure for local Google OIDC mode (OSS MVP)",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file (default: .env)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write configuration to .env file",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing secrets in .env without prompting",
    )
    args = parser.parse_args()

    if args.with_hexiam and args.with_local_google:
        print("Error: Cannot specify both --with-hexiam and --with-local-google")
        sys.exit(1)

    if not args.with_hexiam and not args.with_local_google:
        print("Error: Must specify either --with-hexiam or --with-local-google")
        sys.exit(1)

    env_path = Path(args.env_file)
    existing = _load_env_file(env_path)

    if args.with_hexiam:
        new_env = _hexiam_mode()
    else:
        new_env = _local_google_mode()

    merged = {**existing, **new_env}
    if args.write:
        if args.force:
            _save_env_file(env_path, merged)
            print(f"\nConfiguration written to {env_path}")
        else:
            secrets = [k for k in new_env if "SECRET" in k or "secret" in k.lower()]
            for k in secrets:
                if k in existing and existing[k]:
                    current = existing[k]
                    overwrite = input(f"Overwrite existing {k}? [y/N]: ").strip().lower()
                    if overwrite != "y":
                        merged[k] = current
            _save_env_file(env_path, merged)
            print(f"\nConfiguration written to {env_path}")
    else:
        print("\n=== Generated Configuration ===")
        for k, v in new_env.items():
            print(f"{k}={v}")
        print(f"\nTo save, run: python bootstrap.py {'--with-hexiam' if args.with_hexiam else '--with-local-google'} --write")

    print("\n=== Next Steps ===")
    print("1. Ensure DATABASE_URL, REDIS_URL, and S3_* variables are set in .env")
    print("2. Run migrations: docker-compose run hexshare-migrate")
    print("3. Start services: docker-compose up -d")
    print("4. Access the application at the configured HEXSHARE_FRONTEND_URL")


if __name__ == "__main__":
    main()
