import React, { useEffect, useState } from 'react';
import { api } from '../services/api';

export const AuditLogsPage: React.FC = () => {
  const [logs, setLogs] = useState<any[]>([]);

  useEffect(() => {
    api.get('/audit/logs').then((res) => setLogs(res.data.logs || []));
  }, []);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold text-white">Audit Logs</h1>
        <p className="text-xs text-slate-400">Immutable compliance audit trail of user authentication, investigations, and configuration changes</p>
      </div>

      <div className="tf-card rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-navy-900 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="text-left px-4 py-2.5">Timestamp</th>
                <th className="text-left px-4 py-2.5">User</th>
                <th className="text-left px-4 py-2.5">Action</th>
                <th className="text-left px-4 py-2.5">Resource</th>
                <th className="text-left px-4 py-2.5">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {logs.map((l) => (
                <tr key={l.id}>
                  <td className="px-4 py-2.5 text-slate-400">{new Date(l.created_at).toLocaleString()}</td>
                  <td className="px-4 py-2.5 text-sky-300">{l.user_email || 'system'}</td>
                  <td className="px-4 py-2.5 font-mono text-white">{l.action}</td>
                  <td className="px-4 py-2.5 text-slate-300">{l.resource_type} ({l.resource_id})</td>
                  <td className="px-4 py-2.5 text-slate-400 font-mono truncate max-w-xs">{JSON.stringify(l.details)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
