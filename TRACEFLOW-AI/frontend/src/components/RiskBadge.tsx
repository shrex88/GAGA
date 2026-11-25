import React from 'react';

const STYLE_MAP: Record<string, string> = {
  Critical: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
  High: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  Moderate: 'bg-sky-500/20 text-sky-300 border-sky-500/40',
  Low: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
};

export const RiskBadge: React.FC<{ category: string; score?: number }> = ({ category, score }) => {
  const cls = STYLE_MAP[category] || 'bg-slate-700/40 text-slate-300 border-slate-600';
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${cls}`}>
      <span>{category}</span>
      {score !== undefined && <span className="opacity-80">({score.toFixed(0)})</span>}
    </span>
  );
};
