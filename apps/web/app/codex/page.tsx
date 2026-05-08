"use client";

import { useEffect, useMemo, useState } from "react";

import {
  buildCodexAppDeeplink,
  buildCodexInvestigationPrompt,
  CODEX_MODE_LABELS,
  CODEX_PRESETS,
  type CodexMode,
} from "@/lib/codex-presets";
import { DashboardNav } from "@/components/DashboardNav";

type ChatRole = "operator" | "codex" | "system";

interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
}

interface CodexStatus {
  enabled: boolean;
  repoRoot: string;
  rustMcpBinaryBuilt: boolean;
  note: string;
}

const INITIAL_MESSAGE: ChatMessage = {
  id: "intro",
  role: "system",
  content:
    "This is a Find Evil operator wrapper for Codex. It cannot send text into an already-running Codex CLI TUI because the TUI does not expose an input API. Use Copy TUI prompt for the terminal, Open Codex app for a deeplink, or Run in chat for a separate one-shot codex exec run.",
};

export default function CodexPage() {
  const [mode, setMode] = useState<CodexMode>("evtx");
  const [evidencePath, setEvidencePath] = useState("fixtures/single-evtx/Security.evtx");
  const [prompt, setPrompt] = useState(CODEX_PRESETS[0]?.prompt ?? "");
  const [messages, setMessages] = useState<ChatMessage[]>([INITIAL_MESSAGE]);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState<CodexStatus | null>(null);

  useEffect(() => {
    fetch("/api/codex", { cache: "no-store" })
      .then((res) => res.json() as Promise<CodexStatus>)
      .then(setStatus)
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : String(err);
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: "system",
            content: `Unable to read Codex route status: ${msg}`,
          },
        ]);
      });
  }, []);

  const generatedPrompt = useMemo(
    () =>
      buildCodexInvestigationPrompt({
        mode,
        message: prompt,
        evidencePath,
      }),
    [evidencePath, mode, prompt],
  );

  const codexAppHref = useMemo(
    () =>
      buildCodexAppDeeplink({
        prompt: generatedPrompt,
        repoRoot: status?.repoRoot,
      }),
    [generatedPrompt, status?.repoRoot],
  );

  const applyPreset = (presetId: string): void => {
    const preset = CODEX_PRESETS.find((candidate) => candidate.id === presetId);
    if (!preset) return;
    setMode(preset.mode);
    setPrompt(preset.prompt);
    if (preset.placeholderEvidence) setEvidencePath(preset.placeholderEvidence);
  };

  const runCodex = async (): Promise<void> => {
    if (running || prompt.trim().length === 0) return;

    const operatorMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "operator",
      content: prompt.trim(),
    };
    const codexMessageId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      operatorMessage,
      { id: codexMessageId, role: "codex", content: "" },
    ]);
    setRunning(true);

    try {
      const res = await fetch("/api/codex", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, evidencePath, message: prompt }),
      });

      if (!res.ok || !res.body) {
        const text = await res.text();
        updateMessage(codexMessageId, text || `Codex route failed with ${res.status}`);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let accumulated = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        accumulated += decoder.decode(value, { stream: true });
        updateMessage(codexMessageId, accumulated);
      }
      accumulated += decoder.decode();
      updateMessage(codexMessageId, accumulated);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      updateMessage(codexMessageId, `Codex request failed: ${msg}`);
    } finally {
      setRunning(false);
    }
  };

  const updateMessage = (id: string, content: string): void => {
    setMessages((prev) =>
      prev.map((message) => (message.id === id ? { ...message, content } : message)),
    );
  };

  return (
    <main className="min-h-screen overflow-x-hidden bg-[#0f172a] px-4 py-6 text-slate-100 md:px-8">
      <DashboardNav active="codex" variant="dark" />
      <div className="mx-auto max-w-7xl">
        <header className="grid gap-4 rounded-3xl border border-cyan-300/30 bg-slate-950/80 p-6 shadow-2xl shadow-cyan-950/30 md:grid-cols-[1.3fr_0.7fr]">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-cyan-300">Find Evil Codex UI</p>
            <h1 className="mt-3 text-3xl font-black tracking-tight md:text-5xl">
              Codex investigation cockpit
            </h1>
            <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-300 md:text-base">
              A local wrapper for curated Codex prompts. Use the regular Codex TUI when you want its built-in dashboard; use this page when you want repeatable Find Evil investigation prompts, evidence-path guardrails, and a browser chat transcript.
            </p>
          </div>
          <div className="rounded-2xl border border-slate-700 bg-slate-900 p-4 text-sm">
            <p className="font-bold text-cyan-200">Runner status</p>
            <p className="mt-3">
              API: {status?.enabled ? "enabled" : "disabled"}
            </p>
            <p>Rust MCP binary: {status?.rustMcpBinaryBuilt ? "built" : "missing"}</p>
            <p className="mt-3 text-xs text-slate-400">
              Enable one-shot runs with <code>FINDEVIL_CODEX_UI_ENABLE=1</code>. Without it, this page still works as a prompt launcher.
            </p>
          </div>
        </header>

        <div className="mt-6 grid gap-6 lg:grid-cols-[360px_1fr]">
          <aside className="space-y-4">
            <section className="rounded-2xl border border-slate-700 bg-slate-950/80 p-4">
              <h2 className="text-lg font-bold text-cyan-200">Suggested investigations</h2>
              <div className="mt-4 space-y-3">
                {CODEX_PRESETS.map((preset) => (
                  <button
                    key={preset.id}
                    type="button"
                    onClick={() => applyPreset(preset.id)}
                    className="w-full rounded-xl border border-slate-700 bg-slate-900 p-3 text-left transition hover:border-cyan-300 hover:bg-slate-800"
                  >
                    <span className="block text-sm font-bold text-slate-100">{preset.title}</span>
                    <span className="mt-1 block text-xs text-slate-400">{preset.summary}</span>
                    <span className="mt-2 inline-block rounded-full bg-cyan-950 px-2 py-1 text-[11px] text-cyan-200">
                      {CODEX_MODE_LABELS[preset.mode]}
                    </span>
                  </button>
                ))}
              </div>
            </section>

            <section className="rounded-2xl border border-amber-300/30 bg-amber-950/20 p-4 text-sm text-amber-100">
              <h2 className="font-bold">Safety envelope</h2>
              <p className="mt-2 text-xs leading-5">
                The server runner is disabled by default. When enabled, it uses an ephemeral Codex exec command, disables the shell tool, and allowlists only the MCP tools required by the selected mode.
              </p>
            </section>

            <section className="rounded-2xl border border-fuchsia-300/30 bg-fuchsia-950/20 p-4 text-sm text-fuchsia-100">
              <h2 className="font-bold">TUI boundary</h2>
              <p className="mt-2 text-xs leading-5">
                This browser page cannot type into a live Codex CLI TUI. Use Copy TUI prompt and paste it into the terminal, or use the Codex app deeplink when the desktop app is installed.
              </p>
            </section>
          </aside>

          <section className="rounded-2xl border border-slate-700 bg-slate-950/80 p-4">
            <div className="grid gap-4 md:grid-cols-[220px_1fr]">
              <label className="block text-sm">
                <span className="font-bold text-slate-200">Mode</span>
                <select
                  value={mode}
                  onChange={(event) => setMode(event.target.value as CodexMode)}
                  className="mt-2 w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-slate-100"
                >
                  {Object.entries(CODEX_MODE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm">
                <span className="font-bold text-slate-200">Evidence or run path</span>
                <input
                  value={evidencePath}
                  onChange={(event) => setEvidencePath(event.target.value)}
                  className="mt-2 w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-slate-100"
                  placeholder="fixtures/single-evtx/Security.evtx"
                />
              </label>
            </div>

            <div className="mt-4 h-[420px] overflow-y-auto rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
              <div className="space-y-4">
                {messages.map((message) => (
                  <article
                    key={message.id}
                    className={
                      message.role === "operator"
                        ? "ml-auto max-w-[88%] rounded-2xl bg-cyan-900/70 p-4"
                        : message.role === "codex"
                          ? "max-w-[88%] rounded-2xl bg-slate-800 p-4"
                          : "max-w-[95%] rounded-2xl border border-slate-700 bg-slate-950 p-4 text-slate-300"
                    }
                  >
                    <p className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-400">
                      {message.role}
                    </p>
                    <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-6">
                      {message.content || (running ? "Codex is thinking..." : "")}
                    </pre>
                  </article>
                ))}
              </div>
            </div>

            <label className="mt-4 block text-sm">
              <span className="font-bold text-slate-200">Prompt</span>
              <textarea
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                className="mt-2 min-h-32 w-full rounded-xl border border-slate-600 bg-slate-900 px-3 py-2 text-slate-100"
              />
            </label>

            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => void runCodex()}
                disabled={running}
                className="rounded-xl bg-cyan-400 px-5 py-3 font-bold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:bg-slate-600"
              >
                {running ? "Running Codex" : "Run in chat"}
              </button>
              <button
                type="button"
                onClick={() => navigator.clipboard.writeText(generatedPrompt)}
                className="rounded-xl border border-slate-600 px-5 py-3 font-bold text-slate-200 transition hover:border-cyan-300"
              >
                Copy TUI prompt
              </button>
              <a
                href={codexAppHref}
                className="rounded-xl border border-slate-600 px-5 py-3 font-bold text-slate-200 transition hover:border-cyan-300"
              >
                Open Codex app
              </a>
              <a
                href="/"
                className="rounded-xl border border-slate-600 px-5 py-3 font-bold text-slate-200 transition hover:border-cyan-300"
              >
                Audit dashboard
              </a>
              <a
                href="/debug"
                className="rounded-xl border border-slate-600 px-5 py-3 font-bold text-slate-200 transition hover:border-cyan-300"
              >
                Debug stream
              </a>
            </div>

            <details className="mt-4 rounded-2xl border border-slate-800 bg-slate-900 p-4 text-sm">
              <summary className="cursor-pointer font-bold text-cyan-200">Generated guarded prompt</summary>
              <pre className="mt-3 max-h-64 overflow-y-auto whitespace-pre-wrap break-words text-xs leading-5 text-slate-300">
                {generatedPrompt}
              </pre>
            </details>
          </section>
        </div>
      </div>
    </main>
  );
}
