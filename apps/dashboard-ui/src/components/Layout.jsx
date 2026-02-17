import React, { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import {
  LayoutDashboard,
  GitBranch,
  ShieldCheck,
  ClipboardCheck,
  FolderGit2,
  Code2,
  BarChart3,
  FileText,
  Settings,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

const NAV = [
  { to: '/',             label: 'Overview',        icon: LayoutDashboard },
  { to: '/devops',       label: 'DevOps',          icon: GitBranch },
  { to: '/devsecops',    label: 'DevSecOps',       icon: ShieldCheck },
  { to: '/quality',      label: 'Code Quality',    icon: Code2 },
  { to: '/governance',   label: 'Governance',      icon: ClipboardCheck },
  { to: '/value-stream', label: 'Value Stream',    icon: BarChart3 },
  { to: '/logging',      label: 'Logging',         icon: FileText },
  { to: '/repos',        label: 'Repositories',    icon: FolderGit2 },
  { to: '/admin',        label: 'Settings',        icon: Settings },
];

function SidebarLink({ to, label, icon: Icon, collapsed }) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      title={collapsed ? label : undefined}
      className={({ isActive }) =>
        `flex items-center gap-3 rounded-lg text-sm font-medium transition
         ${collapsed ? 'justify-center px-2 py-2.5' : 'px-4 py-2.5'}
         ${isActive
           ? 'bg-brand-600/20 text-brand-400'
           : 'text-slate-400 hover:text-slate-200 hover:bg-surface-200/40'}`
      }
    >
      <Icon size={18} className="flex-shrink-0" />
      {!collapsed && <span>{label}</span>}
    </NavLink>
  );
}

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-surface">
      {/* Sidebar */}
      <aside
        className={`flex-shrink-0 bg-surface-100 border-r border-surface-200 flex flex-col transition-all duration-200
          ${collapsed ? 'w-16' : 'w-60'}`}
      >
        {/* Brand */}
        <div className={`flex items-center border-b border-surface-200 ${collapsed ? 'px-2 py-4 justify-center' : 'px-5 py-5'}`}>
          {!collapsed && (
            <div className="flex-1 min-w-0">
              <h1 className="text-lg font-bold tracking-tight text-slate-100 truncate">
                Eng Intelligence
              </h1>
              <p className="text-xs text-slate-500 mt-0.5">Dashboard v2.0</p>
            </div>
          )}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="p-1 rounded hover:bg-surface-200/60 text-slate-400 hover:text-slate-200 transition"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
        </div>

        {/* Navigation */}
        <nav className={`flex-1 py-4 space-y-1 overflow-y-auto ${collapsed ? 'px-1.5' : 'px-3'}`}>
          {NAV.map((n) => (
            <SidebarLink key={n.to} {...n} collapsed={collapsed} />
          ))}
        </nav>

        {/* Footer */}
        {!collapsed && (
          <div className="px-5 py-3 border-t border-surface-200 text-xs text-slate-600">
            © {new Date().getFullYear()} Platform Engineering
          </div>
        )}
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto p-6 lg:p-8">
        <Outlet />
      </main>
    </div>
  );
}
