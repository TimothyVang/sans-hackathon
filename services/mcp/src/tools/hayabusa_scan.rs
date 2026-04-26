//! `hayabusa_scan` — subprocess wrapper for the Hayabusa Sigma scanner.
//!
//! Spec #2 §6 + invariant: Hayabusa is AGPL-3.0, so per CLAUDE.md
//! "AGPL/GPL tools are subprocess-only — never linked". This tool
//! shells out to the `hayabusa` binary and parses its JSON output;
//! we never link the Hayabusa code into our Apache-2.0 binary.
//!
//! Pool A persistence detection — Hayabusa runs Sigma rules against
//! Windows EVTX logs and surfaces alerts (suspicious logons, service
//! installs, scheduled-task creates, persistence-classified events).
//! Use AFTER `case_open` to scan an extracted EVTX directory.
//!
//! Hayabusa invocation: `hayabusa json-timeline -d <evtx_dir> -o
//! <output.json> [-m <min_level>]`. We capture the JSON, parse it,
//! and emit a typed Alert list.
//!
//! Binary location: PATH lookup, overridable via `$HAYABUSA_BIN`.

use std::path::PathBuf;
use std::process::Command;

use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use thiserror::Error;

const DEFAULT_LIMIT: usize = 10_000;

/// Sigma rule severity levels Hayabusa knows. Names mirror the CLI's
/// `-m` flag; agent passes one of these as the minimum threshold.
const VALID_LEVELS: &[&str] = &["informational", "low", "medium", "high", "critical"];

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct HayabusaInput {
    /// Case ID from a prior `case_open` call.
    pub case_id: String,

    /// Directory containing `.evtx` files to scan. Hayabusa walks the
    /// directory recursively. A typical value is the case dir's
    /// `Logs/` subdirectory after evidence extraction.
    pub evtx_dir: PathBuf,

    /// Optional path to a Hayabusa rules directory (override the
    /// default bundled rules). When omitted, Hayabusa uses whatever
    /// rules ship with its binary — this is what most analysts want.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub rule_set: Option<PathBuf>,

    /// Minimum Sigma severity to emit. One of `informational`, `low`,
    /// `medium`, `high`, `critical`. Default `low` (informational
    /// floods the agent context with noise; low+ is the right
    /// triage starting point).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub min_level: Option<String>,

    /// Hard cap on alerts emitted. Default `10_000`. Hayabusa can
    /// generate tens of thousands of alerts on a busy DC; the limit
    /// keeps responses bounded.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub limit: Option<usize>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct HayabusaAlert {
    /// UTC ISO-8601 timestamp of the matched event.
    pub timestamp_iso: String,

    /// Sigma rule name (or rule title in newer Hayabusa output).
    pub rule: String,

    /// Severity level (informational / low / medium / high / critical).
    pub level: String,

    /// Windows EVTX channel (e.g. `Security`, `Microsoft-Windows-Sysmon/Operational`).
    pub channel: String,

    /// Numeric Windows Event ID.
    pub event_id: u32,

    /// Hostname / Computer name from the event.
    pub computer: String,

    /// Extracted detail fields from the matched event (raw map; keys
    /// vary by event type, e.g. `SubjectUserName`, `TargetFilename`).
    pub details: serde_json::Map<String, serde_json::Value>,
}

#[derive(Clone, Debug, Serialize)]
pub struct HayabusaOutput {
    pub alerts: Vec<HayabusaAlert>,

    /// Total alerts Hayabusa reported before our limit was applied.
    pub alerts_seen: usize,

    /// Stderr tail captured from the Hayabusa subprocess; useful for
    /// surfacing rule-load warnings or evtx-parse errors. Capped at
    /// 4096 bytes.
    pub stderr_tail: String,
}

#[derive(Debug, Error)]
pub enum HayabusaError {
    #[error("evtx_dir not found: {0}")]
    EvtxDirNotFound(PathBuf),

    #[error("evtx_dir is not a directory: {0}")]
    EvtxDirNotDirectory(PathBuf),

    #[error("rule_set not found: {0}")]
    RuleSetNotFound(PathBuf),

    #[error(
        "hayabusa binary not on PATH (set $HAYABUSA_BIN to override). \
         Install: https://github.com/Yamato-Security/hayabusa/releases"
    )]
    BinaryNotFound,

    #[error("hayabusa exited {exit_code}: {stderr}")]
    SubprocessFailed { exit_code: i32, stderr: String },

    #[error("could not parse hayabusa JSON output: {0}")]
    OutputParse(String),

    #[error(
        "invalid min_level {0:?}; expected one of: informational, low, medium, high, critical"
    )]
    InvalidMinLevel(String),
}

/// Run Hayabusa against an EVTX directory and parse its alerts.
///
/// # Errors
/// * [`HayabusaError::EvtxDirNotFound`] / [`HayabusaError::EvtxDirNotDirectory`] —
///   the supplied `evtx_dir` is missing or not a directory.
/// * [`HayabusaError::RuleSetNotFound`] — `rule_set` was supplied but does not exist.
/// * [`HayabusaError::BinaryNotFound`] — `hayabusa` not on PATH and `$HAYABUSA_BIN` unset.
/// * [`HayabusaError::SubprocessFailed`] — the binary returned non-zero.
/// * [`HayabusaError::OutputParse`] — the binary's JSON output was malformed.
/// * [`HayabusaError::InvalidMinLevel`] — `min_level` not in the recognized set.
pub fn hayabusa_scan(input: &HayabusaInput) -> Result<HayabusaOutput, HayabusaError> {
    if !input.evtx_dir.exists() {
        return Err(HayabusaError::EvtxDirNotFound(input.evtx_dir.clone()));
    }
    if !input.evtx_dir.is_dir() {
        return Err(HayabusaError::EvtxDirNotDirectory(input.evtx_dir.clone()));
    }
    if let Some(ref rules) = input.rule_set {
        if !rules.exists() {
            return Err(HayabusaError::RuleSetNotFound(rules.clone()));
        }
    }
    if let Some(ref level) = input.min_level {
        if !VALID_LEVELS.iter().any(|v| v.eq_ignore_ascii_case(level)) {
            return Err(HayabusaError::InvalidMinLevel(level.clone()));
        }
    }

    let binary = resolve_binary()?;
    let limit = input.limit.unwrap_or(DEFAULT_LIMIT);

    // Hayabusa writes JSON to a file (the CLI doesn't reliably stream
    // a clean JSON document to stdout — its progress UI mixes in).
    let output_dir = std::env::temp_dir();
    let output_file = output_dir.join(format!(
        "hayabusa-{}-{}.json",
        std::process::id(),
        nanosecond_tag()
    ));

    let mut cmd = Command::new(&binary);
    cmd.arg("json-timeline")
        .arg("-d")
        .arg(&input.evtx_dir)
        .arg("-o")
        .arg(&output_file)
        // Quiet mode suppresses the progress banner; hayabusa-cli has -q
        // as a global. Older versions ignore unknown flags so this is
        // forward-compatible.
        .arg("-q");
    if let Some(ref rules) = input.rule_set {
        cmd.arg("-r").arg(rules);
    }
    if let Some(ref level) = input.min_level {
        cmd.arg("-m").arg(level.to_lowercase());
    }

    let proc = cmd.output().map_err(|err| {
        // Treat ENOENT specifically as the "binary missing" path even
        // though we resolved it above — race conditions where the
        // binary disappeared between resolution and exec are rare but
        // surface this way.
        if err.kind() == std::io::ErrorKind::NotFound {
            HayabusaError::BinaryNotFound
        } else {
            HayabusaError::SubprocessFailed {
                exit_code: -1,
                stderr: format!("spawn failed: {err}"),
            }
        }
    })?;

    let stderr_tail = truncate_to(String::from_utf8_lossy(&proc.stderr).into_owned(), 4096);

    if !proc.status.success() {
        let _ = std::fs::remove_file(&output_file);
        return Err(HayabusaError::SubprocessFailed {
            exit_code: proc.status.code().unwrap_or(-1),
            stderr: stderr_tail,
        });
    }

    let body = match std::fs::read_to_string(&output_file) {
        Ok(b) => b,
        Err(err) => {
            return Err(HayabusaError::OutputParse(format!(
                "could not read output {}: {err}",
                output_file.display()
            )));
        }
    };
    // Best-effort cleanup; we don't propagate the error if remove
    // fails because the scan succeeded already.
    let _ = std::fs::remove_file(&output_file);

    parse_alerts(&body, limit, stderr_tail)
}

fn resolve_binary() -> Result<PathBuf, HayabusaError> {
    if let Ok(env_path) = std::env::var("HAYABUSA_BIN") {
        let p = PathBuf::from(env_path);
        if p.is_file() {
            return Ok(p);
        }
    }
    // PATH lookup. We don't pull in the `which` crate; std::process::
    // Command will resolve it implicitly when we exec, but we want
    // an EARLY error when the binary is missing — otherwise the user
    // gets a confusing "spawn failed" message after we've already
    // built the temp output file.
    if let Ok(path_var) = std::env::var("PATH") {
        let bin_name = if cfg!(windows) {
            "hayabusa.exe"
        } else {
            "hayabusa"
        };
        for dir in std::env::split_paths(&path_var) {
            let candidate = dir.join(bin_name);
            if candidate.is_file() {
                return Ok(candidate);
            }
        }
    }
    Err(HayabusaError::BinaryNotFound)
}

fn parse_alerts(
    body: &str,
    limit: usize,
    stderr_tail: String,
) -> Result<HayabusaOutput, HayabusaError> {
    // Hayabusa's json-timeline emits either:
    //   1. A JSON array (older versions): [ { "...alert..." }, ... ]
    //   2. JSONL (newer versions): one JSON object per line.
    // We accept both shapes. Empty body = no alerts.
    let trimmed = body.trim();
    if trimmed.is_empty() {
        return Ok(HayabusaOutput {
            alerts: Vec::new(),
            alerts_seen: 0,
            stderr_tail,
        });
    }

    let alerts: Vec<serde_json::Value> = if trimmed.starts_with('[') {
        serde_json::from_str(trimmed).map_err(|e| HayabusaError::OutputParse(e.to_string()))?
    } else {
        // JSONL — one object per line.
        let mut parsed = Vec::new();
        for (idx, line) in trimmed.lines().enumerate() {
            let line = line.trim();
            if line.is_empty() {
                continue;
            }
            match serde_json::from_str::<serde_json::Value>(line) {
                Ok(v) => parsed.push(v),
                Err(e) => {
                    return Err(HayabusaError::OutputParse(format!(
                        "line {}: {}",
                        idx + 1,
                        e
                    )));
                }
            }
        }
        parsed
    };

    let alerts_seen = alerts.len();
    let mut out = Vec::with_capacity(alerts_seen.min(limit));
    for value in alerts.into_iter().take(limit) {
        out.push(json_value_to_alert(&value));
    }

    Ok(HayabusaOutput {
        alerts: out,
        alerts_seen,
        stderr_tail,
    })
}

/// Best-effort projection of one Hayabusa JSON record into our typed
/// shape. Hayabusa's field names have shifted across versions; this
/// function tolerates a couple of common spellings and falls back
/// to empty strings rather than failing — the agent gets *something*
/// for every record, even from an unfamiliar Hayabusa build.
fn json_value_to_alert(v: &serde_json::Value) -> HayabusaAlert {
    let map = v.as_object().cloned().unwrap_or_default();
    let pick_str = |keys: &[&str]| -> String {
        for k in keys {
            if let Some(val) = map.get(*k) {
                if let Some(s) = val.as_str() {
                    return s.to_string();
                }
            }
        }
        String::new()
    };
    let pick_u32 = |keys: &[&str]| -> u32 {
        for k in keys {
            if let Some(val) = map.get(*k) {
                if let Some(n) = val.as_u64() {
                    return u32::try_from(n).unwrap_or(0);
                }
                if let Some(s) = val.as_str() {
                    if let Ok(n) = s.parse::<u32>() {
                        return n;
                    }
                }
            }
        }
        0
    };

    let timestamp_iso = pick_str(&["Timestamp", "timestamp", "@timestamp", "ts"]);
    let rule = pick_str(&["RuleTitle", "RuleName", "rule", "title"]);
    let level = pick_str(&["Level", "level", "severity"]);
    let channel = pick_str(&["Channel", "channel"]);
    let computer = pick_str(&["Computer", "computer", "Hostname"]);
    let event_id = pick_u32(&["EventID", "EventId", "event_id", "EID"]);

    // Anything not in the canonical fields gets dumped into details
    // so the agent can still see context-specific data.
    let mut details = serde_json::Map::new();
    let canonical: &[&str] = &[
        "Timestamp",
        "timestamp",
        "@timestamp",
        "ts",
        "RuleTitle",
        "RuleName",
        "rule",
        "title",
        "Level",
        "level",
        "severity",
        "Channel",
        "channel",
        "Computer",
        "computer",
        "Hostname",
        "EventID",
        "EventId",
        "event_id",
        "EID",
    ];
    for (k, v) in &map {
        if !canonical.contains(&k.as_str()) {
            details.insert(k.clone(), v.clone());
        }
    }

    HayabusaAlert {
        timestamp_iso,
        rule,
        level,
        channel,
        event_id,
        computer,
        details,
    }
}

fn truncate_to(mut s: String, max: usize) -> String {
    if s.len() > max {
        // Walk to the nearest char boundary. Hayabusa is a Yamato Security
        // project — its stderr is Japanese-friendly and contains multi-byte
        // codepoints. `String::truncate` panics if the cut splits a
        // codepoint; this avoids that.
        let mut boundary = max;
        while boundary > 0 && !s.is_char_boundary(boundary) {
            boundary -= 1;
        }
        s.truncate(boundary);
        s.push_str("…[truncated]");
    }
    s
}

fn nanosecond_tag() -> u128 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |d| d.as_nanos())
}
