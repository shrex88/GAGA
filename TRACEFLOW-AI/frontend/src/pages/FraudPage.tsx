import React, { useEffect, useState } from 'react';
import { Play, ShieldAlert } from 'lucide-react';
import { api } from '../services/api';
import { DetectionFinding } from '../types';
import { useAuth } from '../context/AuthContext';

export const FraudPage: React.FC = () => {
  const { hasPermission } = useAuth();
  const [findings, setFindings] = useState<DetectionFinding[]>([]);
  const [running, setRunning] = useState(false);

  const load = async () => {
    const res = await api.get('/fraud/findings');
    setFindings(res.data.findings || []);
  };

  useEffect(() => { load(); }, []);

  const runAnalysis = async () => {
    setRunning(true);
    try {
      await api.post('/fraud/analyse');
      await load();
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-white">Fraud Intelligence Engine</h1>
          <p className="text-xs text-slate-400">Isolation Forest anomaly detection, behavioral profiling, velocity & device indicators</p>
        </div>
        {hasPermission('fraud:analyse') && (
          <button
            onClick={runAnalysis}
            disabled={running}
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold bg-amber-600 hover:bg-amber-500 text-white rounded-lg disabled:opacity-50"
          >
            <Play className="w-3.5 h-3.5" />
            {running ? 'Running Fraud Pipeline...' : 'Run Fraud Analysis'}
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4">
        {findings.map((f) => (
          <div key={f.id} className="tf-card rounded-xl p-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-amber-400" />
                <span className="text-sm font-semibold text-white capitalize">{f.finding_type.replace(/_/g, ' ')}</span>
                <span className="text-xs font-mono text-sky-300">{f.account_number}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30 font-semibold">
                  Fraud Score: {f.risk_score.toFixed(1)} / 100
                </span>
                <span className="text-[11px] text-slate-400">{f.algorithm} ({f.model_version})</span>
              </div>
            </div>

            <p className="text-xs text-slate-200 leading-relaxed">{f.explanation}</p>

            <div className="flex flex-wrap gap-2">
              {f.evidence_indicators.map((ind, i) => (
                <span key={i} className="text-[11px] px-2.5 py-1 rounded bg-navy-900 border border-slate-700 text-slate-300">
                  {ind}
                </span>
              ))}
            </div>

            {f.shap_values && Object.keys(f.shap_values).length > 0 && (
              <div className="pt-2 border-t border-slate-800/80">
                <div className="text-[11px] text-slate-400 mb-1.5">Feature Attribution (Standardized Deviation from Baseline):</div>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(f.shap_values)
                    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
                    .slice(0, 5)
                    .map(([k, v]) => (
                      <span key={k} className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-indigo-300">
                        {k}: {v > 0 ? `+${v}` : v}σ
                      </span>
                    ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
