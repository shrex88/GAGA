import React, { useEffect, useState } from 'react';
import { Search, ChevronLeft, ChevronRight, X } from 'lucide-react';
import { api } from '../services/api';
import { TransactionItem } from '../types';
import { RiskBadge } from '../components/RiskBadge';

export const TransactionsPage: React.FC = () => {
  const [items, setItems] = useState<TransactionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [riskCategory, setRiskCategory] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [minAmount, setMinAmount] = useState('');
  const [sortBy, setSortBy] = useState('timestamp');
  const [sortDir, setSortDir] = useState('desc');
  const [selectedDetail, setSelectedDetail] = useState<any>(null);

  const load = async () => {
    const params: any = { page, page_size: 20, sort_by: sortBy, sort_dir: sortDir };
    if (search) params.search = search;
    if (riskCategory) params.risk_category = riskCategory;
    if (statusFilter) params.status = statusFilter;
    if (minAmount) params.min_amount = Number(minAmount);
    const res = await api.get('/transactions', { params });
    setItems(res.data.items || []);
    setTotal(res.data.total || 0);
  };

  useEffect(() => {
    load();
  }, [page, riskCategory, statusFilter, sortBy, sortDir]);

  const openDetail = async (id: string) => {
    const res = await api.get(`/transactions/${id}`);
    setSelectedDetail(res.data);
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold text-white">Transaction Explorer</h1>
        <p className="text-xs text-slate-400">Search, filter, and inspect transaction risk indicators and Explainable AI attributions</p>
      </div>

      {/* Filters */}
      <div className="tf-card rounded-xl p-4 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && (setPage(1), load())}
            placeholder="Search Transaction Ref or Account..."
            className="w-full pl-9 pr-3 py-2 text-xs bg-navy-900 border border-slate-700 rounded-lg text-white"
          />
        </div>
        <select
          value={riskCategory}
          onChange={(e) => { setRiskCategory(e.target.value); setPage(1); }}
          className="px-3 py-2 text-xs bg-navy-900 border border-slate-700 rounded-lg text-slate-100"
        >
          <option value="">All Risk Categories</option>
          <option value="Critical">Critical</option>
          <option value="High">High</option>
          <option value="Moderate">Moderate</option>
          <option value="Low">Low</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
          className="px-3 py-2 text-xs bg-navy-900 border border-slate-700 rounded-lg text-slate-100"
        >
          <option value="">All Statuses</option>
          <option value="completed">Completed</option>
          <option value="pending">Pending</option>
          <option value="flagged">Flagged</option>
        </select>
        <input
          value={minAmount}
          onChange={(e) => setMinAmount(e.target.value)}
          placeholder="Min Amount $"
          type="number"
          className="w-28 px-3 py-2 text-xs bg-navy-900 border border-slate-700 rounded-lg text-slate-100"
        />
        <select
          value={`${sortBy}:${sortDir}`}
          onChange={(e) => {
            const [sb, sd] = e.target.value.split(':');
            setSortBy(sb);
            setSortDir(sd);
          }}
          className="px-3 py-2 text-xs bg-navy-900 border border-slate-700 rounded-lg text-slate-100"
        >
          <option value="timestamp:desc">Newest First</option>
          <option value="risk_score:desc">Highest Risk</option>
          <option value="amount:desc">Highest Amount</option>
          <option value="amount:asc">Lowest Amount</option>
        </select>
        <button
          onClick={() => { setPage(1); load(); }}
          className="px-4 py-2 text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white rounded-lg"
        >
          Apply
        </button>
      </div>

      {/* Table */}
      <div className="tf-card rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-navy-900 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="text-left px-4 py-3">Transaction Ref</th>
                <th className="text-left px-4 py-3">Sender</th>
                <th className="text-left px-4 py-3">Receiver</th>
                <th className="text-right px-4 py-3">Amount</th>
                <th className="text-left px-4 py-3">Type</th>
                <th className="text-left px-4 py-3">Timestamp</th>
                <th className="text-right px-4 py-3">Risk</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {items.map((t) => (
                <tr
                  key={t.id}
                  onClick={() => openDetail(t.id)}
                  className="hover:bg-blue-500/10 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-2.5 font-mono text-sky-300">{t.transaction_ref}</td>
                  <td className="px-4 py-2.5 font-mono text-slate-200">{t.source_account}</td>
                  <td className="px-4 py-2.5 font-mono text-slate-200">{t.destination_account}</td>
                  <td className="px-4 py-2.5 text-right font-semibold">${t.amount.toLocaleString()} {t.currency}</td>
                  <td className="px-4 py-2.5 capitalize text-slate-300">{t.transaction_type}</td>
                  <td className="px-4 py-2.5 text-slate-400">{new Date(t.timestamp).toLocaleString()}</td>
                  <td className="px-4 py-2.5 text-right"><RiskBadge category={t.risk_category} score={t.risk_score} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="px-4 py-3 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
          <span>Showing {items.length} of {total} transactions</span>
          <div className="flex items-center gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="p-1.5 rounded bg-navy-900 border border-slate-700 disabled:opacity-40"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span>Page {page}</span>
            <button
              disabled={page * 20 >= total}
              onClick={() => setPage((p) => p + 1)}
              className="p-1.5 rounded bg-navy-900 border border-slate-700 disabled:opacity-40"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Transaction Detail Modal / Panel */}
      {selectedDetail && (
        <div className="fixed inset-0 z-50 bg-black/70 flex justify-end">
          <div className="w-full max-w-lg bg-[#0a1020] border-l border-slate-700 p-6 overflow-y-auto space-y-5">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-white">Transaction Intelligence Detail</h2>
              <button onClick={() => setSelectedDetail(null)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="tf-card rounded-lg p-4 space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-400">Reference</span>
                <span className="font-mono text-sky-300">{selectedDetail.transaction.transaction_ref}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Sender → Receiver</span>
                <span className="font-mono">{selectedDetail.transaction.source_account} → {selectedDetail.transaction.destination_account}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Amount</span>
                <span className="font-semibold text-white">${selectedDetail.transaction.amount.toLocaleString()} {selectedDetail.transaction.currency}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Risk Rating</span>
                <RiskBadge category={selectedDetail.transaction.risk_category} score={selectedDetail.transaction.risk_score} />
              </div>
            </div>

            {selectedDetail.xai_explanation && (
              <div className="tf-card-accent rounded-lg p-4 space-y-2 text-xs">
                <div className="font-semibold text-indigo-300">Explainable AI Summary</div>
                <p className="text-slate-200 leading-relaxed">{selectedDetail.xai_explanation.summary}</p>
                {selectedDetail.xai_explanation.recommended_actions?.length > 0 && (
                  <ul className="list-disc list-inside text-slate-300 space-y-1 pt-1">
                    {selectedDetail.xai_explanation.recommended_actions.map((a: string, i: number) => (
                      <li key={i}>{a}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            <div className="space-y-2">
              <div className="text-xs font-semibold text-slate-300">Related Detection Findings ({selectedDetail.findings.length})</div>
              {selectedDetail.findings.map((f: any) => (
                <div key={f.id} className="p-3 rounded-lg bg-navy-900 border border-slate-800 text-xs space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-amber-300 uppercase">{f.engine} • {f.finding_type.replace('_', ' ')}</span>
                    <span className="text-slate-400">{f.risk_score.toFixed(1)}/100</span>
                  </div>
                  <p className="text-slate-300">{f.explanation}</p>
                  <div className="text-[11px] text-slate-400">Algorithm: {f.algorithm} ({f.model_version})</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
