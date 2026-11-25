import React, { useEffect, useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { RefreshCw, ShieldAlert, Activity, Users, AlertTriangle, Briefcase, Gauge } from 'lucide-react';
import { api } from '../services/api';
import { DashboardKPIs } from '../types';
import { RiskBadge } from '../components/RiskBadge';
import { TransactionGraph } from '../components/TransactionGraph';

export const OverviewPage: React.FC = () => {
  const [days, setDays] = useState(30);
  const [kpis, setKpis] = useState<DashboardKPIs | null>(null);
  const [recentSuspicious, setRecentSuspicious] = useState<any[]>([]);
  const [highRiskAccounts, setHighRiskAccounts] = useState<any[]>([]);
  const [trends, setTrends] = useState<any[]>([]);
  const [riskDist, setRiskDist] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedGraphAccount, setSelectedGraphAccount] = useState<string>('');

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [sumRes, trRes, distRes] = await Promise.all([
        api.get('/dashboard/summary', { params: { days } }),
        api.get('/dashboard/trends', { params: { days } }),
        api.get('/dashboard/risk-distribution'),
      ]);
      setKpis(sumRes.data.kpis);
      setRecentSuspicious(sumRes.data.recent_suspicious || []);
      const hrAccs = sumRes.data.high_risk_accounts_list || [];
      setHighRiskAccounts(hrAccs);
      if (hrAccs.length > 0 && !selectedGraphAccount) {
        setSelectedGraphAccount(hrAccs[0].account_number);
      }
      setTrends(trRes.data.trends || []);
      setRiskDist(distRes.data.distribution || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
  }, [days]);

  const statCards = kpis
    ? [
        { label: 'Transactions Analysed', value: kpis.total_transactions.toLocaleString(), icon: Activity, color: 'text-sky-400' },
        { label: 'Accounts Monitored', value: kpis.total_accounts.toLocaleString(), icon: Users, color: 'text-indigo-400' },
        { label: 'Suspicious Flagged', value: kpis.suspicious_transactions.toLocaleString(), icon: ShieldAlert, color: 'text-amber-400' },
        { label: 'Fraud Alerts', value: kpis.fraud_alerts.toLocaleString(), icon: AlertTriangle, color: 'text-rose-400' },
        { label: 'AML Alerts', value: kpis.aml_alerts.toLocaleString(), icon: AlertTriangle, color: 'text-violet-400' },
        { label: 'High-Risk Accounts', value: kpis.high_risk_accounts.toLocaleString(), icon: ShieldAlert, color: 'text-rose-400' },
        { label: 'Active Cases', value: kpis.active_cases.toLocaleString(), icon: Briefcase, color: 'text-emerald-400' },
        { label: 'Avg Risk Score', value: `${kpis.avg_risk_score.toFixed(1)} / 100`, icon: Gauge, color: 'text-sky-300' },
      ]
    : [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-white">Executive Financial Crime Overview</h1>
          <p className="text-xs text-slate-400">Real-time metrics computed from stored banking transactions and detection engines</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="px-3 py-1.5 text-xs bg-navy-900 border border-slate-700 rounded-lg text-slate-100"
          >
            <option value={7}>Last 7 Days</option>
            <option value={30}>Last 30 Days</option>
            <option value={90}>Last 90 Days</option>
          </select>
          <button
            onClick={fetchAll}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white rounded-lg"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5">
        {statCards.map((c) => {
          const Icon = c.icon;
          return (
            <div key={c.label} className="tf-card rounded-xl p-4 flex items-start justify-between">
              <div>
                <div className="text-[11px] text-slate-400">{c.label}</div>
                <div className="text-xl font-bold text-white mt-1">{c.value}</div>
              </div>
              <Icon className={`w-5 h-5 ${c.color}`} />
            </div>
          );
        })}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="tf-card rounded-xl p-4 lg:col-span-2">
          <h3 className="text-sm font-semibold text-slate-100 mb-3">Transaction Volume & Fraud vs AML Detections</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trends}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="date" stroke="#64748b" tick={{ fontSize: 10 }} />
                <YAxis stroke="#64748b" tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: 12 }} />
                <Area type="monotone" dataKey="fraud_count" name="Fraud Flags" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.25} />
                <Area type="monotone" dataKey="aml_count" name="AML Flags" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.25} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="tf-card rounded-xl p-4">
          <h3 className="text-sm font-semibold text-slate-100 mb-3">Risk Score Distribution</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={riskDist}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="category" stroke="#64748b" tick={{ fontSize: 11 }} />
                <YAxis stroke="#64748b" tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: 12 }} />
                <Bar dataKey="transactions" name="Transactions" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                <Bar dataKey="accounts" name="Accounts" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Tables */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="tf-card rounded-xl p-4">
          <h3 className="text-sm font-semibold text-slate-100 mb-3">Recent Suspicious Activities</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="text-left py-2">Ref</th>
                  <th className="text-left py-2">Flow</th>
                  <th className="text-right py-2">Amount</th>
                  <th className="text-right py-2">Risk</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {recentSuspicious.map((t) => (
                  <tr key={t.id} className="hover:bg-slate-800/30">
                    <td className="py-2 font-mono text-sky-300">{t.transaction_ref}</td>
                    <td className="py-2 text-slate-300">{t.source_account} → {t.destination_account}</td>
                    <td className="py-2 text-right font-medium">${Number(t.amount).toLocaleString()}</td>
                    <td className="py-2 text-right"><RiskBadge category={t.risk_category} score={t.risk_score} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="tf-card rounded-xl p-4">
          <h3 className="text-sm font-semibold text-slate-100 mb-3">High-Risk Accounts (Click to Inspect Network)</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="text-left py-2">Account</th>
                  <th className="text-left py-2">Type</th>
                  <th className="text-right py-2">Balance</th>
                  <th className="text-right py-2">Risk</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {highRiskAccounts.map((a) => (
                  <tr
                    key={a.id}
                    onClick={() => setSelectedGraphAccount(a.account_number)}
                    className="hover:bg-indigo-500/10 cursor-pointer"
                  >
                    <td className="py-2 font-mono text-indigo-300">{a.account_number}</td>
                    <td className="py-2 text-slate-300 capitalize">{a.account_type}</td>
                    <td className="py-2 text-right">${Number(a.balance).toLocaleString()}</td>
                    <td className="py-2 text-right"><RiskBadge category={a.risk_category} score={a.risk_score} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Live Transaction Graph Overview */}
      <TransactionGraph initialAccountId={selectedGraphAccount} height="400px" />
    </div>
  );
};
