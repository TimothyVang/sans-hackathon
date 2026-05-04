import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  buildCodexAppDeeplink,
  buildCodexInvestigationPrompt,
  CODEX_PRESETS,
} from "@/lib/codex-presets";
import {
  buildCodexCommandSpec,
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
});
