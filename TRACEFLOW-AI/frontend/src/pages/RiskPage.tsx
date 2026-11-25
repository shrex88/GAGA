import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { RiskBadge } from '../components/RiskBadge';

export const RiskPage: React.FC = () => {
  const [accounts, setAccounts] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);

  useEffect(() => {
    Promise.all([api.get('/risk/accounts'), api.get('/risk/summary')]).then(([aRes, sRes]) => {
      setAccounts(aRes.data.accounts || []);
      setSummary(sRes.data);
    });
  }, []);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-white">Unified Risk Intelligence</h1>
        <p className="text-xs text-slate-400">
          Transparent multi-engine scoring combining Fraud, AML, and Network Centrality (0–29 Low, 30–49 Moderate, 50–74 High, 75–100 Critical)
        </p>
      </div>

      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="tf-card rounded-xl p-4">
            <div className="text-xs text-slate-400">Monitored Accounts</div>
            <div className="text-2xl font-bold text-white mt-1">{summary.total_accounts}</div>
          </div>
          <div className="tf-card rounded-xl p-4">
            <div className="text-xs text-slate-400">Critical Risk Accounts</div>
            <div className="text-2xl font-bold text-rose-400 mt-1">{summary.critical_accounts}</div>
          </div>
          <div className="tf-card rounded-xl p-4">
            <div className="text-xs text-slate-400">High Risk Accounts</div>
            <div className="text-2xl font-bold text-amber-400 mt-1">{summary.high_accounts}</div>
          </div>
        </div>
      )}

      <div className="tf-card rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-800 font-semibold text-sm text-white">
          Account Risk Breakdown & Contributing Factors
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-navy-900 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="text-left px-4 py-2.5">Account</th>
                <th className="text-right px-4 py-2.5">Fraud</th>
                <th className="text-right px-4 py-2.5">AML</th>
                <th className="text-right px-4 py-2.5">Network</th>
                <th className="text-right px-4 py-2.5">Combined</th>
                <th className="text-left px-4 py-2.5">Contributing Factors</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {accounts.slice(0, 30).map((a) => (
                <tr key={a.id} className="hover:bg-slate-800/30">
                  <td className="px-4 py-2.5 font-mono text-sky-300">{a.account_number}</td>
                  <td className="px-4 py-2.5 text-right">{a.fraud_risk.toFixed(1)}</td>
                  <td className="px-4 py-2.5 text-right">{a.aml_risk.toFixed(1)}</td>
                  <td className="px-4 py-2.5 text-right">{a.network_risk.toFixed(1)}</td>
                  <td className="px-4 py-2.5 text-right"><RiskBadge category={a.risk_category} score={a.risk_score} /></td>
                  <td className="px-4 py-2.5 text-slate-300 max-w-md truncate">
                    {(a.contributing_factors || []).join(' | ') || 'Baseline activity'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
