import React from 'react';
import { Outlet, Link, useLocation } from 'react-router-dom';
import { FileText, Folder, LogOut } from 'lucide-react';
import { cn } from '../lib/utils';
import { HexLogo } from './ui/HexLogo';

export function Layout() {
  const location = useLocation();
  const navItems = [
    { icon: FileText, label: 'Documents', path: '/dashboard' },
    { icon: Folder, label: 'Groups', path: '/groups' },
  ];

  return (
    <div className="flex min-h-screen bg-zinc-50">
      <aside className="flex w-64 flex-col border-r border-zinc-200 bg-white">
        <div className="flex h-20 items-center border-b border-zinc-200 px-6">
          <Link to="/dashboard" className="flex items-center gap-3 text-zinc-950">
            <HexLogo className="h-8 w-8" />
            <span className="text-xl font-semibold tracking-tight">HexShare</span>
          </Link>
        </div>

        <nav className="flex-1 space-y-1 px-4 py-6">
          {navItems.map((item) => {
            const isActive = location.pathname === item.path || (item.path !== '/' && location.pathname.startsWith(item.path));
            return (
              <Link
                key={item.path}
                to={item.path}
                className={cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  isActive ? 'bg-zinc-100 text-zinc-900' : 'text-zinc-600 hover:bg-zinc-50 hover:text-zinc-900'
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-zinc-200 p-4">
          <div className="flex items-center justify-between rounded-lg px-3 py-2">
            <div>
              <p className="text-sm font-medium text-zinc-900">My Workspace</p>
              {/* <p className="text-xs text-zinc-500">Cookie-based backend auth</p> */}
            </div>
            <Link to="/" className="text-zinc-400 hover:text-zinc-600" aria-label="Return home">
              <LogOut className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-6xl p-8">
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  );
}
