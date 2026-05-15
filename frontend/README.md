# HexShare Frontend

React-based frontend for HexShare document sharing platform.

## Tech Stack

- **React 18** with TypeScript
- **Vite** for build tooling
- **TailwindCSS** for styling
- **Lucide React** for icons
- **React Router** for navigation

## Features

- Document upload and management
- Document group management with member permissions
- Share link creation with customizable permissions
- Automatic token refresh on session expiry
- Responsive design

## Authentication

The frontend uses httponly cookies for authentication, managed by the backend:

- **Access Token**: Short-lived JWT stored in `hexshare_access_token` cookie
- **Refresh Token**: Long-lived token stored in `hexshare_refresh_token` cookie

### Automatic Token Refresh

When any API call returns 401 (Unauthorized):
1. The frontend automatically calls `POST /api/auth/refresh`
2. If successful, the original request is retried
3. If refresh fails, user is redirected to login

This provides seamless session management without manual intervention.

## Environment Variables

Create a `.env.local` file:

```env
VITE_API_URL=http://localhost:8001
VITE_API_PROXY_TARGET=http://host.docker.internal:8000
VITE_BASE_PATH=/
```

## Development

### Prerequisites
- Node.js 18+
- npm or yarn

### Setup

```bash
# Install dependencies
npm install

# Start development server
npm run dev
```

The app runs at `http://localhost:3000` by default. The dev server proxies `/api` to the backend to avoid CORS.

### Build

```bash
npm run build
```

## API Integration

The `api.ts` service handles all backend communication:

```typescript
import { api } from './services/api';

// Authentication
api.loginUrl      // GET - redirect to login
api.signupUrl     // GET - redirect to signup
api.logout()      // POST - clear session
api.refreshToken() // POST - manually refresh token

// Documents
api.listDocuments()
api.getDocument(id)
api.deleteDocument(id)
api.moveDocumentToGroup(documentId, groupId)

// Groups
api.listGroups()
api.createGroup(data)
api.addGroupMember(groupId, userId, role)
api.removeGroupMember(groupId, userId)

// Share Links
api.createLink(documentId, options)
api.listLinks()

// Workspace Users
api.listWorkspaceUsers(page, pageSize)
```

## Project Structure

```
src/
├── components/     # Reusable UI components
│   └── ui/         # Base UI components (Button, Input, Modal)
├── pages/          # Page components
│   ├── Dashboard.tsx
│   ├── DocumentDetails.tsx
│   ├── Groups.tsx
│   ├── GroupDetails.tsx
│   ├── Landing.tsx
│   ├── Login.tsx
│   ├── Signup.tsx
│   └── ViewDocument.tsx
├── services/       # API and utility services
│   └── api.ts      # Backend API client
├── types/          # TypeScript type definitions
└── lib/            # Utility functions
```
