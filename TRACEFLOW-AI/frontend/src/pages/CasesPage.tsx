import React, { useEffect, useState } from 'react';
import { Briefcase, FileDown, Plus, Send } from 'lucide-react';
import { api } from '../services/api';
import { InvestigationCaseItem } from '../types';
import { useAuth } from '../context/AuthContext';

export const CasesPage: React.FC = () => {
  const { hasPermission } = useAuth();
  const [cases, setCases] = useState<InvestigationCaseItem[]>([]);
  const [selected, setSelected] = useState<any>(null);
  const [noteText, setNoteText] = useState('');
  const [isConclusion, setIsConclusion] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [showCreate, setShowCreate] = useState(false);

  const load = async () => {
    const res = await api.get('/cases');
    const list = res.data.cases || [];
    setCases(list);
    if (list.length > 0 && !selected) {
      openCase(list[0].id);
    }
  };

  useEffect(() => { load(); }, []);

  const openCase = async (id: string) => {
    const res = await api.get(`/cases/${id}`);
    setSelected(res.data);
  };

  const updateStatus = async (status: string) => {
    if (!selected) return;
    await api.patch(`/cases/${selected.case.id}`, { status });
    await openCase(selected.case.id);
    load();
  };

  const addNote = async () => {
    if (!selected || !noteText.trim()) return;
    await api.post(`/cases/${selected.case.id}/notes`, { content: noteText, is_conclusion: isConclusion });
    setNoteText('');
    setIsConclusion(false);
    openCase(selected.case.id);
  };

  const createCase = async () => {
    if (!newTitle.trim()) return;
    const res = await api.post('/cases', { title: newTitle, priority: 'High' });
    setNewTitle('');
    setShowCreate(false);
    await load();
    openCase(res.data.id);
  };

  const exportPdf = async () => {
    if (!selected) return;
    const res = await api.post('/reports/generate', { case_id: selected.case.id });
    const dl = await api.get(`/reports/${res.data.report_id}/download`, { responseType: 'blob' });
    const url = window.URL.createObjectURL(new Blob([dl.data], { type: 'application/pdf' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = res.data.filename;
    link.click();
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Investigation Cases</h1>
          <p className="text-xs text-slate-400">Manage case lifecycle, analyst conclusions, evidence timeline, and PDF exports</p>
        </div>
        {hasPermission('cases:write') && (
          <button onClick={() => setShowCreate(true)} className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white rounded-lg">
            <Plus className="w-4 h-4" /> New Case
          </button>
        )}
      </div>

      {showCreate && (
        <div className="tf-card rounded-xl p-4 flex gap-3 items-center">
          <input
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="Case title..."
            className="flex-1 px-3 py-2 text-xs bg-navy-900 border border-slate-700 rounded-lg text-white"
          />
          <button onClick={createCase} className="px-4 py-2 text-xs bg-blue-600 text-white rounded-lg">Create</button>
          <button onClick={() => setShowCreate(false)} className="px-3 py-2 text-xs bg-slate-800 rounded-lg">Cancel</button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="tf-card rounded-xl p-3 space-y-2 max-h-[650px] overflow-y-auto">
          {cases.length === 0 && <div className="text-xs text-slate-400 p-4 text-center">No cases yet. Convert an alert or create a case.</div>}
          {cases.map((c) => (
            <div
              key={c.id}
              onClick={() => openCase(c.id)}
              className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                selected?.case?.id === c.id
                  ? 'bg-indigo-600/20 border-indigo-500/50'
                  : 'bg-navy-900 border-slate-800 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center justify-between text-xs">
                <span className="font-mono text-sky-300">{c.case_number}</span>
                <span className="px-2 py-0.5 rounded bg-slate-800 text-[10px]">{c.status}</span>
              </div>
              <div className="text-xs font-semibold text-white mt-1">{c.title}</div>
              <div className="text-[11px] text-slate-400 mt-1">Priority: {c.priority}</div>
            </div>
          ))}
        </div>

        <div className="lg:col-span-2">
          {selected ? (
            <div className="tf-card rounded-xl p-5 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
                <div>
                  <div className="flex items-center gap-2">
                    <Briefcase className="w-4 h-4 text-indigo-400" />
                    <span className="font-mono text-xs text-sky-300">{selected.case.case_number}</span>
                    <h2 className="text-base font-bold text-white">{selected.case.title}</h2>
                  </div>
                  <div className="text-xs text-slate-400 mt-1">Assigned: {selected.case.assigned_to_name || 'Unassigned'}</div>
                </div>
                <div className="flex items-center gap-2">
                  {hasPermission('cases:write') && (
                    <select
                      value={selected.case.status}
                      onChange={(e) => updateStatus(e.target.value)}
                      className="px-3 py-1.5 text-xs bg-navy-900 border border-slate-700 rounded-lg text-white"
                    >
                      <option value="Open">Open</option>
                      <option value="Under Investigation">Under Investigation</option>
                      <option value="Escalated">Escalated</option>
                      <option value="Resolved">Resolved</option>
                      <option value="Closed">Closed</option>
                    </select>
                  )}
                  {hasPermission('reports:write') && (
                    <button onClick={exportPdf} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg">
                      <FileDown className="w-3.5 h-3.5" /> Export PDF
                    </button>
                  )}
                </div>
              </div>

              {selected.case.ai_summary && (
                <div className="tf-card-accent rounded-lg p-3 text-xs space-y-1">
                  <div className="font-semibold text-indigo-300">Algorithmic Evidence Summary (Non-Legal)</div>
                  <p className="text-slate-200">{selected.case.ai_summary}</p>
                </div>
              )}

              <div className="space-y-2">
                <div className="text-xs font-semibold text-slate-300">Evidence Items ({selected.evidence.length})</div>
                {selected.evidence.map((ev: any) => (
                  <div key={ev.id} className="p-2.5 rounded bg-navy-900 border border-slate-800 text-xs">
                    <div className="font-medium text-sky-300">{ev.title} <span className="text-slate-500">({ev.evidence_type})</span></div>
                  </div>
                ))}
              </div>

              <div className="space-y-2">
                <div className="text-xs font-semibold text-slate-300">Analyst Notes & Timeline ({selected.notes.length})</div>
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {selected.notes.map((n: any) => (
                    <div key={n.id} className="p-2.5 rounded bg-navy-900 border border-slate-800 text-xs space-y-1">
                      <div className="flex justify-between text-[11px] text-slate-400">
                        <span className="font-semibold text-slate-200">{n.author_name} {n.is_conclusion && '• [ANALYST CONCLUSION]'}</span>
                        <span>{new Date(n.created_at).toLocaleString()}</span>
                      </div>
                      <p className="text-slate-200">{n.content}</p>
                    </div>
                  ))}
                </div>

                {hasPermission('cases:write') && (
                  <div className="pt-2 space-y-2">
                    <textarea
                      value={noteText}
                      onChange={(e) => setNoteText(e.target.value)}
                      rows={2}
                      placeholder="Add investigation note or analyst conclusion..."
                      className="w-full p-2.5 text-xs bg-navy-900 border border-slate-700 rounded-lg text-white"
                    />
                    <div className="flex items-center justify-between">
                      <label className="flex items-center gap-2 text-xs text-slate-300">
                        <input type="checkbox" checked={isConclusion} onChange={(e) => setIsConclusion(e.target.checked)} />
                        Mark as Formal Analyst Conclusion
                      </label>
                      <button onClick={addNote} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-500 text-white rounded-lg">
                        <Send className="w-3.5 h-3.5" /> Add Note
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="tf-card rounded-xl p-8 text-center text-xs text-slate-400">Select a case to inspect details</div>
          )}
        </div>
      </div>
    </div>
  );
};
