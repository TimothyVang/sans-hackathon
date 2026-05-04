import {
  buildCodexCommandSpec,
  getRepoRoot,
  isCodexUiEnabled,
  isFindevilMcpBinaryBuilt,
  streamCodexExec,
  validateCodexRequest,
} from "@/lib/codex-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  const repoRoot = getRepoRoot();
  return Response.json({
    enabled: isCodexUiEnabled(),
    repoRoot,
    rustMcpBinaryBuilt: isFindevilMcpBinaryBuilt(repoRoot),
    note:
      "Set FINDEVIL_CODEX_UI_ENABLE=1 to allow this local dashboard to launch constrained Codex exec runs.",
  });
}

export async function POST(request: Request): Promise<Response> {
  const repoRoot = getRepoRoot();

  if (!isCodexUiEnabled()) {
    return Response.json(
      {
        error:
          "Codex UI execution is disabled. Set FINDEVIL_CODEX_UI_ENABLE=1 in the local dashboard environment to enable one-shot Codex exec runs.",
      },
      { status: 403 },
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "request body must be JSON" }, { status: 400 });
  }

  const parsed = validateCodexRequest(body, repoRoot);
  if (!parsed.ok) {
    return Response.json({ error: parsed.error }, { status: 400 });
  }

  if (parsed.value.mode !== "manifest" && !isFindevilMcpBinaryBuilt(repoRoot)) {
    return Response.json(
      {
        error:
          "target/release/findevil-mcp binary is missing. Build it first with: cargo build --release -p findevil-mcp --locked",
      },
      { status: 409 },
    );
  }

  const spec = buildCodexCommandSpec(parsed.value, repoRoot);
  return new Response(streamCodexExec(spec, request.signal), {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}
