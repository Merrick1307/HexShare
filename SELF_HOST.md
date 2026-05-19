# Self-hosting HexShare

This guide covers the current self-host path for running HexShare on its own or together with HexIAM from the companion repository.

## 1. Choose the deployment shape

You have two practical options:

- HexShare only: point HexShare at an existing OIDC / IAM provider
- HexShare + bundled HexIAM: clone HexIAM into `.hexiam/` and run both stacks together

The second option is what the new bundle files in this repo target.

## 2. Prepare HexShare configuration

Copy `.env.example` to `.env` and set the values that matter for your environment.

Minimum settings to review:

```env
DATABASE_URL=postgresql://postgres:postgres@db:5432/postgres
HEXSHARE_PUBLIC_URL=http://localhost:8099
HEXSHARE_FRONTEND_URL=http://localhost:3000
HEXSHARE_OBJECT_BUCKET=hexshare-documents
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
HEXSHARE_JWT_SECRET=replace-me
HEXSHARE_SESSION_SECRET=replace-me
```

If you are using the bundled HexIAM flow, also keep these in mind:

```env
HEXIAM_PUBLIC_URL=http://localhost:8000
HEXSHARE_AUTHENTICATOR=hexiam
HEXSHARE_DEFAULT_OIDC_IDP=hexiam
HEXSHARE_IAM_POLICY=hexiam
HEXSHARE_ACCESS_CONTROL=hybrid
HEXSHARE_SHARE_TOKEN_REVOCATION_STORE=redis
```

## 3. Prepare the bundled HexIAM checkout

From the HexShare repo root:

```bash
python scripts/prepare_hexiam.py
```

If you already have a local HexIAM checkout and want to clone from that instead of GitHub:

```bash
python scripts/prepare_hexiam.py --source ..\Hexalgon-iam-system
```

If the checkout already exists and you want to refresh it:

```bash
python scripts/prepare_hexiam.py --update
```

The script creates:

- `.hexiam/hexalgon-iam-system/`
- `.hexiam/hexalgon-iam-system/.env.bundle` if it does not already exist

The bundle env file comes from [hexiam.env.bundle.example](hexiam.env.bundle.example).

## 4. Configure HexIAM for the bundle

Edit `.hexiam/hexalgon-iam-system/.env.bundle`.

At minimum, set:

```env
DATABASE_USER=hexiam
DATABASE_PASSWORD=replace-me
DATABASE_NAME=hexiam
POSTGRES_ADMIN_PASSWORD=replace-me
POSTGRES_DB=hexiam
DATABASE_URL=postgresql://hexiam:replace-me@hexiam-postgres:5432/hexiam
JWT_SECRET=replace-me
ENCRYPT_KEY=replace-me-32-byte-secret
APP_BASE_URL=http://localhost:8000
REDIS_HOST=hexiam-redis
REDIS_PORT=6379
VITE_API_PROXY_TARGET=http://hexiam:8000
```

Notes:

- `APP_BASE_URL` should match `HEXIAM_PUBLIC_URL`
- `DATABASE_URL` should use the internal bundle service name `hexiam-postgres`
- the admin portal uses `VITE_API_PROXY_TARGET=http://hexiam:8000` inside Docker

## 5. Start the combined stack

```bash
docker compose -f docker-compose.yaml -f docker-compose.with-hexiam.yaml up -d --build
```

This starts:

- HexShare API
- HexShare worker
- HexShare frontend
- HexShare PostgreSQL, Redis, and MinIO
- HexIAM API
- HexIAM admin portal
- HexIAM PostgreSQL and Redis

Default host ports:

- HexShare API: `http://localhost:8099`
- HexShare frontend: `http://localhost:3000`
- HexIAM API: `http://localhost:8000`
- HexIAM admin portal: `http://localhost:5173`
- MinIO API: `http://localhost:9000`
- MinIO console: `http://localhost:9001`

## 6. Register HexShare as an OIDC client in HexIAM

The bundle overlay wires the runtimes together, but you still need to register client credentials in HexIAM.

Create a confidential OIDC client for HexShare with:

- redirect URI: `http://localhost:8099/api/auth/callback`
- scopes: `openid profile email`
- authorization code + PKCE enabled
- client credentials enabled if you want to reuse the same client for service-to-service calls

Then place the client values in HexShare `.env`:

```env
HEXSHARE_CLIENT_ID=replace-me
HEXSHARE_CLIENT_SECRET=replace-me
```

For cleaner separation, create a second confidential client for policy and PDP calls:

```env
HEXSHARE_PDP_CLIENT_ID=replace-me
HEXSHARE_PDP_CLIENT_SECRET=replace-me
```

If you do not create separate PDP credentials, the HexIAM adapters fall back to `HEXSHARE_CLIENT_ID` and `HEXSHARE_CLIENT_SECRET`.

## 7. Smoke checks

After the stack is up:

1. open `http://localhost:3000`
2. open `http://localhost:8099/docs`
3. open `http://localhost:8000/health`
4. open `http://localhost:5173`
5. test login from HexShare through the registered HexIAM client
6. upload a document, create a share link, revoke it, and verify the link stops working

## 8. Running HexShare without bundled HexIAM

If you already have an OIDC / IAM provider:

1. use the default `docker compose up -d --build`
2. point `HEXIAM_URL` or the relevant OIDC settings at your provider
3. configure `HEXSHARE_AUTHENTICATOR`, `HEXSHARE_DEFAULT_OIDC_IDP`, and `HEXSHARE_IAM_POLICY` to match your setup

If you are not using HexIAM for authorization, use the local adapters and keep the access-control mode consistent with them.

## 9. Current limits to account for

- HexIAM tenant bootstrap and OIDC client registration are still manual
- the current backend adapters assume a host-reachable public HexIAM URL for browser redirects
- share-token revocation should be set to Redis for real multi-instance deployments
- self-hosting here is Docker Compose oriented; there is no Kubernetes packaging in this repo yet
