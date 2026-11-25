import React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { DashboardLayout } from './layouts/DashboardLayout';
import { OverviewPage } from './pages/OverviewPage';
import { TransactionsPage } from './pages/TransactionsPage';
import { FraudPage } from './pages/FraudPage';
import { AmlPage } from './pages/AmlPage';
import { RiskPage } from './pages/RiskPage';
import { AlertsPage } from './pages/AlertsPage';
import { CasesPage } from './pages/CasesPage';
import { DataManagementPage } from './pages/DataManagementPage';
import { ReportsPage } from './pages/ReportsPage';
import { AuditLogsPage } from './pages/AuditLogsPage';
import { SettingsPage } from './pages/SettingsPage';

const AppRoutes: React.FC = () => {
  const { user, loading, hasPermission } = useAuth();
  if (loading || !user) {
    return (
      <div className="min-h-screen bg-[#050914] flex items-center justify-center text-slate-400 text-sm">
        Initializing TRACEFLOW AI Platform...
      </div>
    );
  }

  const guard = (perm: string, el: React.ReactNode) =>
    hasPermission(perm) ? el : <Navigate to="/" replace />;

  return (
    <Routes>
      <Route path="/login" element={<Navigate to="/" replace />} />
      <Route path="/" element={<DashboardLayout />}>
        <Route index element={<OverviewPage />} />
        <Route path="transactions" element={guard('transactions:read', <TransactionsPage />)} />
        <Route path="fraud" element={guard('fraud:read', <FraudPage />)} />
        <Route path="aml" element={guard('aml:read', <AmlPage />)} />
        <Route path="risk" element={guard('risk:read', <RiskPage />)} />
        <Route path="alerts" element={guard('alerts:read', <AlertsPage />)} />
        <Route path="cases" element={guard('cases:read', <CasesPage />)} />
        <Route path="data" element={guard('datasets:read', <DataManagementPage />)} />
        <Route path="reports" element={guard('reports:read', <ReportsPage />)} />
        <Route path="audit" element={guard('audit:read', <AuditLogsPage />)} />
        <Route path="settings" element={guard('settings:read', <SettingsPage />)} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}
