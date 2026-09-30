export type Patient = { subject_id: number; gender: string; anchor_age: number; admission_count: number | null; latest_discharge_at: string | null; [key: string]: unknown };
export type Evidence = { document_id: string; text: string; score: number; metadata: { source: string; hadm_id: number; subject_id: number } };
export type QualityResult = { run_id: string; dataset: string; rule: string; status: string; severity: string; records_checked: number; records_failed: number; failure_percentage: number; execution_timestamp: string };
export type OperationsSummary = {
  pipeline: { run_id: string; status: string; started_at: string; completed_at: string; duration_seconds: number; engine: string; profiles: Array<{ dataset: string; layer: string; rows: number; columns: number }> };
  model: { run_id: string; trained_at: string; threshold: number; duration_seconds: number; metrics: Record<string, number>; splits: Record<string, { rows: number; patients: number; positives: number }> };
  retrieval: { evaluation: Record<string, number>; index: { model: string; documents: number; dimensions: number; build_seconds: number } };
};
export type Prediction = { risk_probability: number; risk_level: string; threshold: number; model_run_id: string; disclaimer: string };
export type AgentResponse = { answer: string; grounded: boolean; citations: Array<Record<string, string | number>>; tools_executed: string[]; audit_id: string };
export type EpicStatus = { provider: string; standard: string; enabled: boolean; configured: boolean; fhir_base_url: string; live_phi_allowed: boolean; compliance_status: string };
