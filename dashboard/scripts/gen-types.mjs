import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { compileFromFile } from 'json-schema-to-typescript';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const contractsDir = path.resolve(__dirname, '../../contracts');
const outDir = path.resolve(__dirname, '../src/types');

if (!fs.existsSync(outDir)) {
  fs.mkdirSync(outDir, { recursive: true });
}

async function generate() {
  const files = fs.readdirSync(contractsDir).filter(f => f.endsWith('.schema.json'));
  let tsOutput = `/**
 * Generated TypeScript contracts from contracts/*.schema.json.
 * DO NOT EDIT MANUALLY.
 */\n\n`;

  for (const file of files) {
    const fullPath = path.join(contractsDir, file);
    const schemaName = file.replace('.schema.json', '');
    // PascalCase name
    const typeName = schemaName
      .split('_')
      .map(part => part.charAt(0).toUpperCase() + part.slice(1))
      .join('');

    try {
      const compiled = await compileFromFile(fullPath, {
        bannerComment: '',
        cwd: contractsDir,
        declareExternallyReferenced: true,
        style: { singleQuote: true },
      });
      tsOutput += `/* === ${file} === */\n${compiled}\n\n`;
      console.log(`Compiled ${file} -> ${typeName}`);
    } catch (err) {
      console.error(`Failed to compile ${file}:`, err);
    }
  }

  // Also add composite UI types for frontend state
  tsOutput += `
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
`;

  const targetPath = path.join(outDir, 'contracts.ts');
  fs.writeFileSync(targetPath, tsOutput, 'utf-8');
  console.log(`Generated types successfully at: ${targetPath}`);
}

generate();
