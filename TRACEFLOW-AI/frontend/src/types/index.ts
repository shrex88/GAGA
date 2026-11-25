export interface User {
  id: string;
  bank_id: string;
  email: string;
  full_name: string;
  roles: string[];
  permissions: string[];
  is_active: boolean;
}

export interface DashboardKPIs {
  total_transactions: number;
  total_accounts: number;
  suspicious_transactions: number;
  fraud_alerts: number;
  aml_alerts: number;
  high_risk_accounts: number;
  active_cases: number;
  avg_risk_score: number;
}

export interface TransactionItem {
  id: string;
  transaction_ref: string;
  source_account_id: string;
  source_account: string;
  destination_account_id: string;
  destination_account: string;
  amount: number;
  currency: string;
  timestamp: string;
  transaction_type: string;
  transaction_status: string;
  channel?: string;
  risk_score: number;
  risk_category: string;
  is_flagged: boolean;
  is_synthetic: boolean;
}

export interface DetectionFinding {
  id: string;
  engine: 'fraud' | 'aml';
  finding_type: string;
  transaction_id?: string;
  account_id?: string;
  account_number?: string;
  algorithm: string;
  model_version: string;
  risk_score: number;
  evidence_indicators: string[];
  graph_path: string[];
  explanation: string;
  shap_values?: Record<string, number>;
  detected_at: string;
}

export interface AlertItem {
  id: string;
  title: string;
  category: string;
  severity: string;
  status: string;
  risk_score: number;
  transaction_id?: string;
  account_id?: string;
  account_number?: string;
  assigned_to?: string;
  assigned_to_name?: string;
  resolution_reason?: string;
  supporting_evidence: Record<string, any>;
  created_at: string;
}

export interface InvestigationCaseItem {
  id: string;
  case_number: string;
  title: string;
  description?: string;
  priority: string;
  status: string;
  assigned_to?: string;
  assigned_to_name?: string;
  related_account_ids: string[];
  related_transaction_ids: string[];
  ai_summary?: string;
  created_at: string;
  updated_at: string;
}
