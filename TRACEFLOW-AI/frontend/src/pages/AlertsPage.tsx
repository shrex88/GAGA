import React, { useEffect, useState } from 'react';
import { Briefcase, CheckCircle, Eye, XCircle } from 'lucide-react';
import { api } from '../services/api';
import { AlertItem, User } from '../types';
import { RiskBadge } from '../components/RiskBadge';
import { useAuth } from '../context/AuthContext';

export const AlertsPage: React.FC = () => {
  const { hasPermission } = useAuth();
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [severity, setSeverity] = useState('');
  const [category, setCategory] = useState('');
  const [resolveModal, setResolveModal] = useState<{ id: string; action: 'resolved' | 'dismissed' } | null>(null);
  const [reason, setReason] = useState('');
  const [msg, setMsg] = useState('');

  const load = async () => {
    const params: any = {};
    if (severity) params.severity = severity;
    if (category) params.category = category;
    const [aRes, uRes] = await Promise.all([api.get('/alerts', { params }), api.get('/auth/users')]);
    setAlerts(aRes.data.alerts || []);
    setUsers(uRes.data || []);
  };

  useEffect(() => { load(); }, [severity, category]);

  const markUnderReview = async (id: string) => {
    await api.patch(`/alerts/${id}`, { status: 'under_review' });
    load();
  };

  const assignAlert = async (id: string, userId: string) => {
    if (!userId) return;
    await api.post(`/alerts/${id}/assign`, { assigned_to: userId });
    load();
  };

  const submitResolve = async () => {
    if (!resolveModal || !reason.trim()) return;
    await api.patch(`/alerts/${resolveModal.id}`, { status: resolveModal.action, resolution_reason: reason });
    setResolveModal(null);
    setReason('');
    load();
  };

  const convertToCase = async (a: AlertItem) => {
    const res = await api.post(`/alerts/${a.id}/convert-to-case`, { priority: a.severity === 'Critical' ? 'Critical' : 'High' });
    setMsg(`Converted alert to Case ${res.data.case_number}`);
    load();
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-white">Alerts Center</h1>
          <p className="text-xs text-slate-400">Triage Fraud & AML alerts, assign analysts, resolve with mandatory reason, or escalate to cases</p>
        </div>
        <div className="flex items-center gap-2">
          <select value={severity} onChange={(e) => setSeverity(e.target.value)} className="px-3 py-1.5 text-xs bg-navy-900 border border-slate-700 rounded-lg">
            <option value="">All Severities</option>
            <option value="Critical">Critical</option>
            <option value="High">High</option>
            <option value="Moderate">Moderate</option>
          </select>
          <select value={category} onChange={(e) => setCategory(e.target.value)} className="px-3 py-1.5 text-xs bg-navy-900 border border-slate-700 rounded-lg">
            <option value="">All Categories</option>
            <option value="fraud">Fraud</option>
            <option value="aml">AML</option>
          </select>
        </div>
      </div>

      {msg && <div className="text-xs text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-2.5">{msg}</div>}

      <div className="space-y-3">
        {alerts.map((a) => (
          <div key={a.id} className="tf-card rounded-xl p-4 space-y-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2.5">
                <RiskBadge category={a.severity} score={a.risk_score} />
                <span className="text-sm font-semibold text-white">{a.title}</span>
                <span className="text-xs font-mono text-sky-300">{a.account_number}</span>
              </div>
              <span className="text-xs px-2.5 py-0.5 rounded bg-slate-800 text-slate-300 uppercase">{a.status.replace('_', ' ')}</span>
            </div>

            <p className="text-xs text-slate-300">{a.supporting_evidence?.explanation}</p>

            {a.resolution_reason && (
              <div className="text-xs text-emerald-300 bg-emerald-500/10 px-2.5 py-1.5 rounded">
                Resolution Reason: {a.resolution_reason}
              </div>
            )}

            {hasPermission('alerts:write') && (
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <select
                  value={a.assigned_to || ''}
                  onChange={(e) => assignAlert(a.id, e.target.value)}
                  className="px-2.5 py-1 text-xs bg-navy-900 border border-slate-700 rounded text-slate-200"
                >
                  <option value="">Assign Analyst...</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>{u.full_name}</option>
                  ))}
                </select>
                <button onClick={() => markUnderReview(a.id)} className="inline-flex items-center gap-1 px-2.5 py-1 text-xs bg-sky-600/20 hover:bg-sky-600/30 text-sky-300 border border-sky-500/30 rounded">
                  <Eye className="w-3.5 h-3.5" /> Under Review
                </button>
                <button onClick={() => setResolveModal({ id: a.id, action: 'resolved' })} className="inline-flex items-center gap-1 px-2.5 py-1 text-xs bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 rounded">
                  <CheckCircle className="w-3.5 h-3.5" /> Resolve
                </button>
                <button onClick={() => setResolveModal({ id: a.id, action: 'dismissed' })} className="inline-flex items-center gap-1 px-2.5 py-1 text-xs bg-slate-700/40 hover:bg-slate-700 text-slate-300 border border-slate-600 rounded">
                  <XCircle className="w-3.5 h-3.5" /> Dismiss
                </button>
                {hasPermission('cases:write') && a.status !== 'escalated' && (
                  <button onClick={() => convertToCase(a)} className="inline-flex items-center gap-1 px-2.5 py-1 text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded">
                    <Briefcase className="w-3.5 h-3.5" /> Convert to Case
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {resolveModal && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="tf-card rounded-xl p-5 max-w-md w-full space-y-4">
            <h3 className="text-sm font-bold text-white capitalize">{resolveModal.action} Alert (Mandatory Reason)</h3>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              placeholder="Enter justification for audit log..."
              className="w-full p-2.5 text-xs bg-navy-900 border border-slate-700 rounded-lg text-white"
            />
            <div className="flex justify-end gap-2">
              <button onClick={() => setResolveModal(null)} className="px-3 py-1.5 text-xs bg-slate-800 rounded-lg">Cancel</button>
              <button onClick={submitResolve} disabled={!reason.trim()} className="px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg">
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
