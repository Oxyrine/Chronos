/**
 * Generated TypeScript contracts from contracts/*.schema.json.
 * DO NOT EDIT MANUALLY.
 */

/* === anomaly_alert.schema.json === */
export interface AnomalyAlert {
  ts: string;
  client: string;
  window_s: number;
  recon_error: number;
  threshold: number;
  top_features: string[];
  engine: string;
  [k: string]: unknown;
}


/* === attestation.schema.json === */
export interface Attestation {
  seq: number;
  ts: string;
  proposal_id: string;
  approved_by: string;
  verification_sha256: string;
  cbom_sha256: string;
  prev_hash: string;
  alg: 'ML-DSA-65';
  sig_b64: string;
  [k: string]: unknown;
}


/* === cbom_component.schema.json === */
export interface CbomComponent {
  type: 'cryptographic-asset';
  'bom-ref': string;
  name: string;
  cryptoProperties: {
    assetType: 'algorithm' | 'protocol' | 'certificate' | 'related-crypto-material';
    [k: string]: unknown;
  };
  evidence?: {
    occurrences: {
      location: string;
      line?: number;
      [k: string]: unknown;
    }[];
    [k: string]: unknown;
  };
  properties: {
    name: string;
    value: string;
    [k: string]: unknown;
  }[];
  [k: string]: unknown;
}


/* === client_mix.schema.json === */
export interface ClientMix {
  mix?: {
    hybrid_capable: number;
    legacy: number;
    [k: string]: unknown;
  };
  q: {
    [k: string]: number;
  };
  [k: string]: unknown;
}


/* === exposure.schema.json === */
export interface Exposure {
  channel: string;
  store_table: string;
  scenario: string;
  x_years: number;
  y_years: number;
  z_years: number;
  margin: number;
  exposed: boolean;
  kex_class: 'classical' | 'hybrid' | 'pq';
  classical_share: number;
  records: number;
  priority: number;
  driving_finding: string;
  [k: string]: unknown;
}


/* === finding.schema.json === */
export interface Finding {
  finding_id: string;
  bom_ref: string;
  asset_type: 'algorithm' | 'protocol' | 'certificate' | 'related-crypto-material';
  usage: 'key_exchange' | 'encryption' | 'signature' | 'hash' | 'symmetric' | 'protocol';
  algorithm: string;
  params: {
    [k: string]: unknown;
  };
  quantum_status: 'vulnerable' | 'weakened' | 'resistant';
  classical_weak: boolean;
  service: string;
  channels: string[];
  location: {
    path: string;
    line?: number;
    [k: string]: unknown;
  };
  fix_class: 'config' | 'library' | 'code_change' | 'vendor' | 'hardware';
  /**
   * @minItems 1
   */
  sources: [string, ...string[]];
  confidence: number;
  [k: string]: unknown;
}


/* === ground_truth.schema.json === */
export interface GroundTruth {
  assets: {
    id: string;
    path: string;
    line?: number;
    asset_type: string;
    algorithm: string;
    params?: {
      [k: string]: unknown;
    };
    quantum_status: 'vulnerable' | 'weakened' | 'resistant';
    [k: string]: unknown;
  }[];
  [k: string]: unknown;
}


/* === metrics.schema.json === */
export interface Metrics {
  synthetic: true;
  measured_at: string;
  discovery?: {
    [k: string]: unknown;
  };
  shelflife?: {
    [k: string]: unknown;
  };
  exposure?: {
    [k: string]: unknown;
  };
  performance?: {
    [k: string]: unknown;
  };
  [k: string]: unknown;
}


/* === patch_proposal.schema.json === */
export interface PatchProposal {
  proposal_id: string;
  finding_id: string;
  template_id: 'T1_nginx_hybrid_groups' | 'T2_sshd_hybrid_kex' | 'T3_client_tls_groups' | 'T4_mtls_mldsa';
  params: {
    [k: string]: unknown;
  };
  rationale: string;
  compatibility_risk: 'low' | 'medium' | 'high';
  requires_human: true;
  model: string;
  [k: string]: unknown;
}


/* === shelflife_prediction.schema.json === */
export interface ShelflifePrediction {
  store: string;
  table: string;
  column: string;
  category:
    | 'genetic'
    | 'child_health'
    | 'clinical'
    | 'identity'
    | 'financial'
    | 'contact'
    | 'pseudonymous_id'
    | 'scheduling'
    | 'auth_secret'
    | 'non_sensitive';
  policy_years: number;
  policy_version: string;
  probabilities: {
    [k: string]: number;
  };
  decided_by: 'model' | 'llm' | 'override';
  top_features: string[];
  model_version: string;
  override: {
    [k: string]: unknown;
  } | null;
  [k: string]: unknown;
}


/* === tls_event.schema.json === */
export interface TlsEvent {
  ts: string;
  client: string;
  uri: string;
  bytes: number;
  proto: string;
  group: string;
  kex_class: 'classical' | 'hybrid' | 'pq';
  store: string;
  records_est: number;
  [k: string]: unknown;
}


/* === topology.schema.json === */
export interface Topology {
  channels: {
    id: string;
    src: string;
    dst: string;
    protocol: 'tls' | 'ssh';
    port?: number;
    reach: 'internet' | 'partner' | 'internal';
    tables: string[];
    [k: string]: unknown;
  }[];
  tables: {
    [k: string]: {
      records: number;
      store?: string;
      mean_record_bytes?: number;
      [k: string]: unknown;
    };
  };
  [k: string]: unknown;
}


/* === verification_result.schema.json === */
export interface VerificationResult {
  proposal_id: string;
  status: 'passed' | 'failed';
  checks: {
    name: string;
    passed: boolean;
    evidence: string;
    [k: string]: unknown;
  }[];
  diff_sha256: string;
  log_path: string;
  duration_s: number;
  [k: string]: unknown;
}



/* === Composite Frontend UI Types === */

export interface UserSession {
  sub: string;
  role: 'viewer' | 'security_engineer';
}

export interface SystemHealth {
  status: string;
  arch: string;
  nnpa: boolean;
  tls_groups: string[];
}

export interface RankedFinding extends Finding {
  priority: number;
  method?: string;
  fingerprint?: string;
}

export interface ProposalRecord {
  proposal: PatchProposal;
  finding?: Finding;
  target?: string;
  diff?: string;
  rendered?: string;
  state: 'proposed' | 'verified_awaiting_approval' | 'verification_failed' | 'approved' | 'apply_failed' | 'rollback_failed' | 'sample';
  latency_s?: number;
  original_sha256?: string;
  diff_sha256?: string;
}

export interface ExposureResponse {
  scenario: string;
  exposures: (Exposure & { driving_column?: string })[];
  E: number;
  already_sent: Record<string, { R: number; classical_route_open?: boolean; sessions?: number }>;
  client_mix_measured: boolean;
  note?: string;
}

export interface LedgerChainVerification {
  chain_ok: boolean | null;
  bad_seq: number | null;
  mode?: string;
  detail?: string;
}
