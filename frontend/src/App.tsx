/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Landing } from './pages/Landing';
import { Login } from './pages/Login';
import { Signup } from './pages/Signup';
import { Dashboard } from './pages/Dashboard';
import { DocumentDetails } from './pages/DocumentDetails';
import { ExternalRoomInvitation } from './pages/ExternalRoomInvitation';
import { ExternalRoomViewer } from './pages/ExternalRoomViewer';
import { Groups } from './pages/Groups';
import { GroupDetails } from './pages/GroupDetails';
import { Activity } from './pages/Activity';
import { Ndas } from './pages/Ndas';
import { ViewDocument } from './pages/ViewDocument';
import { NotFound } from './pages/NotFound';
import { ErrorBoundary } from './components/ErrorBoundary';

export default function App() {
  return (
    <ErrorBoundary>
    <Router>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/view/:token" element={<ViewDocument />} />
        <Route path="/external-room/invitations/:token" element={<ExternalRoomInvitation />} />
        <Route path="/external-room/viewer/:sessionId" element={<ExternalRoomViewer />} />
        
        {/* Authenticated Routes */}
        <Route element={<Layout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/documents/:id" element={<DocumentDetails />} />
          <Route path="/groups" element={<Groups />} />
          <Route path="/groups/:id" element={<GroupDetails />} />
          <Route path="/activity" element={<Activity />} />
          <Route path="/ndas" element={<Ndas />} />
        </Route>
        
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Router>
    </ErrorBoundary>
  );
}
