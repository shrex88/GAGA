import React, { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Briefcase,
  Database,
  FileText,
  History,
  LayoutDashboard,
  Menu,
  Network,
  Settings,
  ShieldAlert,
  ShieldCheck,
  X,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const ROLE_OPTIONS = [
  { label: 'Bank Admin', role: 'bank_admin' },
  { label: 'Fraud Analyst', role: 'fraud_analyst' },
  { label: 'AML Investigator', role: 'aml_investigator' },
  { label: 'Auditor', role: 'auditor' },
];

const NAV_ITEMS = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, perm: 'dashboard:read' },
  { to: '/transactions', label: 'Transaction Explorer', icon: Activity, perm: 'transactions:read' },
  { to: '/fraud', label: 'Fraud Intelligence', icon: ShieldAlert, perm: 'fraud:read' },
  { to: '/aml', label: 'AML Intelligence', icon: Network, perm: 'aml:read' },
  { to: '/risk', label: 'Risk Analysis', icon: BarChart3, perm: 'risk:read' },
  { to: '/alerts', label: 'Alerts Center', icon: AlertTriangle, perm: 'alerts:read' },
  { to: '/cases', label: 'Investigation Cases', icon: Briefcase, perm: 'cases:read' },
  { to: '/data', label: 'Data Management', icon: Database, perm: 'datasets:read' },
  { to: '/reports', label: 'Reports', icon: FileText, perm: 'reports:read' },
  { to: '/audit', label: 'Audit Logs', icon: History, perm: 'audit:read' },
  { to: '/settings', label: 'Settings', icon: Settings, perm: 'settings:read' },
];

export const DashboardLayout: React.FC = () => {
  const { user, health, switchRole, hasPermission } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const visibleNav = NAV_ITEMS.filter((item) => hasPermission(item.perm));

  return (
    <div className="min-h-screen flex bg-[#050914] text-slate-100">
      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-64 bg-[#070d1d] border-r border-slate-800/80 flex flex-col transition-transform duration-200 lg:static lg:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="p-5 border-b border-slate-800/80 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center shadow-lg shadow-blue-900/40">
              <ShieldCheck className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="font-bold text-sm tracking-wide text-white">TRACEFLOW AI</div>
              <div className="text-[10px] text-sky-400 tracking-wider uppercase">Financial Crime Intel</div>
            </div>
          </div>
          <button onClick={() => setSidebarOpen(false)} className="lg:hidden text-slate-400">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-4 py-2.5 border-b border-slate-800/60">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 w-full justify-center">
            Synthetic Demo Dataset Active
          </span>
        </div>

        <nav className="flex-1 overflow-y-auto p-3 space-y-1">
          {visibleNav.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                onClick={() => setSidebarOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-medium transition-colors ${
                    isActive
                      ? 'bg-gradient-to-r from-blue-600/25 to-violet-600/20 text-white border border-blue-500/30'
                      : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/50'
                  }`
                }
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="p-4 border-t border-slate-800/80 space-y-2.5">
          <div className="text-xs">
            <div className="font-semibold text-slate-200 truncate">{user?.full_name}</div>
            <div className="text-[11px] text-slate-400 truncate">{user?.email}</div>
          </div>
          <div>
            <label className="block text-[10px] text-slate-400 uppercase mb-1">Active Role View</label>
            <select
              value={user?.roles?.[0] || 'bank_admin'}
              onChange={(e) => switchRole(e.target.value)}
              className="w-full px-2.5 py-1.5 rounded-lg text-xs bg-navy-900 border border-slate-700 text-sky-300 focus:outline-none focus:border-blue-500"
            >
              {ROLE_OPTIONS.map((r) => (
                <option key={r.role} value={r.role}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-14 border-b border-slate-800/80 bg-[#070d1d]/80 backdrop-blur px-4 lg:px-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button onClick={() => setSidebarOpen(true)} className="lg:hidden text-slate-300">
              <Menu className="w-5 h-5" />
            </button>
            <span className="text-xs text-slate-400 hidden sm:inline">
              Follow the Money. Reveal the Pattern. Protect the Financial System.
            </span>
          </div>
          <div className="flex items-center gap-3 text-xs text-slate-400">
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 text-[11px]">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              Backend {health?.status === 'ok' ? 'Connected' : 'Degraded'} • DB {health?.database?.connected ? 'OK' : 'Down'}
            </span>
            <span className="hidden sm:inline">
              Bank Scope: <span className="text-sky-300 font-mono">{user?.bank_id}</span>
            </span>
          </div>
        </header>

        <main className="flex-1 p-4 lg:p-6 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
