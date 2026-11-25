import React, { useEffect, useState } from 'react';
import { Database, Sparkles, Upload } from 'lucide-react';
import { api } from '../services/api';
import { useAuth } from '../context/AuthContext';

export const DataManagementPage: React.FC = () => {
  const { hasPermission } = useAuth();
  const [datasets, setDatasets] = useState<any[]>([]);
  const [seedCount, setSeedCount] = useState(1000);
  const [seedNum, setSeedNum] = useState(42);
  const [seeding, setSeeding] = useState(false);

  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<any>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<any>(null);
  const [error, setError] = useState('');

  const loadDatasets = async () => {
    const res = await api.get('/datasets');
    setDatasets(res.data.datasets || []);
  };

  useEffect(() => { loadDatasets(); }, []);

  const handleSeed = async () => {
    setSeeding(true);
    setError('');
    try {
      await api.post('/datasets/seed-synthetic', { count: seedCount, seed: seedNum, run_analysis: true });
      await loadDatasets();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Synthetic generation failed');
    } finally {
      setSeeding(false);
    }
  };

  const handleFileSelect = async (f: File | null) => {
    setFile(f);
    setUploadResult(null);
    setPreview(null);
    if (!f) return;
    const fd = new FormData();
    fd.append('file', f);
    try {
      const res = await api.post('/datasets/preview', fd);
      setPreview(res.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to preview CSV');
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError('');
    const fd = new FormData();
    fd.append('file', file);
    fd.append('run_analysis', 'true');
    try {
      const res = await api.post('/datasets/upload', fd);
      setUploadResult(res.data.import_result);
      await loadDatasets();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'CSV upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-white">Data Management & Ingestion</h1>
        <p className="text-xs text-slate-400">Upload validated CSV transaction batches or generate reproducible synthetic banking datasets</p>
      </div>

      {error && <div className="text-xs text-rose-300 bg-rose-500/10 border border-rose-500/30 rounded-lg p-3">{error}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Synthetic Generator */}
        <div className="tf-card rounded-xl p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-indigo-400" />
            <h2 className="text-sm font-semibold text-white">Synthetic Dataset Generator</h2>
          </div>
          <p className="text-xs text-slate-400">
            Generates normal transactions plus 8 labelled financial crime scenarios (circular, layering, structuring, mule, fan-in/out, amount & velocity anomalies).
          </p>
          <div className="flex flex-wrap gap-3">
            <select value={seedCount} onChange={(e) => setSeedCount(Number(e.target.value))} className="px-3 py-2 text-xs bg-navy-900 border border-slate-700 rounded-lg">
              <option value={1000}>1,000 Transactions</option>
              <option value={5000}>5,000 Transactions</option>
              <option value={10000}>10,000 Transactions</option>
            </select>
            <input
              type="number"
              value={seedNum}
              onChange={(e) => setSeedNum(Number(e.target.value))}
              placeholder="Seed"
              className="w-24 px-3 py-2 text-xs bg-navy-900 border border-slate-700 rounded-lg"
            />
            {hasPermission('datasets:write') && (
              <button
                onClick={handleSeed}
                disabled={seeding}
                className="px-4 py-2 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg"
              >
                {seeding ? 'Generating & Analysing...' : 'Generate & Run Engines'}
              </button>
            )}
          </div>
        </div>

        {/* CSV Upload */}
        <div className="tf-card rounded-xl p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Upload className="w-4 h-4 text-sky-400" />
            <h2 className="text-sm font-semibold text-white">CSV Transaction Batch Upload</h2>
          </div>
          <input
            type="file"
            accept=".csv"
            onChange={(e) => handleFileSelect(e.target.files?.[0] || null)}
            className="block w-full text-xs text-slate-300 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-slate-800 file:text-sky-300"
          />
          {preview && (
            <div className="text-xs bg-navy-900 border border-slate-800 rounded-lg p-3 space-y-2">
              <div className="text-sky-300 font-medium">
                Preview: {preview.total_rows_detected} rows detected • Columns: {preview.headers.join(', ')}
              </div>
              {hasPermission('datasets:write') && (
                <button
                  onClick={handleUpload}
                  disabled={uploading}
                  className="px-4 py-2 text-xs font-semibold bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg"
                >
                  {uploading ? 'Validating & Importing...' : 'Validate, Import & Analyse'}
                </button>
              )}
            </div>
          )}
          {uploadResult && (
            <div className="text-xs bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-3 space-y-1">
              <div className="font-semibold text-emerald-300">Import Summary ({uploadResult.status})</div>
              <div>Accepted: {uploadResult.accepted_rows} | Rejected: {uploadResult.rejected_rows} | Duplicates: {uploadResult.duplicate_rows}</div>
            </div>
          )}
        </div>
      </div>

      {/* Import History */}
      <div className="tf-card rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-800 flex items-center gap-2 text-sm font-semibold text-white">
          <Database className="w-4 h-4 text-sky-400" /> Dataset Import History
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-navy-900 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="text-left px-4 py-2.5">Name</th>
                <th className="text-left px-4 py-2.5">Status</th>
                <th className="text-right px-4 py-2.5">Accepted</th>
                <th className="text-right px-4 py-2.5">Rejected</th>
                <th className="text-left px-4 py-2.5">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {datasets.map((d) => (
                <tr key={d.id}>
                  <td className="px-4 py-2.5 text-white">{d.name}</td>
                  <td className="px-4 py-2.5 uppercase text-sky-300">{d.status}</td>
                  <td className="px-4 py-2.5 text-right text-emerald-300">{d.accepted_rows}</td>
                  <td className="px-4 py-2.5 text-right text-rose-300">{d.rejected_rows}</td>
                  <td className="px-4 py-2.5 text-slate-400">{new Date(d.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
