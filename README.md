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
- **Storage**: PostgreSQL for metadata, object storage (S3/Cloudinary) for files
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
HEXIAM_JWT_SECRET=your-jwt-secret
HEXSHARE_CLIENT_ID=your-client-id
HEXSHARE_CLIENT_SECRET=your-client-secret
HEXSHARE_PDP_CLIENT_ID=your-pdp-client-id
HEXSHARE_PDP_CLIENT_SECRET=your-pdp-client-secret

# URLs
HEXSHARE_PUBLIC_URL=http://localhost:8001
HEXSHARE_FRONTEND_URL=http://localhost:3003

# Object Storage (choose one)
CLOUDINARY_URL=cloudinary://...
# or
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET=...
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
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8001 --reload
```

### Frontend
```bash
cd hexshare-frontend
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
