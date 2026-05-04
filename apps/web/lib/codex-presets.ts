export type CodexMode = "evtx" | "memory" | "disk" | "manifest" | "general";

export interface CodexPreset {
  id: string;
  title: string;
  mode: CodexMode;
  summary: string;
  prompt: string;
  placeholderEvidence?: string;
}

export const CODEX_MODE_LABELS: Record<CodexMode, string> = {
  evtx: "EVTX triage",
  memory: "Memory triage",
  disk: "Disk triage",
  manifest: "Manifest verify",
  general: "General operator",
};

export const CODEX_MODE_TOOL_ALLOWLIST: Record<
  CodexMode,
  { rust: string[]; agent: string[] }
> = {
  evtx: {
    rust: ["case_open", "evtx_query"],
    agent: [],
  },
  memory: {
    rust: ["case_open", "vol_pslist", "vol_psscan", "vol_psxview", "vol_malfind"],
    agent: [],
  },
  disk: {
    rust: [
      "case_open",
      "mft_timeline",
      "usnjrnl_query",
      "registry_query",
      "prefetch_parse",
    ],
    agent: [],
  },
  manifest: {
    rust: [],
    agent: ["audit_verify", "manifest_verify", "verify_finding"],
  },
  general: {
    rust: ["case_open", "evtx_query"],
    agent: ["audit_verify", "manifest_verify"],
  },
};

export const CODEX_PRESETS: CodexPreset[] = [
  {
    id: "evtx-first-look",
    title: "EVTX first look",
    mode: "evtx",
    summary: "Open one EVTX and inspect bounded parsed rows.",
    placeholderEvidence: "fixtures/single-evtx/Security.evtx",
    prompt:
      "Open the EVTX with case_open, run evtx_query with a conservative limit, and summarize row_count, records_seen, parse_errors, notable event IDs, and coverage limits. Treat any single-rule or anomaly hit as a triage lead only.",
  },
  {
    id: "memory-dkom",
    title: "Memory DKOM triage",
    mode: "memory",
    summary: "Compare process views for rootkit-shaped divergence.",
    placeholderEvidence: "test-forensics/extracted/<host>/<host>-memory.img",
    prompt:
      "Open the memory image and compare vol_pslist, vol_psscan, and vol_psxview before discussing DKOM or T1014. Run vol_malfind only as injection triage. Do not claim execution or compromise without corroboration.",
  },
  {
    id: "disk-custody",
    title: "Disk custody check",
    mode: "disk",
    summary: "Register a disk image and avoid content overclaims.",
    placeholderEvidence: "test-forensics/disk-images/<host>.E01",
    prompt:
      "Open the disk image for chain-of-custody and state exactly which disk artifacts are available for deeper analysis. If only case_open runs, return INDETERMINATE-style limited coverage and do not claim file-system content was reviewed.",
  },
  {
    id: "manifest-verify",
    title: "Manifest verification",
    mode: "manifest",
    summary: "Verify a prior run manifest and audit chain.",
    placeholderEvidence: "tmp/auto-runs/<run-id>/run.manifest.json",
    prompt:
      "Verify the manifest and audit chain for this run. Report overall, audit_chain_ok, merkle_root_ok, signature_present, and any precise mismatch diagnostics. Do not print secrets or private paths beyond the operator-provided path.",
  },
  {
    id: "report-limitations",
    title: "Report limitations pass",
    mode: "general",
    summary: "Ask Codex to review a run for overclaiming.",
    placeholderEvidence: "tmp/auto-runs/<run-id>",
    prompt:
      "Review the investigation output for overclaims. Focus on whether findings cite tool_call_id, whether execution claims have two artifact classes, and whether NO_EVIL or INDETERMINATE wording states coverage limits.",
  },
  {
    id: "codex-smoke",
    title: "Codex MCP smoke",
    mode: "evtx",
    summary: "Minimal Codex-to-MCP connectivity check.",
    placeholderEvidence: "fixtures/single-evtx/Security.evtx",
    prompt:
      "Use only case_open and evtx_query with limit 25 against the provided EVTX. Return the tool names used, case_id, image_hash prefix, row_count, records_seen, parse_errors, and whether the sample produced any standalone finding-worthy event.",
  },
];

export function isCodexMode(value: unknown): value is CodexMode {
  return (
    value === "evtx" ||
    value === "memory" ||
    value === "disk" ||
    value === "manifest" ||
    value === "general"
  );
}

export function buildCodexInvestigationPrompt(input: {
  mode: CodexMode;
  message: string;
  evidencePath?: string;
}): string {
  const tools = CODEX_MODE_TOOL_ALLOWLIST[input.mode];
  const rustTools = tools.rust.length > 0 ? tools.rust.join(", ") : "none";
  const agentTools = tools.agent.length > 0 ? tools.agent.join(", ") : "none";
  const evidence = input.evidencePath?.trim()
    ? input.evidencePath.trim()
    : "not provided";

  return [
    "You are operating Find Evil through Codex as a local operator UI.",
    "Use the configured Find Evil MCP tools only. Do not use shell commands.",
    "Do not edit files. Treat original evidence as read-only.",
    "Every Finding must cite tool_call_id when a finding is produced.",
    "Execution claims require at least two artifact classes.",
    "Treat Hayabusa, Sigma, YARA, capa, and anomaly matches as triage leads unless corroborated.",
    "Do not describe limited coverage as clean, cleared, disproven, or proof of absence.",
    "Use NO_EVIL only with the documented verdict semantics and state the exact coverage reviewed.",
    `Mode: ${CODEX_MODE_LABELS[input.mode]}`,
    `Allowed Rust MCP tools: ${rustTools}`,
    `Allowed agent MCP tools: ${agentTools}`,
    `Evidence or run path: ${evidence}`,
    "Operator request:",
    input.message.trim(),
  ].join("\n");
}

export function buildCodexAppDeeplink(input: {
  prompt: string;
  repoRoot?: string;
}): string {
  const params = new URLSearchParams();
  params.set("prompt", input.prompt);
  if (input.repoRoot?.trim()) {
    params.set("path", input.repoRoot.trim());
  }
  return `codex://new?${params.toString()}`;
}
