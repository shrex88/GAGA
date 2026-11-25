import React, { useEffect, useRef, useState } from 'react';
import cytoscape from 'cytoscape';
import { api } from '../services/api';
import { GitBranch, RefreshCw, Search, ShieldAlert } from 'lucide-react';
import { RiskBadge } from './RiskBadge';

interface Props {
  initialAccountId?: string;
  height?: string;
}

export const TransactionGraph: React.FC<Props> = ({ initialAccountId, height = '480px' }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);

  const [accountQuery, setAccountQuery] = useState(initialAccountId || '');
  const [hops, setHops] = useState(2);
  const [minAmount, setMinAmount] = useState('');
  const [graphData, setGraphData] = useState<any>(null);
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [selectedEdge, setSelectedEdge] = useState<any>(null);
  const [tracePaths, setTracePaths] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const loadGraph = async (targetId: string, hopCount = hops) => {
    if (!targetId) return;
    setLoading(true);
    setError('');
    setSelectedNode(null);
    setSelectedEdge(null);
    try {
      const params: any = { hops: hopCount };
      if (minAmount) params.min_amount = Number(minAmount);
      const [netRes, traceRes] = await Promise.all([
        api.get(`/graph/account/${encodeURIComponent(targetId)}`, { params }),
        api.get(`/graph/trace/${encodeURIComponent(targetId)}`, { params: { max_hops: Math.max(2, hopCount) } }),
      ]);
      setGraphData(netRes.data);
      setTracePaths(traceRes.data.paths || []);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load transaction graph');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (initialAccountId) {
      setAccountQuery(initialAccountId);
      loadGraph(initialAccountId, hops);
    }
  }, [initialAccountId]);

  useEffect(() => {
    if (!containerRef.current || !graphData) return;

    if (cyRef.current) {
      cyRef.current.destroy();
    }

    const cy = cytoscape({
      container: containerRef.current,
      elements: [...(graphData.nodes || []), ...(graphData.edges || [])],
      style: [
        {
          selector: 'node',
          style: {
            'background-color': (ele: any) => {
              const cat = ele.data('risk_category');
              if (cat === 'Critical') return '#e11d48';
              if (cat === 'High') return '#f59e0b';
              if (cat === 'Moderate') return '#0ea5e9';
              return '#1e293b';
            },
            'border-width': (ele: any) => (ele.data('is_center') ? 3 : ele.data('in_cycle') ? 2.5 : 1.5),
            'border-color': (ele: any) => (ele.data('is_center') ? '#818cf8' : ele.data('in_cycle') ? '#fb7185' : '#475569'),
            label: 'data(label)',
            color: '#e2e8f0',
            'font-size': '10px',
            'text-valign': 'bottom',
            'text-margin-y': 5,
            width: (ele: any) => (ele.data('is_center') ? 40 : 28),
            height: (ele: any) => (ele.data('is_center') ? 40 : 28),
          },
        },
        {
          selector: 'edge',
          style: {
            width: (ele: any) => (ele.data('is_cycle_edge') || ele.data('is_flagged') ? 2.8 : 1.4),
            'line-color': (ele: any) => (ele.data('is_cycle_edge') ? '#f43f5e' : ele.data('is_flagged') ? '#f59e0b' : '#3b82f6'),
            'target-arrow-color': (ele: any) => (ele.data('is_cycle_edge') ? '#f43f5e' : ele.data('is_flagged') ? '#f59e0b' : '#3b82f6'),
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            label: 'data(label)',
            'font-size': '9px',
            color: '#94a3b8',
            'text-background-color': '#050914',
            'text-background-opacity': 0.8,
            'text-background-padding': '2px',
          },
        },
      ],
      layout: { name: 'cose', animate: false, padding: 30 },
    });

    cy.on('tap', 'node', (evt) => {
      setSelectedEdge(null);
      setSelectedNode(evt.target.data());
    });
    cy.on('tap', 'edge', (evt) => {
      setSelectedNode(null);
      setSelectedEdge(evt.target.data());
    });

    cyRef.current = cy;
    return () => {
      cy.destroy();
    };
  }, [graphData]);

  return (
    <div className="tf-card rounded-xl p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <GitBranch className="w-5 h-5 text-indigo-400" />
          <h3 className="text-sm font-semibold text-slate-100">Interactive Transaction Network (Cytoscape)</h3>
          {graphData && (
            <span className="text-xs px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
              {graphData.backend_mode} • {graphData.stats?.node_count} nodes • {graphData.stats?.edge_count} edges
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
            <input
              value={accountQuery}
              onChange={(e) => setAccountQuery(e.target.value)}
              placeholder="Account ID or Number"
              className="pl-8 pr-3 py-1.5 text-xs bg-navy-900 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-indigo-500"
            />
          </div>
          <select
            value={hops}
            onChange={(e) => setHops(Number(e.target.value))}
            className="px-2.5 py-1.5 text-xs bg-navy-900 border border-slate-700 rounded-lg text-slate-100"
          >
            <option value={2}>2 Hops</option>
            <option value={3}>3 Hops</option>
            <option value={4}>4 Hops</option>
            <option value={5}>5 Hops</option>
          </select>
          <input
            value={minAmount}
            onChange={(e) => setMinAmount(e.target.value)}
            placeholder="Min $"
            type="number"
            className="w-24 px-2.5 py-1.5 text-xs bg-navy-900 border border-slate-700 rounded-lg text-slate-100"
          />
          <button
            onClick={() => loadGraph(accountQuery, hops)}
            disabled={loading || !accountQuery}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Load Graph
          </button>
        </div>
      </div>

      {error && <div className="text-xs text-rose-400 bg-rose-500/10 border border-rose-500/30 rounded-lg p-2.5">{error}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-3">
        <div
          ref={containerRef}
          style={{ height }}
          className="lg:col-span-3 rounded-lg bg-[#050914] border border-slate-800/80 relative"
        />

        <div className="space-y-3 text-xs">
          {selectedNode && (
            <div className="p-3 rounded-lg bg-navy-900 border border-slate-700/80 space-y-2">
              <div className="font-semibold text-indigo-300">Selected Account</div>
              <div><span className="text-slate-400">Number:</span> {selectedNode.account_number}</div>
              <div><span className="text-slate-400">Type:</span> {selectedNode.account_type}</div>
              <div><span className="text-slate-400">Balance:</span> ${Number(selectedNode.balance).toLocaleString()}</div>
              <div className="flex items-center gap-2">
                <span className="text-slate-400">Risk:</span>
                <RiskBadge category={selectedNode.risk_category} score={selectedNode.risk_score} />
              </div>
              <div><span className="text-slate-400">In/Out Degree:</span> {selectedNode.in_degree} / {selectedNode.out_degree}</div>
              <button
                onClick={() => {
                  setAccountQuery(selectedNode.account_number);
                  loadGraph(selectedNode.account_number, hops);
                }}
                className="w-full mt-1 py-1.5 bg-indigo-600/80 hover:bg-indigo-500 rounded text-white font-medium"
              >
                Expand From This Account
              </button>
            </div>
          )}

          {selectedEdge && (
            <div className="p-3 rounded-lg bg-navy-900 border border-slate-700/80 space-y-1.5">
              <div className="font-semibold text-sky-300">Selected Transfer</div>
              <div><span className="text-slate-400">Ref:</span> {selectedEdge.transaction_ref}</div>
              <div><span className="text-slate-400">Amount:</span> ${Number(selectedEdge.amount).toLocaleString()} {selectedEdge.currency}</div>
              <div><span className="text-slate-400">Type:</span> {selectedEdge.transaction_type}</div>
              <div><span className="text-slate-400">Time:</span> {new Date(selectedEdge.timestamp).toLocaleString()}</div>
              <div><span className="text-slate-400">Risk Score:</span> {selectedEdge.risk_score}</div>
            </div>
          )}

          {graphData?.cycles?.length > 0 && (
            <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 space-y-1.5">
              <div className="flex items-center gap-1.5 font-semibold text-rose-300">
                <ShieldAlert className="w-4 h-4" />
                Circular Paths ({graphData.cycles.length})
              </div>
              {graphData.cycles.slice(0, 4).map((c: string[], i: number) => (
                <div key={i} className="text-[11px] text-rose-200 break-all">
                  {c.join(' → ')} → {c[0]}
                </div>
              ))}
            </div>
          )}

          {tracePaths.length > 0 && (
            <div className="p-3 rounded-lg bg-navy-900 border border-slate-800 space-y-1.5 max-h-48 overflow-y-auto">
              <div className="font-semibold text-slate-200">Multi-Hop Fund Traces</div>
              {tracePaths.slice(0, 5).map((p, i) => (
                <div key={i} className="text-[11px] text-slate-300 border-b border-slate-800 pb-1">
                  <span className="text-indigo-400 font-medium">{p.hops} hops</span> (${Number(p.min_hop_amount).toLocaleString()}):{' '}
                  {p.account_numbers.join(' → ')}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
