import React, { useEffect, useState } from 'react';
import { Network, Play } from 'lucide-react';
import { api } from '../services/api';
import { DetectionFinding } from '../types';
import { useAuth } from '../context/AuthContext';
import { TransactionGraph } from '../components/TransactionGraph';

export const AmlPage: React.FC = () => {
  const { hasPermission } = useAuth();
  const [findings, setFindings] = useState<DetectionFinding[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<string>('');
  const [running, setRunning] = useState(false);

  const load = async () => {
    const res = await api.get('/aml/findings');
    const list = res.data.findings || [];
    setFindings(list);
    if (list.length > 0 && !selectedAccount) {
      setSelectedAccount(list[0].account_number || list[0].account_id || '');
    }
  };

  useEffect(() => { load(); }, []);

  const runAnalysis = async () => {
    setRunning(true);
    try {
      await api.post('/aml/analyse');
      await load();
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-white">AML & Network Pattern Intelligence</h1>
          <p className="text-xs text-slate-400">
            Detects circular flows, layering chains, structuring, rapid pass-through, and fan-in/fan-out hubs.
            Patterns are risk indicators, not proof of criminal activity.
          </p>
        </div>
        {hasPermission('aml:analyse') && (
          <button
            onClick={runAnalysis}
            disabled={running}
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold bg-violet-600 hover:bg-violet-500 text-white rounded-lg disabled:opacity-50"
          >
            <Play className="w-3.5 h-3.5" />
            {running ? 'Running AML Graph Scan...' : 'Run AML Analysis'}
          </button>
        )}
      </div>

      <TransactionGraph initialAccountId={selectedAccount} height="420px" />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {findings.map((f) => (
          <div
            key={f.id}
            onClick={() => setSelectedAccount(f.account_number || f.account_id || '')}
            className="tf-card rounded-xl p-4 space-y-2.5 cursor-pointer hover:border-violet-500/50 transition-colors"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Network className="w-4 h-4 text-violet-400" />
                <span className="text-sm font-semibold text-white capitalize">{f.finding_type.replace(/_/g, ' ')}</span>
              </div>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-violet-500/20 text-violet-300 border border-violet-500/30 font-semibold">
                AML Score: {f.risk_score.toFixed(1)}
              </span>
            </div>
            <p className="text-xs text-slate-200 leading-relaxed">{f.explanation}</p>
            {f.graph_path?.length > 0 && (
              <div className="text-[11px] font-mono text-sky-300 bg-navy-900 p-2 rounded border border-slate-800">
                Path: {f.graph_path.join(' → ')}
              </div>
            )}
            <div className="text-[11px] text-slate-400">Click card to inspect account network above • {f.algorithm}</div>
          </div>
        ))}
      </div>
    </div>
  );
};
