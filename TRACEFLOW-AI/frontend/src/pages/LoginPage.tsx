import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldCheck, Lock, Mail } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const DEV_DEMO_PASSWORD = import.meta.env.VITE_DEMO_USER_PASSWORD || 'TraceflowDemo@2026!';

const DEMO_ACCOUNTS = [
  { label: 'Bank Admin', email: 'admin@traceflow.ai', pass: DEV_DEMO_PASSWORD },
  { label: 'Fraud Analyst', email: 'fraud@traceflow.ai', pass: DEV_DEMO_PASSWORD },
  { label: 'AML Investigator', email: 'aml@traceflow.ai', pass: DEV_DEMO_PASSWORD },
  { label: 'Auditor', email: 'auditor@traceflow.ai', pass: DEV_DEMO_PASSWORD },
];

function getRoleLandingRoute(roles: string[]): string {
  if (roles.includes('fraud_analyst')) return '/fraud';
  if (roles.includes('aml_investigator')) return '/aml';
  if (roles.includes('auditor')) return '/audit';
  return '/';
}

export const LoginPage: React.FC = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('admin@traceflow.ai');
  const [password, setPassword] = useState(DEV_DEMO_PASSWORD);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const authedUser = await login(email, password);
      navigate(getRoleLandingRoute(authedUser.roles || []));
    } catch (err: any) {
      const status = err.response?.status;
      if (!err.response || err.code === 'ERR_NETWORK' || status === 502 || status === 504) {
        setError('Backend API server is unreachable. Please ensure the TRACEFLOW AI backend is running on port 8000.');
      } else {
        setError(err.response?.data?.detail || 'Authentication failed. Please verify your credentials.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#050914] p-4 relative overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(37,99,235,0.18),transparent_60%)] pointer-events-none" />
      <div className="w-full max-w-md tf-card rounded-2xl p-7 space-y-6 relative z-10">
        <div className="text-center space-y-2">
          <div className="w-12 h-12 mx-auto rounded-xl bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center shadow-lg shadow-blue-900/50">
            <ShieldCheck className="w-7 h-7 text-white" />
          </div>
          <h1 className="text-xl font-bold text-white tracking-wide">TRACEFLOW AI</h1>
          <p className="text-xs text-slate-400">
            AI-Powered Financial Crime & Transaction Intelligence Platform
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-slate-300 mb-1.5">Institutional Email</label>
            <div className="relative">
              <Mail className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full pl-9 pr-3 py-2 text-sm bg-navy-900 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs text-slate-300 mb-1.5">Password</label>
            <div className="relative">
              <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full pl-9 pr-3 py-2 text-sm bg-navy-900 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          {error && (
            <div className="text-xs text-rose-300 bg-rose-500/10 border border-rose-500/30 rounded-lg p-2.5">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 rounded-lg bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-500 hover:to-violet-500 text-white text-sm font-semibold shadow-lg shadow-blue-900/30 disabled:opacity-60"
          >
            {loading ? 'Authenticating...' : 'Sign In to Platform'}
          </button>
        </form>

        <div className="pt-4 border-t border-slate-800 space-y-2">
          <div className="text-[11px] text-slate-400 text-center">Quick-Fill Demo Credentials</div>
          <div className="grid grid-cols-2 gap-2">
            {DEMO_ACCOUNTS.map((acc) => (
              <button
                key={acc.email}
                type="button"
                onClick={() => {
                  setEmail(acc.email);
                  setPassword(acc.pass);
                }}
                className="px-2.5 py-1.5 rounded-lg bg-navy-900 hover:bg-slate-800 border border-slate-700/80 text-[11px] text-slate-300 text-left transition-colors"
              >
                <div className="font-medium text-sky-300">{acc.label}</div>
                <div className="text-[10px] text-slate-500 truncate">{acc.email}</div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
