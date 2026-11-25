import React, { useEffect, useState } from 'react';
import { Save } from 'lucide-react';
import { api } from '../services/api';
import { useAuth } from '../context/AuthContext';

export const SettingsPage: React.FC = () => {
  const { hasPermission } = useAuth();
  const [config, setConfig] = useState<any>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.get('/settings/bank-config').then((res) => setConfig(res.data.config));
  }, []);

  const saveConfig = async () => {
    setSaved(false);
    await api.patch('/settings/bank-config', {
      scoring_weights: config.scoring_weights,
      risk_thresholds: config.risk_thresholds,
      aml_thresholds: config.aml_thresholds,
    });
    setSaved(true);
  };

  if (!config) return <div className="text-xs text-slate-400">Loading bank configuration...</div>;

  return (
    <div className="space-y-5 max-w-3xl">
      <div>
        <h1 className="text-xl font-bold text-white">Platform & Risk Scoring Settings</h1>
        <p className="text-xs text-slate-400">Configure unified risk weights and AML detection thresholds</p>
      </div>

      {saved && <div className="text-xs text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-3">Configuration saved and unified risk scores recomputed.</div>}

      <div className="tf-card rounded-xl p-5 space-y-4">
        <h2 className="text-sm font-semibold text-white">Unified Risk Scoring Weights</h2>
        <div className="grid grid-cols-3 gap-4 text-xs">
          {['fraud_weight', 'aml_weight', 'network_weight'].map((k) => (
            <div key={k}>
              <label className="block text-slate-400 mb-1 capitalize">{k.replace('_', ' ')}</label>
              <input
                type="number"
                step="0.05"
                value={config.scoring_weights?.[k] ?? 0}
                disabled={!hasPermission('settings:write')}
                onChange={(e) =>
                  setConfig({
                    ...config,
                    scoring_weights: { ...config.scoring_weights, [k]: Number(e.target.value) },
                  })
                }
                className="w-full px-3 py-2 bg-navy-900 border border-slate-700 rounded-lg text-white"
              />
            </div>
          ))}
        </div>

        <h2 className="text-sm font-semibold text-white pt-2">AML Detection Thresholds</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-xs">
          {Object.entries(config.aml_thresholds || {}).map(([k, v]) => (
            <div key={k}>
              <label className="block text-slate-400 mb-1">{k}</label>
              <input
                type="number"
                value={Number(v)}
                disabled={!hasPermission('settings:write')}
                onChange={(e) =>
                  setConfig({
                    ...config,
                    aml_thresholds: { ...config.aml_thresholds, [k]: Number(e.target.value) },
                  })
                }
                className="w-full px-3 py-2 bg-navy-900 border border-slate-700 rounded-lg text-white"
              />
            </div>
          ))}
        </div>

        {hasPermission('settings:write') && (
          <button onClick={saveConfig} className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white rounded-lg">
            <Save className="w-3.5 h-3.5" /> Save & Recompute Risk
          </button>
        )}
      </div>
    </div>
  );
};
