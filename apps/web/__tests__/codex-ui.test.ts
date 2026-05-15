import path from "node:path";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";

import { describe, expect, it } from "vitest";

import {
  buildCodexAppDeeplink,
  buildCodexInvestigationPrompt,
  CODEX_PRESETS,
} from "@/lib/codex-presets";
import {
  buildCodexCommandSpec,
  getLatestCodexReadinessSummary,
  isAllowedCodexEvidencePath,
  validateCodexRequest,
} from "@/lib/codex-server";

describe("Codex UI presets", () => {
  it("ships suggested investigation prompts", () => {
    expect(CODEX_PRESETS.length).toBeGreaterThanOrEqual(5);
    expect(CODEX_PRESETS.map((preset) => preset.id)).toContain("evtx-first-look");
    expect(CODEX_PRESETS.map((preset) => preset.id)).toContain("memory-dkom");
  });

  it("does not train operators to call limited coverage clean", () => {
    const joined = CODEX_PRESETS.map((preset) => preset.prompt.toLowerCase()).join("\n");
    expect(joined).not.toContain("clean");
    expect(joined).not.toContain("cleared");
    expect(joined).not.toContain("disproven");
  });

  it("builds a guarded Find Evil prompt", () => {
    const prompt = buildCodexInvestigationPrompt({
      mode: "evtx",
      evidencePath: "fixtures/single-evtx/Security.evtx",
      message: "Run a narrow EVTX check.",
    });
    expect(prompt).toContain("Use the configured Find Evil MCP tools only");
    expect(prompt).toContain("Do not use shell commands");
    expect(prompt).toContain("case_open, evtx_query");
    expect(prompt).toContain("Do not describe limited coverage as clean");
  });

  it("builds a Codex app deeplink without pretending to control the TUI", () => {
    const link = buildCodexAppDeeplink({
      prompt: "Investigate the EVTX.",
      repoRoot: process.platform === "win32" ? "C:\\repo" : "/repo",
    });
    expect(link).toContain("codex://new?");
    expect(link).toContain("prompt=Investigate+the+EVTX");
    expect(link).toContain("path=");
  });
});

describe("Codex UI server guardrails", () => {
  const repoRoot = process.platform === "win32" ? "C:\\repo" : "/repo";

  it("allows evidence inside known repo roots", () => {
    expect(
      isAllowedCodexEvidencePath(
        path.join("fixtures", "single-evtx", "Security.evtx"),
        repoRoot,
      ),
    ).toBe(true);
  });

  it("blocks evidence outside known roots", () => {
    const outside = process.platform === "win32" ? "C:\\Windows\\win.ini" : "/etc/passwd";
    expect(isAllowedCodexEvidencePath(outside, repoRoot)).toBe(false);
  });

  it("rejects invalid request shapes", () => {
    expect(validateCodexRequest({ mode: "evtx", message: "" }, repoRoot).ok).toBe(false);
    expect(validateCodexRequest({ mode: "browser", message: "hi" }, repoRoot).ok).toBe(false);
  });

  it("builds Codex exec args with shell disabled and narrow tool allowlist", () => {
    const spec = buildCodexCommandSpec(
      {
        mode: "evtx",
        message: "Use the EVTX tools.",
        evidencePath: "fixtures/single-evtx/Security.evtx",
      },
      repoRoot,
    );
    expect(spec.args).toContain("--ignore-user-config");
    expect(spec.args).toContain("--ephemeral");
    expect(spec.args).toContain("--disable");
    expect(spec.args).toContain("shell_tool");
    expect(spec.args.join(" ")).toContain("enabled_tools=['case_open','evtx_query']");
    expect(spec.prompt).toContain("Execution claims require at least two artifact classes");
  });

  it("loads the latest local readiness summary for the operator surface", () => {
    const repoRoot = mkdtempSync(path.join(tmpdir(), "findevil-codex-ready-"));
    const runRoot = path.join(repoRoot, "tmp", "readiness-gates", "ready-run");
    const evidenceRunDir = path.join(repoRoot, "tmp", "auto-runs", "auto-1");
    mkdirSync(runRoot, { recursive: true });
    mkdirSync(evidenceRunDir, { recursive: true });
    writeFileSync(path.join(evidenceRunDir, "REPORT.html"), "<h1>Report</h1>");
    writeFileSync(
      path.join(runRoot, "readiness-summary.json"),
      JSON.stringify({
        generated_at: "2026-05-14T00:00:00Z",
        run_id: "ready-run",
        readiness_state: "PACKET_READY_FOR_EXPERT_REVIEW",
        evidence_run_dir: evidenceRunDir,
        packet_zip: path.join(runRoot, "readiness-packet.zip"),
        customer_releasable: false,
        blockers: [],
        warnings: ["REPORT.pdf missing; packet contains HTML report only"],
      }),
    );

    const summary = getLatestCodexReadinessSummary(repoRoot);

    expect(summary?.readinessState).toBe("PACKET_READY_FOR_EXPERT_REVIEW");
    expect(summary?.packetZip).toContain("readiness-packet.zip");
    expect(summary?.warnings).toContain("REPORT.pdf missing; packet contains HTML report only");
    expect(summary?.reportLinks.map((link) => link.label)).toContain("REPORT.html");
  });
});
