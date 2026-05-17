# HexShare

A secure document sharing platform with fine-grained access control, built with FastAPI and React.

## Features

- **Document Management**: Upload, organize, move between groups, and delete documents
- **Document Groups**: Create groups with member permissions and shared document access
- **Share Links**: Generate secure, time-limited share links with customizable permissions
- **Fine-grained Access Control**: Role-based permissions via HexIAM integration
- **Analytics**: Track document views and engagement

## Architecture

### Backend (FastAPI)
- **Authentication**: OIDC-based authentication with HexIAM
- **Authorization**: Hybrid edge/PDP authorization with policy-based access control
- **Storage**: PostgreSQL for metadata, S3-compatible object storage for files
- **Token Management**: JWT-based access tokens with automatic refresh

### Frontend (React + TypeScript)
- **Modern UI**: TailwindCSS, Lucide icons
- **Automatic Token Refresh**: Seamless session management

## Authentication Flow

### Login
1. User visits `/api/auth/login` → Redirects to HexIAM authorize endpoint
2. After successful authentication, callback sets cookies:
   - `hexshare_access_token` (httponly, short-lived)
   - `hexshare_refresh_token` (httponly, 30 days)
3. User is redirected to the dashboard

### Token Refresh
The frontend automatically refreshes tokens when receiving a 401 response:
1. Calls `POST /api/auth/refresh`
2. Backend uses stored refresh token to get new tokens from HexIAM
3. New access token is set in cookie
4. Original request is retried

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/login` | GET | Initiate OIDC login flow |
| `/api/auth/callback` | GET | OIDC callback handler |
| `/api/auth/signup` | GET | Initiate signup flow |
| `/api/auth/refresh` | POST | Refresh access token |
| `/api/auth/logout` | POST | Clear auth cookies |

## Environment Variables

### Backend
```env
# Database
DATABASE_URL=postgresql://user:pass@host:5432/hexshare

# HexIAM Integration
HEXIAM_URL=http://localhost:8000
HEXIAM_PDP_URL=http://localhost:8000
HEXIAM_JWT_SECRET=your-jwt-secret
HEXSHARE_CLIENT_ID=your-client-id
HEXSHARE_CLIENT_SECRET=your-client-secret
HEXSHARE_PDP_CLIENT_ID=your-pdp-client-id
HEXSHARE_PDP_CLIENT_SECRET=your-pdp-client-secret

# URLs
HEXSHARE_PUBLIC_URL=http://localhost:8099
HEXSHARE_FRONTEND_URL=http://localhost:3003

# Runtime switches
HEXSHARE_STORAGE=postgres
HEXSHARE_ACCESS_CONTROL=hybrid
HEXSHARE_AUTHENTICATOR=hexiam
HEXSHARE_IAM_POLICY=hexiam
HEXSHARE_OBJECT_STORAGE=s3
HEXSHARE_VIEWER_STRATEGY=secure_streaming
HEXSHARE_DOCUMENT_PROCESSING_ENABLED=true

# S3-compatible object storage (MinIO/S3/R2)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
HEXSHARE_OBJECT_BUCKET=hexshare-documents
HEXSHARE_OBJECT_PREFIX=documents
S3_ENDPOINT_URL=http://localhost:9000
S3_PUBLIC_ENDPOINT_URL=http://localhost:9000
S3_REGION=us-east-1
S3_FORCE_PATH_STYLE=true

# Optional alternative adapters
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
CLOUDFLARE_R2_ACCOUNT_ID=
```

### Frontend
```env
VITE_API_URL=http://localhost:8001
VITE_API_PROXY_TARGET=http://host.docker.internal:8000
VITE_BASE_PATH=/
```

## Running Locally

### Backend
```bash
# Install dependencies
poetry install

# Start local stack (API, frontend, Postgres, MinIO)
docker compose up --build

# MinIO console
# http://localhost:9001
# Local browser upload CORS is configured on the MinIO container via `MINIO_API_CORS_ALLOW_ORIGIN` for:
# - http://localhost:3000
# - http://localhost:3003
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## API Documentation

### Documents
- `GET /api/v1/documents` - List all documents
- `POST /api/v1/documents` - Create document metadata
- `GET /api/v1/documents/{id}` - Get document details
- `PATCH /api/v1/documents/{id}/group` - Move document between groups
- `DELETE /api/v1/documents/{id}` - Delete document

### Document Groups
- `GET /api/v1/document-groups` - List groups
- `POST /api/v1/document-groups` - Create group
- `GET /api/v1/document-groups/{id}` - Get group details
- `POST /api/v1/document-groups/{id}/members` - Add member
- `DELETE /api/v1/document-groups/{id}/members/{user_id}` - Remove member

### Share Links
- `POST /api/v1/links` - Create share link
- `GET /api/v1/links` - List share links
- `DELETE /api/v1/links/{id}` - Revoke share link

### Workspace
- `GET /api/v1/workspace/users` - List workspace users (for member selection)

## License

MIT
