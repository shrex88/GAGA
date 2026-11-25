import React, { useEffect, useState } from 'react';
import { FileDown, FileText } from 'lucide-react';
import { api } from '../services/api';
import { useAuth } from '../context/AuthContext';

export const ReportsPage: React.FC = () => {
  const { hasPermission } = useAuth();
  const [reports, setReports] = useState<any[]>([]);
  const [cases, setCases] = useState<any[]>([]);
  const [selectedCase, setSelectedCase] = useState('');
  const [title, setTitle] = useState('');

  const load = async () => {
    const [rRes, cRes] = await Promise.all([api.get('/reports'), api.get('/cases')]);
    setReports(rRes.data.reports || []);
    setCases(cRes.data.cases || []);
  };

  useEffect(() => { load(); }, []);

  const generate = async () => {
    await api.post('/reports/generate', {
      case_id: selectedCase || undefined,
      title: title || undefined,
    });
    setTitle('');
    load();
  };

  const download = async (id: string, filename: string) => {
    const dl = await api.get(`/reports/${id}/download`, { responseType: 'blob' });
    const url = window.URL.createObjectURL(new Blob([dl.data], { type: 'application/pdf' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-white">Intelligence & Compliance Reports (PDF)</h1>
        <p className="text-xs text-slate-400">Generate downloadable PDF reports separating algorithmic indicators from analyst conclusions</p>
      </div>

      {hasPermission('reports:write') && (
        <div className="tf-card rounded-xl p-4 flex flex-wrap gap-3 items-center">
          <select value={selectedCase} onChange={(e) => setSelectedCase(e.target.value)} className="px-3 py-2 text-xs bg-navy-900 border border-slate-700 rounded-lg">
            <option value="">General Bank Intelligence Summary</option>
            {cases.map((c) => (
              <option key={c.id} value={c.id}>{c.case_number} — {c.title}</option>
            ))}
          </select>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Optional custom report title..."
            className="flex-1 min-w-[200px] px-3 py-2 text-xs bg-navy-900 border border-slate-700 rounded-lg"
          />
          <button onClick={generate} className="px-4 py-2 text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white rounded-lg">
            Generate PDF Report
          </button>
        </div>
      )}

      <div className="tf-card rounded-xl p-4 space-y-2.5">
        {reports.length === 0 && <div className="text-xs text-slate-400 text-center py-6">No reports generated in this session yet.</div>}
        {reports.map((r) => (
          <div key={r.report_id} className="flex items-center justify-between p-3 rounded-lg bg-navy-900 border border-slate-800 text-xs">
            <div className="flex items-center gap-2.5">
              <FileText className="w-4 h-4 text-emerald-400" />
              <div>
                <div className="font-semibold text-white">{r.title}</div>
                <div className="text-[11px] text-slate-400">{r.filename} • {new Date(r.generated_at).toLocaleString()}</div>
              </div>
            </div>
            <button onClick={() => download(r.report_id, r.filename)} className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg">
              <FileDown className="w-3.5 h-3.5" /> Download PDF
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};
