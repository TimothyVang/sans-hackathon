//! Stdio JSON-RPC 2.0 server for `findevil-mcp`.
//!
//! Hand-rolled rather than `rmcp`-based for two reasons:
//!
//! 1. **Wire-format stability.** Spec #2 commits to MCP 2024-11-05.
//!    A manual implementation pinned to that protocol revision is
//!    unaffected by future rmcp API churn.
//! 2. **Mirrored Python pattern.** The `findevil-agent-mcp` Python
//!    server uses the same line-delimited JSON-RPC dispatch shape.
//!    Two languages, one wire format, one mental model.
//!
//! Wire format (per the MCP spec):
//!
//! * One JSON object per line on stdin / stdout.
//! * Logs go to stderr only — anything on stdout that is not a
//!   valid JSON-RPC response corrupts the protocol stream.
//!
//! Methods handled:
//!
//! * `initialize` → echoes protocol version, advertises `tools` capability.
//! * `notifications/initialized` → no-op acknowledgement.
//! * `tools/list` → emits the tool catalog with JSON Schemas.
//! * `tools/call` → validates arguments, dispatches to the handler,
//!   returns content as a single `text` block of canonical JSON.
//!
//! Errors follow JSON-RPC 2.0:
//! * `-32601` method-not-found
//! * `-32602` invalid-params (input failed Pydantic-equivalent validation)
//! * `-32603` internal-error (handler panicked or returned an error)
//!
//! Spec #2 invariant: every successful tool response carries the
//! tool's typed output and a SHA-256 of the raw JSON text. The
//! SHA-256 lives in the `_meta` extension envelope so MCP clients
//! that only read `content[0].text` still get the typed payload.

use std::io::{BufRead, BufReader, Read, Write};

use serde::de::DeserializeOwned;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use crate::tools::{
    case_open, evtx_query::evtx_query, mft_timeline::mft_timeline, prefetch_parse::prefetch_parse,
    CaseOpenInput, EvtxQueryInput, MftInput, PrefetchInput,
};
use crate::CRATE_VERSION;

/// MCP protocol revision we speak. Hard-coded; any breaking change
/// ships behind a code update + spec amendment, not silent drift.
const PROTOCOL_VERSION: &str = "2024-11-05";

const SERVER_NAME: &str = "findevil-mcp";

// JSON-RPC standard error codes (kept for reference; we use INVALID_PARAMS
// for unknown methods/tools so the client gets actionable messages).
const ERR_INVALID_PARAMS: i64 = -32602;
const ERR_INTERNAL: i64 = -32603;

/// Tool descriptor — name, human-readable description, schema producer,
/// and the dispatch closure.
struct ToolEntry {
    name: &'static str,
    description: &'static str,
    /// Returns the JSON Schema for the input type. Computed lazily so
    /// the server only pays the schemars cost on `tools/list`.
    schema: fn() -> Value,
    /// Validates the arguments and returns the typed output as JSON.
    /// On invalid input returns `Err(ToolError::InvalidParams(_))`;
    /// on handler failure returns `Err(ToolError::Internal(_))`.
    handler: fn(Value) -> Result<Value, ToolError>,
}

#[derive(Debug)]
enum ToolError {
    InvalidParams(String),
    Internal(String),
}

/// Run the stdio server until stdin closes. Returns on EOF or fatal
/// I/O error. Logs to stderr.
///
/// # Errors
/// Returns the underlying I/O error if reading from stdin or writing
/// to stdout fails. Per-message errors (validation, handler) are
/// returned to the client as JSON-RPC errors and do not abort the
/// loop.
pub fn run_stdio_server() -> std::io::Result<()> {
    run_stdio_server_with_streams(std::io::stdin().lock(), std::io::stdout().lock())
}

/// Test-friendly variant that takes arbitrary read/write streams.
///
/// # Errors
/// Returns the first I/O error from reading or writing.
pub fn run_stdio_server_with_streams<R, W>(input: R, mut output: W) -> std::io::Result<()>
where
    R: Read,
    W: Write,
{
    let registry = build_registry();
    let mut reader = BufReader::new(input);
    let mut line = String::new();

    loop {
        line.clear();
        let n = reader.read_line(&mut line)?;
        if n == 0 {
            // EOF — peer closed.
            break;
        }
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        if let Some(response) = dispatch(trimmed, &registry) {
            writeln!(output, "{response}")?;
            output.flush()?;
        }
    }
    Ok(())
}

fn build_registry() -> Vec<ToolEntry> {
    vec![
        ToolEntry {
            name: "case_open",
            description:
                "FIRST tool to call when starting an investigation. Registers an evidence image \
                 (.e01, .raw, .dd, .mem) by computing its SHA-256, issuing a UUID4 case_id, and \
                 creating the case directory at $FINDEVIL_HOME/cases/<id>/. Idempotent per image \
                 hash — calling twice on the same file yields a new case_id but does not mutate \
                 evidence. Use the returned case_id in every subsequent tool call. \
                 ERRORS: ImageNotFound (check the path), ImageNotRegular (path is a directory; \
                 pass the file directly), ImageHashMismatch (only if expected_sha256 supplied — \
                 implies tampering or wrong file).",
            schema: || schema_for::<CaseOpenInput>(),
            handler: |args| dispatch_case_open(args),
        },
        ToolEntry {
            name: "evtx_query",
            description:
                "Parse a Windows Event Log (.evtx) file. Use AFTER case_open. Pass eids=[4624] \
                 for successful logons (Pool A persistence baseline), eids=[4688] for process \
                 creation, eids=[7045] for service install. Default limit 10000; lower it for \
                 dense system logs. Returns rows[] (event_id, ts, channel, record_id, data), \
                 parse_errors count (per-record failures swallowed, not aborted), and \
                 records_seen (pre-filter). \
                 ERRORS: EvtxNotFound (verify case_open succeeded and the path exists inside \
                 the mounted image), EvtxOpen (file is corrupt or not a real EVTX — check \
                 magic bytes 'ElfFile'), EvtxParseAllFailed (every record failed; the file \
                 is structurally broken — try a different copy of the log).",
            schema: || schema_for::<EvtxQueryInput>(),
            handler: |args| dispatch_evtx_query(args),
        },
        ToolEntry {
            name: "prefetch_parse",
            description:
                "Extract execution evidence from a Windows Prefetch (.pf) file. THIS IS THE \
                 CANONICAL 'did this binary actually run' artifact — combine it with \
                 amcache/shimcache for the SOUL.md ≥2 artifact-class corroboration rule. \
                 Handles MAM compression (Win10+) and uncompressed SCCA (Win7-/8.1) \
                 transparently. Returns executable_name, version (17/23/26/30 → \
                 XP/7/8.1/10), run_count, last_run_times_iso (UTC ISO-8601Z, up to 8 most \
                 recent on Win10+), file_references (DLLs/EXEs the binary loaded), and \
                 volume_paths. CAVEAT (per agent-config/MEMORY.md): prefetch can be disabled \
                 on SSDs (EnablePrefetcher=0); absence is NOT evidence of absence — surface \
                 that caveat in any finding that relies on prefetch absence. \
                 ERRORS: NotFound (verify the path), Unreadable (permissions / device error), \
                 ParseFailed (corrupt header or unsupported version — try a fresh copy).",
            schema: || schema_for::<PrefetchInput>(),
            handler: |args| dispatch_prefetch_parse(args),
        },
        ToolEntry {
            name: "mft_timeline",
            description: "Extract a timeline from an NTFS Master File Table ($MFT). Pair with \
                 prefetch_parse for the SOUL.md ≥2 artifact-class rule on execution claims: \
                 MFT proves the binary EXISTED on disk; Prefetch proves it RAN. Each row \
                 carries BOTH $SI (StandardInformation) and $FN (FileName) MAC times — the \
                 agent should compare them to detect timestomping ($SI is trivially \
                 stompable via SetFileTime; $FN updates only on rename/move and is \
                 tamper-evident). A binary whose $SI.modified is OLDER than $FN.modified is \
                 a strong tampering signal. Use since_iso/until_iso to focus on an incident \
                 window. Returns entries[] (record_number, parent_record, name, full_path, \
                 is_directory, is_allocated, logical_size, plus 4 $SI + 2 $FN times), \
                 parse_errors (per-record failures swallowed), and records_seen (pre-filter). \
                 ERRORS: MftNotFound (verify path), MftOpen (wrong magic — check the file is \
                 a real $MFT export, not a copy of the volume root), InvalidTimeFilter \
                 (since_iso/until_iso must be RFC 3339 / ISO-8601, e.g. 2026-04-25T00:00:00Z).",
            schema: || schema_for::<MftInput>(),
            handler: |args| dispatch_mft_timeline(args),
        },
    ]
}

fn schema_for<T: schemars::JsonSchema>() -> Value {
    let schema = schemars::schema_for!(T);
    serde_json::to_value(schema).expect("schemars output is JSON")
}

/// Parse one inbound line and produce the response line (or None for
/// notifications, which the spec says are not replied to).
fn dispatch(line: &str, registry: &[ToolEntry]) -> Option<String> {
    // Parse the message envelope. Malformed JSON is itself an error
    // response with a null id (we have no id to echo).
    let msg: Value = match serde_json::from_str(line) {
        Ok(v) => v,
        Err(err) => {
            return Some(make_error_response(
                &Value::Null,
                ERR_INVALID_PARAMS,
                &format!("malformed JSON: {err}"),
            ));
        }
    };

    let method = msg.get("method").and_then(|v| v.as_str()).unwrap_or("");
    let id = msg.get("id").cloned();
    let params = msg.get("params").cloned().unwrap_or(Value::Null);

    // Notifications have no id and expect no response.
    let is_notification = id.is_none();

    let result = match method {
        "initialize" => Ok(handle_initialize(&params)),
        "notifications/initialized" | "initialized" => {
            // Spec: notifications/initialized is fire-and-forget.
            return None;
        }
        "tools/list" => Ok(handle_tools_list(registry)),
        "tools/call" => handle_tools_call(&params, registry),
        "ping" => Ok(json!({})),
        other => Err(ToolError::InvalidParams(format!(
            "unknown method: {other:?}"
        ))),
    };

    if is_notification {
        // Method-call-without-id is a notification; even errors get swallowed.
        return None;
    }

    let id = id.unwrap_or(Value::Null);
    Some(match result {
        Ok(value) => make_success_response(&id, &value),
        Err(ToolError::InvalidParams(msg)) => make_error_response(&id, ERR_INVALID_PARAMS, &msg),
        Err(ToolError::Internal(msg)) => make_error_response(&id, ERR_INTERNAL, &msg),
    })
}

fn handle_initialize(_params: &Value) -> Value {
    json!({
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {
            "tools": {}
        },
        "serverInfo": {
            "name": SERVER_NAME,
            "version": CRATE_VERSION,
        },
    })
}

fn handle_tools_list(registry: &[ToolEntry]) -> Value {
    let tools: Vec<Value> = registry
        .iter()
        .map(|t| {
            json!({
                "name": t.name,
                "description": t.description,
                "inputSchema": (t.schema)(),
            })
        })
        .collect();
    json!({ "tools": tools })
}

fn handle_tools_call(params: &Value, registry: &[ToolEntry]) -> Result<Value, ToolError> {
    let name = params
        .get("name")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ToolError::InvalidParams("tools/call missing 'name'".to_string()))?;
    let arguments = params.get("arguments").cloned().unwrap_or(json!({}));

    let entry = registry
        .iter()
        .find(|t| t.name == name)
        .ok_or_else(|| ToolError::InvalidParams(format!("unknown tool: {name}")))?;

    let payload = (entry.handler)(arguments)?;
    let payload_text = serde_json::to_string(&payload)
        .map_err(|e| ToolError::Internal(format!("serialize tool output: {e}")))?;
    let sha = sha256_hex(payload_text.as_bytes());

    Ok(json!({
        "content": [
            {
                "type": "text",
                "text": payload_text,
            }
        ],
        "_meta": {
            "tool": name,
            "output_sha256": sha,
        },
    }))
}

// ---------------------------------------------------------------------------
// Per-tool dispatchers — validate input, call the typed handler,
// serialize the typed output back to JSON.
// ---------------------------------------------------------------------------

fn dispatch_case_open(args: Value) -> Result<Value, ToolError> {
    let input: CaseOpenInput = parse_args(args)?;
    let handle =
        case_open::case_open(&input).map_err(|e| ToolError::Internal(format!("case_open: {e}")))?;
    serde_json::to_value(handle).map_err(|e| ToolError::Internal(format!("serialize: {e}")))
}

fn dispatch_evtx_query(args: Value) -> Result<Value, ToolError> {
    let input: EvtxQueryInput = parse_args(args)?;
    let output = evtx_query(&input).map_err(|e| ToolError::Internal(format!("evtx_query: {e}")))?;
    serde_json::to_value(output).map_err(|e| ToolError::Internal(format!("serialize: {e}")))
}

fn dispatch_prefetch_parse(args: Value) -> Result<Value, ToolError> {
    let input: PrefetchInput = parse_args(args)?;
    let output =
        prefetch_parse(&input).map_err(|e| ToolError::Internal(format!("prefetch_parse: {e}")))?;
    serde_json::to_value(output).map_err(|e| ToolError::Internal(format!("serialize: {e}")))
}

fn dispatch_mft_timeline(args: Value) -> Result<Value, ToolError> {
    let input: MftInput = parse_args(args)?;
    // InvalidTimeFilter is user-facing input; surface as -32602 not -32603.
    match mft_timeline(&input) {
        Ok(output) => {
            serde_json::to_value(output).map_err(|e| ToolError::Internal(format!("serialize: {e}")))
        }
        Err(crate::tools::MftError::InvalidTimeFilter { value, reason }) => Err(
            ToolError::InvalidParams(format!("invalid time filter {value:?}: {reason}")),
        ),
        Err(e) => Err(ToolError::Internal(format!("mft_timeline: {e}"))),
    }
}

fn parse_args<T: DeserializeOwned>(args: Value) -> Result<T, ToolError> {
    serde_json::from_value(args).map_err(|e| ToolError::InvalidParams(format!("invalid args: {e}")))
}

// ---------------------------------------------------------------------------
// JSON-RPC envelope helpers.
// ---------------------------------------------------------------------------

fn make_success_response(id: &Value, result: &Value) -> String {
    serialize_envelope(&json!({
        "jsonrpc": "2.0",
        "id": id,
        "result": result,
    }))
}

fn make_error_response(id: &Value, code: i64, message: &str) -> String {
    serialize_envelope(&json!({
        "jsonrpc": "2.0",
        "id": id,
        "error": {
            "code": code,
            "message": message,
        },
    }))
}

fn serialize_envelope(value: &Value) -> String {
    serde_json::to_string(value).unwrap_or_else(|_| {
        // Pathological — should never happen; fall back to a valid
        // hand-crafted JSON-RPC parse-error.
        r#"{"jsonrpc":"2.0","id":null,"error":{"code":-32700,"message":"could not serialize response"}}"#
            .to_string()
    })
}

fn sha256_hex(bytes: &[u8]) -> String {
    let mut h = Sha256::new();
    h.update(bytes);
    hex::encode(h.finalize())
}

// Hand-rolled hex encoder removed — `hex` is already a dev-dep,
// promote to runtime.
//
// Note: the `hex` crate is in `[dev-dependencies]` for tests today;
// `Cargo.toml` should add it under `[dependencies]` for production
// use. Until that change lands the `hex::encode` call uses the
// `dev-dependencies` symbol via `cargo test`, so the server fails
// to link in `--release`. The Cargo.toml edit accompanies this file.

// ---------------------------------------------------------------------------
// Tests.
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    fn drive(input: &str) -> String {
        let mut output: Vec<u8> = Vec::new();
        run_stdio_server_with_streams(Cursor::new(input.as_bytes()), &mut output)
            .expect("server loop");
        String::from_utf8(output).expect("utf-8 output")
    }

    #[test]
    fn initialize_returns_protocol_version() {
        let req = r#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}"#;
        let out = drive(&format!("{req}\n"));
        let resp: Value = serde_json::from_str(out.trim()).unwrap();
        assert_eq!(resp["id"], 1);
        assert_eq!(resp["result"]["protocolVersion"], PROTOCOL_VERSION);
        assert_eq!(resp["result"]["serverInfo"]["name"], SERVER_NAME);
        assert!(resp["result"]["capabilities"]["tools"].is_object());
    }

    #[test]
    fn tools_list_advertises_all_tools() {
        let req = r#"{"jsonrpc":"2.0","id":2,"method":"tools/list"}"#;
        let out = drive(&format!("{req}\n"));
        let resp: Value = serde_json::from_str(out.trim()).unwrap();
        let tools = resp["result"]["tools"].as_array().unwrap();
        let names: Vec<&str> = tools.iter().map(|t| t["name"].as_str().unwrap()).collect();
        let expected = ["case_open", "evtx_query", "prefetch_parse", "mft_timeline"];
        assert_eq!(names.len(), expected.len());
        for want in expected {
            assert!(names.contains(&want), "missing {want}: {names:?}");
        }
        // Each must have an inputSchema dict.
        for tool in tools {
            assert!(tool["inputSchema"].is_object(), "schema missing for {tool}");
        }
    }

    #[test]
    fn unknown_tool_returns_invalid_params() {
        let req = r#"{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"no_such","arguments":{}}}"#;
        let out = drive(&format!("{req}\n"));
        let resp: Value = serde_json::from_str(out.trim()).unwrap();
        assert_eq!(resp["error"]["code"], ERR_INVALID_PARAMS);
        assert!(
            resp["error"]["message"]
                .as_str()
                .unwrap()
                .contains("no_such"),
            "{resp}"
        );
    }

    #[test]
    fn unknown_method_errors() {
        let req = r#"{"jsonrpc":"2.0","id":4,"method":"some/bogus"}"#;
        let out = drive(&format!("{req}\n"));
        let resp: Value = serde_json::from_str(out.trim()).unwrap();
        assert_eq!(resp["error"]["code"], ERR_INVALID_PARAMS);
    }

    #[test]
    fn malformed_json_error_keeps_loop_alive() {
        let lines = "not json\n{\"jsonrpc\":\"2.0\",\"id\":5,\"method\":\"ping\"}\n";
        let out = drive(lines);
        let mut iter = out.lines();
        let first: Value = serde_json::from_str(iter.next().unwrap()).unwrap();
        assert_eq!(first["error"]["code"], ERR_INVALID_PARAMS);
        let second: Value = serde_json::from_str(iter.next().unwrap()).unwrap();
        assert_eq!(second["id"], 5);
        assert!(second["result"].is_object());
    }

    #[test]
    fn notifications_initialized_produces_no_response() {
        let req = r#"{"jsonrpc":"2.0","method":"notifications/initialized"}"#;
        let out = drive(&format!("{req}\n"));
        assert!(
            out.is_empty(),
            "notification must not produce a response: {out:?}"
        );
    }

    #[test]
    fn tool_call_invalid_args_returns_invalid_params() {
        let req = r#"{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"case_open","arguments":{"image_path":42}}}"#;
        let out = drive(&format!("{req}\n"));
        let resp: Value = serde_json::from_str(out.trim()).unwrap();
        assert_eq!(resp["error"]["code"], ERR_INVALID_PARAMS);
    }

    #[test]
    fn case_open_against_real_file_succeeds() {
        let tmp = tempfile::tempdir().expect("tempdir");
        let img = tmp.path().join("evidence.E01");
        std::fs::write(&img, b"fake evidence bytes for hashing").unwrap();
        let home = tmp.path().join("home");
        std::env::set_var("FINDEVIL_HOME", &home);

        let req = format!(
            r#"{{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{{"name":"case_open","arguments":{{"image_path":{img:?}}}}}}}"#,
            img = img.to_string_lossy().replace('\\', "\\\\"),
        );
        let out = drive(&format!("{req}\n"));
        std::env::remove_var("FINDEVIL_HOME");

        let resp: Value = serde_json::from_str(out.trim()).expect(&out);
        assert!(resp["result"].is_object(), "expected success: {resp}");
        let body_text = resp["result"]["content"][0]["text"].as_str().unwrap();
        let body: Value = serde_json::from_str(body_text).unwrap();
        assert!(body["id"].is_string(), "case handle has id");
        assert_eq!(
            body["image_hash"].as_str().unwrap().len(),
            64,
            "image_hash is sha256-length: {body}"
        );
        // _meta.output_sha256 is sha256 of the serialized typed output.
        assert_eq!(
            resp["result"]["_meta"]["output_sha256"]
                .as_str()
                .unwrap()
                .len(),
            64
        );
    }
}
