// Dev/QA debug page: subscribe to /api/audit?case=<path> SSE stream
// from the browser and dump each `audit_line` event as a small NES.css
// card. This is a back-end smoke tool — Phase 5's sprite components
// will render the same data prettier (per A3 plan §5).
//
// Importing the AuditLine type from `@/lib/audit-tail` would drag the
// server-only `node:fs` + chokidar imports into the client bundle, so
// we redeclare the shape here. Keep this in sync with
// `apps/web/lib/audit-tail.ts:AuditLine`.

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface AuditLine {
  seq: number;
  kind: string;
  ts: string;
  payload: Record<string, unknown>;
  line_hash?: string;
  raw_line: string;
}

type ConnState = "disconnected" | "connecting" | "live";

const MAX_EVENTS = 100;

export default function DebugPage() {
  const [casePath, setCasePath] = useState("");
  const [events, setEvents] = useState<AuditLine[]>([]);
  const [conn, setConn] = useState<ConnState>("disconnected");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [showPayloads, setShowPayloads] = useState(true);
  const esRef = useRef<EventSource | null>(null);

  const disconnect = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setConn("disconnected");
  }, []);

  const connect = useCallback(() => {
    if (!casePath.trim()) {
      setErrorMsg("Enter an absolute case directory path first.");
      return;
    }
    // Close any previous connection cleanly before opening a new one.
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setErrorMsg(null);
    setConn("connecting");

    const url = `/api/audit?case=${encodeURIComponent(casePath.trim())}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.addEventListener("open", () => {
      setConn("live");
    });

    es.addEventListener("audit_line", (raw: MessageEvent) => {
      try {
        const line = JSON.parse(raw.data) as AuditLine;
        setEvents((prev) => {
          const next = [line, ...prev];
          return next.length > MAX_EVENTS ? next.slice(0, MAX_EVENTS) : next;
        });
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setErrorMsg(`failed to parse audit_line: ${msg}`);
      }
    });

    es.addEventListener("error", (raw: Event) => {
      // SSE error events from the route handler carry a JSON body in
      // `MessageEvent.data`; native EventSource errors (network drop,
      // 400, etc.) come in as plain Events with no data. Surface
      // whatever we can get.
      const maybeMsg = (raw as MessageEvent).data;
      if (typeof maybeMsg === "string" && maybeMsg.length > 0) {
        try {
          const parsed = JSON.parse(maybeMsg) as { error?: string };
          setErrorMsg(parsed.error ?? maybeMsg);
        } catch {
          setErrorMsg(maybeMsg);
        }
      } else {
        setErrorMsg(
          "EventSource error (connection refused, 400 from API, or stream closed). Check the case path and that audit.jsonl exists.",
        );
      }
      setConn("disconnected");
      es.close();
      esRef.current = null;
    });
  }, [casePath]);

  // Tear down the EventSource on unmount so the stream doesn't leak
  // across navigations.
  useEffect(() => {
    return () => {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, []);

  const clearEvents = useCallback(() => {
    setEvents([]);
  }, []);

  const dotColor =
    conn === "live"
      ? "#22c55e"
      : conn === "connecting"
        ? "#eab308"
        : "#ef4444";

  return (
    <main className="min-h-screen p-8">
      <div className="nes-container with-title is-rounded max-w-4xl mx-auto">
        <p className="title">/debug — audit.jsonl SSE stream viewer</p>
        <p className="text-sm">
          Dev/QA tool. Subscribe to <code>/api/audit?case=&lt;path&gt;</code>{" "}
          and dump each <code>audit_line</code> event raw. Phase 5 sprite
          components will render the same data prettier; this page just proves
          the stream is alive without <code>curl</code>.
        </p>

        <div className="nes-field mt-6">
          <label htmlFor="case-path">Case directory (absolute path)</label>
          <input
            id="case-path"
            type="text"
            className="nes-input"
            placeholder="absolute path to a case dir containing audit.jsonl"
            value={casePath}
            onChange={(e) => setCasePath(e.target.value)}
            disabled={conn !== "disconnected"}
          />
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          {conn === "disconnected" ? (
            <button
              type="button"
              className="nes-btn is-primary"
              onClick={connect}
            >
              Connect
            </button>
          ) : (
            <button
              type="button"
              className="nes-btn is-error"
              onClick={disconnect}
            >
              Disconnect
            </button>
          )}
          <button
            type="button"
            className="nes-btn"
            onClick={clearEvents}
            disabled={events.length === 0}
          >
            Clear ({events.length})
          </button>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              className="nes-checkbox"
              checked={showPayloads}
              onChange={(e) => setShowPayloads(e.target.checked)}
            />
            <span>Show payloads</span>
          </label>
          <span className="ml-auto inline-flex items-center gap-2 text-sm">
            <span
              aria-label={`stream ${conn}`}
              style={{
                display: "inline-block",
                width: "0.75rem",
                height: "0.75rem",
                borderRadius: "9999px",
                background: dotColor,
                boxShadow: `0 0 6px ${dotColor}`,
              }}
            />
            <span>{conn}</span>
          </span>
        </div>

        {errorMsg ? (
          <div className="nes-container is-rounded is-error mt-4">
            <p className="text-sm">
              <strong>error:</strong> {errorMsg}
            </p>
          </div>
        ) : null}
      </div>

      <div className="max-w-4xl mx-auto mt-6 space-y-3">
        {events.length === 0 ? (
          <div className="nes-container is-rounded">
            <p className="text-sm">
              No events yet.{" "}
              {conn === "live"
                ? "Stream is live — waiting for the next audit append."
                : "Click Connect to start tailing."}
            </p>
          </div>
        ) : (
          events.map((line, idx) => {
            const payloadStr = JSON.stringify(line.payload);
            const truncated =
              payloadStr.length > 200
                ? payloadStr.slice(0, 200) + "…"
                : payloadStr;
            // Use seq + idx so we don't collide on bookkeeping lines
            // that happen to share a seq (e.g. -1 sentinel).
            const key = `${line.seq}-${idx}-${line.line_hash ?? ""}`;
            return (
              <div key={key} className="nes-container is-rounded">
                <p className="text-sm">
                  <code>[seq {line.seq}]</code>{" "}
                  <code>[{line.kind}]</code>{" "}
                  <code>[{line.ts}]</code>
                </p>
                {showPayloads ? (
                  <pre className="mt-2 text-xs whitespace-pre-wrap break-all">
                    <code>{truncated}</code>
                  </pre>
                ) : null}
              </div>
            );
          })
        )}
      </div>
    </main>
  );
}
