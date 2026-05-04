import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

import {
  buildCodexInvestigationPrompt,
  CODEX_MODE_TOOL_ALLOWLIST,
  type CodexMode,
  isCodexMode,
} from "@/lib/codex-presets";

const DEFAULT_ALLOWED_EVIDENCE_ROOTS = [
  "fixtures",
  "goldens",
  "tmp/auto-runs",
  "tmp/smoke",
  "test-forensics",
];

const MAX_PROMPT_CHARS = 6_000;
const CODEX_TIMEOUT_MS = 10 * 60 * 1000;

export interface ValidCodexRequest {
  mode: CodexMode;
  message: string;
  evidencePath?: string;
}

export interface CodexCommandSpec {
  command: string;
  args: string[];
  cwd: string;
  prompt: string;
}

export function isCodexUiEnabled(): boolean {
  return process.env.FINDEVIL_CODEX_UI_ENABLE === "1";
}

export function getRepoRoot(start = process.cwd()): string {
  const cwd = path.resolve(start);
  if (existsSync(path.join(cwd, "Cargo.toml"))) return cwd;

  const fromWebApp = path.resolve(cwd, "..", "..");
  if (existsSync(path.join(fromWebApp, "Cargo.toml"))) return fromWebApp;

  return cwd;
}

export function getFindevilMcpBinary(repoRoot = getRepoRoot()): string {
  const relative =
    process.platform === "win32"
      ? path.join("target", "release", "findevil-mcp.exe")
      : path.join("target", "release", "findevil-mcp");
  return path.join(repoRoot, relative);
}

export function isFindevilMcpBinaryBuilt(repoRoot = getRepoRoot()): boolean {
  return existsSync(getFindevilMcpBinary(repoRoot));
}

export function isAllowedCodexEvidencePath(
  candidate: string,
  repoRoot = getRepoRoot(),
): boolean {
  const resolved = path.resolve(repoRoot, candidate);
  const extraRaw = process.env.FINDEVIL_CODEX_EXTRA_ROOTS ?? "";
  const extraRoots = extraRaw
    .split(path.delimiter)
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0)
    .map((entry) => path.resolve(entry));

  const roots = [
    ...DEFAULT_ALLOWED_EVIDENCE_ROOTS.map((root) => path.resolve(repoRoot, root)),
    ...extraRoots,
  ];

  for (const root of roots) {
    if (resolved === root) return true;
    if (resolved.startsWith(root + path.sep)) return true;
  }

  return false;
}

export function validateCodexRequest(
  body: unknown,
  repoRoot = getRepoRoot(),
): { ok: true; value: ValidCodexRequest } | { ok: false; error: string } {
  if (!body || typeof body !== "object") {
    return { ok: false, error: "request body must be a JSON object" };
  }

  const obj = body as Record<string, unknown>;
  const mode = obj.mode;
  const message = obj.message;
  const evidencePath = obj.evidencePath;

  if (!isCodexMode(mode)) {
    return { ok: false, error: "mode must be evtx, memory, disk, manifest, or general" };
  }
  if (typeof message !== "string" || message.trim().length === 0) {
    return { ok: false, error: "message is required" };
  }
  if (message.length > MAX_PROMPT_CHARS) {
    return { ok: false, error: `message is too long (${MAX_PROMPT_CHARS} char max)` };
  }
  if (evidencePath !== undefined) {
    if (typeof evidencePath !== "string") {
      return { ok: false, error: "evidencePath must be a string when provided" };
    }
    if (evidencePath.trim().length > 0 && !isAllowedCodexEvidencePath(evidencePath, repoRoot)) {
      return {
        ok: false,
        error:
          "evidencePath is outside the Codex UI allow-list; use fixtures, goldens, tmp/auto-runs, tmp/smoke, test-forensics, or FINDEVIL_CODEX_EXTRA_ROOTS",
      };
    }
  }

  return {
    ok: true,
    value: {
      mode,
      message: message.trim(),
      evidencePath:
        typeof evidencePath === "string" && evidencePath.trim().length > 0
          ? evidencePath.trim()
          : undefined,
    },
  };
}

export function buildCodexCommandSpec(
  request: ValidCodexRequest,
  repoRoot = getRepoRoot(),
): CodexCommandSpec {
  const command =
    process.env.FINDEVIL_CODEX_BIN ??
    (process.platform === "win32" ? "npx.cmd" : "npx");
  const packageArgs = process.env.FINDEVIL_CODEX_BIN
    ? []
    : ["-y", "@openai/codex"];
  const rustBinary =
    process.platform === "win32"
      ? "target/release/findevil-mcp.exe"
      : "target/release/findevil-mcp";
  const tools = CODEX_MODE_TOOL_ALLOWLIST[request.mode];
  const args = [
    ...packageArgs,
    "exec",
    "--ignore-user-config",
    "--ephemeral",
    "--dangerously-bypass-approvals-and-sandbox",
    "--disable",
    "shell_tool",
    "-C",
    repoRoot,
  ];

  if (tools.rust.length > 0) {
    args.push(
      "-c",
      `mcp_servers.findevil-mcp.command='${rustBinary}'`,
      "-c",
      "mcp_servers.findevil-mcp.cwd='.'",
      "-c",
      "mcp_servers.findevil-mcp.required=true",
      "-c",
      `mcp_servers.findevil-mcp.enabled_tools=[${tools.rust.map((tool) => `'${tool}'`).join(",")}]`,
      "-c",
      "mcp_servers.findevil-mcp.startup_timeout_sec=30",
      "-c",
      "mcp_servers.findevil-mcp.tool_timeout_sec=120",
    );
  }

  if (tools.agent.length > 0) {
    args.push(
      "-c",
      "mcp_servers.findevil-agent-mcp.command='uv'",
      "-c",
      "mcp_servers.findevil-agent-mcp.args=['run','--directory','services/agent_mcp','python','-m','findevil_agent_mcp.server']",
      "-c",
      "mcp_servers.findevil-agent-mcp.cwd='.'",
      "-c",
      "mcp_servers.findevil-agent-mcp.required=true",
      "-c",
      `mcp_servers.findevil-agent-mcp.enabled_tools=[${tools.agent.map((tool) => `'${tool}'`).join(",")}]`,
      "-c",
      "mcp_servers.findevil-agent-mcp.startup_timeout_sec=30",
      "-c",
      "mcp_servers.findevil-agent-mcp.tool_timeout_sec=120",
    );
  }

  args.push("-");

  return {
    command,
    args,
    cwd: repoRoot,
    prompt: buildCodexInvestigationPrompt(request),
  };
}

export function streamCodexExec(
  spec: CodexCommandSpec,
  signal: AbortSignal,
): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();

  return new ReadableStream({
    start(controller) {
      let closed = false;
      const enqueue = (chunk: Uint8Array | string): void => {
        if (closed) return;
        controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk);
      };
      const close = (): void => {
        if (closed) return;
        closed = true;
        controller.close();
      };

      const child = spawn(spec.command, spec.args, {
        cwd: spec.cwd,
        env: {
          ...process.env,
          NO_COLOR: "1",
        },
        shell: false,
        windowsHide: true,
      });

      const timeout = setTimeout(() => {
        enqueue("\n[codex timeout: process killed]\n");
        child.kill();
      }, CODEX_TIMEOUT_MS);

      const abort = () => {
        child.kill();
      };
      signal.addEventListener("abort", abort, { once: true });

      child.stdout.on("data", (chunk: Buffer) => {
        enqueue(chunk);
      });

      child.stderr.on("data", (chunk: Buffer) => {
        enqueue(chunk);
      });

      child.on("error", (err) => {
        clearTimeout(timeout);
        signal.removeEventListener("abort", abort);
        enqueue(`\n[codex spawn error: ${err.message}]\n`);
        close();
      });

      child.on("close", (code) => {
        clearTimeout(timeout);
        signal.removeEventListener("abort", abort);
        enqueue(`\n[codex exited ${code ?? "unknown"}]\n`);
        close();
      });

      child.stdin.write(spec.prompt);
      child.stdin.end();
    },
  });
}
