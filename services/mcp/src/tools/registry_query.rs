//! `registry_query` — read keys + values from an offline Windows Registry hive.
//!
//! Spec #2 §6 + Pool A persistence territory. Registry hives are the
//! canonical Windows persistence surface: Run, `RunOnce`, IFEO, Services,
//! WMI subscription consumers, scheduled tasks (via Schedule\TaskCache).
//! This tool reads any offline hive file (NTUSER.DAT / SOFTWARE /
//! SYSTEM / SECURITY / SAM / a UsrClass.dat) without mounting it.
//!
//! Backed by `frnsc-hive = "=0.13.4"` (MIT, `ForensicRS`, same author as
//! `frnsc-prefetch` already used by `prefetch_parse`). The crate
//! integrates with `forensic-rs::traits::vfs::StdVirtualFS`, mirroring
//! the prefetch tool exactly.
//!
//! The tool intentionally normalizes the value-data side: `REG_SZ` /
//! `REG_EXPAND_SZ` / `REG_MULTI_SZ` are flattened to readable strings;
//! `REG_DWORD` / `REG_QWORD` become decimal; `REG_BINARY` is hex-encoded.
//! The agent gets a stable shape regardless of the underlying type and
//! can keyword-match against persistence indicators (`LOLBins`, certutil
//! invocations, `mshta http://...`, etc.) without juggling type-tagged
//! union output.

use std::path::{Path, PathBuf};

use forensic_rs::prelude::StdVirtualFS;
use forensic_rs::traits::registry::{RegHiveKey, RegValue, RegistryReader};
use forensic_rs::traits::vfs::{VirtualFile, VirtualFileSystem};
use frnsc_hive::reader::{HiveFiles, HiveRegistryReader};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use thiserror::Error;

const DEFAULT_LIMIT: usize = 10_000;
const MAX_RECURSION_DEPTH: usize = 16;

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct RegistryInput {
    /// Case ID from a prior `case_open` call. Accepted for audit-log
    /// correlation; not consumed by the parser.
    pub case_id: String,

    /// Absolute or relative path to the hive primary file (e.g. the
    /// `SOFTWARE` hive at `Windows/System32/config/SOFTWARE`, or a
    /// per-user `NTUSER.DAT`). Transaction logs (`.LOG1`, `.LOG2`) are
    /// not loaded by this tool — agents that need transaction-replay
    /// can pass a pre-merged hive.
    pub hive_path: PathBuf,

    /// Key path relative to the hive root, using either `\` or `/` as
    /// the separator. Empty string returns the root key. Common values:
    /// `Microsoft\Windows\CurrentVersion\Run` (Run keys), `Microsoft\
    /// Windows\CurrentVersion\Image File Execution Options` (IFEO),
    /// `ControlSet001\Services` (services). Optional `HKLM\` /
    /// `HKCU\` / `HKU\` prefix is stripped.
    pub key_path: String,

    /// When true, recursively descend into all subkeys and emit one
    /// entry per key visited. Capped at depth 16 + the limit below.
    /// Default false — non-recursive returns just the requested key.
    #[serde(default, skip_serializing_if = "is_false")]
    pub recursive: bool,

    /// Hard cap on total entries emitted. Default `10_000`. Use a smaller
    /// value (e.g. 100) for an interactive triage; larger when sweeping
    /// a known-large path like `Services`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub limit: Option<usize>,
}

#[allow(clippy::trivially_copy_pass_by_ref)]
const fn is_false(b: &bool) -> bool {
    !*b
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct RegistryValue {
    pub name: String,

    /// One of: `REG_SZ`, `REG_EXPAND_SZ`, `REG_MULTI_SZ`, `REG_DWORD`,
    /// `REG_QWORD`, `REG_BINARY`. Unknown types fall through to `REG_BINARY`.
    pub value_type: String,

    /// String-formatted data. `SZ/EXPAND_SZ/MULTI_SZ` → text (`MULTI_SZ` is
    /// joined by `|`). DWORD/QWORD → decimal. BINARY → lowercase hex
    /// (capped at 4096 bytes — longer values are truncated and tagged
    /// with `…[truncated, full N bytes]`).
    pub data_str: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct RegistryEntry {
    /// Path of the key under the hive root, using `\` separators.
    pub key_path: String,

    /// Key's `last_write_time` as UTC ISO-8601Z, or None if the
    /// underlying `KeyNode` reports a zero filetime (rare; usually a
    /// freshly-formatted hive's root).
    pub last_write_time_iso: Option<String>,

    /// All values directly attached to this key. Subkey-level values
    /// appear in their own entries when `recursive=true`.
    pub values: Vec<RegistryValue>,

    /// Names of direct subkeys (one level down). For full recursion,
    /// each subkey gets its own entry.
    pub subkeys: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct RegistryOutput {
    pub entries: Vec<RegistryEntry>,
    pub keys_visited: usize,
    pub parse_errors: usize,
}

#[derive(Debug, Error)]
pub enum RegistryError {
    #[error("registry hive not found: {0}")]
    HiveNotFound(PathBuf),

    #[error("registry hive unreadable {path}: {source}")]
    HiveUnreadable {
        path: PathBuf,
        #[source]
        source: std::io::Error,
    },

    /// Boxed because `forensic_rs::err::ForensicError` is large enough
    /// to push our `Result<_, RegistryError>` over clippy's
    /// `result_large_err` threshold.
    #[error("registry hive parse failed for {path}: {source}")]
    HiveOpen {
        path: PathBuf,
        #[source]
        source: Box<forensic_rs::err::ForensicError>,
    },

    #[error("registry key not found: {0}")]
    KeyNotFound(String),
}

/// Cheap pre-flight: file path looks like a registry hive.
///
/// We accept the canonical hive base names (case-insensitive) plus
/// any file whose extension is `.dat` (NTUSER.DAT / UsrClass.dat).
/// The actual parser is the source of truth on whether a file is
/// genuinely a hive.
#[must_use]
pub fn path_looks_like_hive(path: &Path) -> bool {
    if path
        .extension()
        .is_some_and(|e| e.eq_ignore_ascii_case("dat"))
    {
        return true;
    }
    let Some(name) = path.file_name().and_then(|s| s.to_str()) else {
        return false;
    };
    matches!(
        name.to_ascii_uppercase().as_str(),
        "SOFTWARE" | "SYSTEM" | "SECURITY" | "SAM" | "DEFAULT" | "NTUSER.DAT" | "USRCLASS.DAT"
    )
}

/// Read keys + values from an offline registry hive.
///
/// # Errors
/// * [`RegistryError::HiveNotFound`] — the file does not exist.
/// * [`RegistryError::HiveUnreadable`] — exists but cannot be opened
///   (permissions / I/O).
/// * [`RegistryError::HiveOpen`] — file is not a valid hive (wrong
///   magic / corrupt header).
/// * [`RegistryError::KeyNotFound`] — the requested key path does not
///   exist in this hive.
pub fn registry_query(input: &RegistryInput) -> Result<RegistryOutput, RegistryError> {
    let path = &input.hive_path;
    if !path.is_file() {
        return Err(RegistryError::HiveNotFound(path.clone()));
    }

    let mut fs = StdVirtualFS::new();
    let primary: Box<dyn VirtualFile> =
        fs.open(path).map_err(|err| RegistryError::HiveUnreadable {
            path: path.clone(),
            source: std::io::Error::other(err.to_string()),
        })?;

    let hive = HiveFiles::new(path.clone(), primary).map_err(|err| RegistryError::HiveOpen {
        path: path.clone(),
        source: Box::new(err),
    })?;

    let mut reader = HiveRegistryReader::new();
    // The hive type doesn't change which file is read; we always use
    // the same trait dispatch. set_software is an arbitrary choice —
    // open_key with HkeyLocalMachine routes into our single mounted
    // hive regardless of the hive's actual identity.
    reader.set_software(hive);

    let normalized = normalize_key_path(&input.key_path);
    let limit = input.limit.unwrap_or(DEFAULT_LIMIT);

    let mut output = RegistryOutput {
        entries: Vec::new(),
        keys_visited: 0,
        parse_errors: 0,
    };

    walk(&reader, &normalized, input.recursive, limit, 0, &mut output)?;

    Ok(output)
}

fn walk(
    reader: &HiveRegistryReader,
    key_path: &str,
    recursive: bool,
    limit: usize,
    depth: usize,
    output: &mut RegistryOutput,
) -> Result<(), RegistryError> {
    if output.entries.len() >= limit || depth > MAX_RECURSION_DEPTH {
        return Ok(());
    }

    let Ok(hkey) = reader.open_key(RegHiveKey::HkeyLocalMachine, key_path) else {
        // Top-level miss is a reportable error; deeper misses are
        // a "subkey vanished mid-walk" race that we count and skip.
        if depth == 0 {
            return Err(RegistryError::KeyNotFound(key_path.to_string()));
        }
        output.parse_errors += 1;
        return Ok(());
    };
    output.keys_visited += 1;

    let entry = build_entry(reader, hkey, key_path);
    let subkey_names = entry.subkeys.clone();
    output.entries.push(entry);
    reader.close_key(hkey);

    if recursive {
        for sub in subkey_names {
            if output.entries.len() >= limit {
                break;
            }
            let child_path = if key_path.is_empty() {
                sub.clone()
            } else {
                format!("{key_path}\\{sub}")
            };
            walk(reader, &child_path, recursive, limit, depth + 1, output)?;
        }
    }

    Ok(())
}

fn build_entry(reader: &HiveRegistryReader, hkey: RegHiveKey, key_path: &str) -> RegistryEntry {
    let last_write_time_iso = reader
        .key_info(hkey)
        .ok()
        .and_then(|info| filetime_to_iso(info.last_write_time.filetime()));

    let values: Vec<RegistryValue> = reader
        .enumerate_values(hkey)
        .unwrap_or_default()
        .into_iter()
        .map(|name| {
            let raw = reader.read_value(hkey, &name).ok();
            let (value_type, data_str) = format_value(raw.as_ref());
            RegistryValue {
                name,
                value_type,
                data_str,
            }
        })
        .collect();

    let subkeys = reader.enumerate_keys(hkey).unwrap_or_default();

    RegistryEntry {
        key_path: key_path.to_string(),
        last_write_time_iso,
        values,
        subkeys,
    }
}

fn format_value(value: Option<&RegValue>) -> (String, String) {
    match value {
        Some(RegValue::SZ(s)) => ("REG_SZ".into(), s.clone()),
        Some(RegValue::ExpandSZ(s)) => ("REG_EXPAND_SZ".into(), s.clone()),
        Some(RegValue::MultiSZ(parts)) => ("REG_MULTI_SZ".into(), parts.join("|")),
        Some(RegValue::DWord(n)) => ("REG_DWORD".into(), n.to_string()),
        Some(RegValue::QWord(n)) => ("REG_QWORD".into(), n.to_string()),
        Some(RegValue::Binary(bytes)) => {
            const MAX_HEX: usize = 4096;
            if bytes.len() <= MAX_HEX {
                ("REG_BINARY".into(), hex::encode(bytes))
            } else {
                let suffix = format!("…[truncated, full {} bytes]", bytes.len());
                let mut out = hex::encode(&bytes[..MAX_HEX]);
                out.push_str(&suffix);
                ("REG_BINARY".into(), out)
            }
        }
        None => ("REG_BINARY".into(), String::new()),
    }
}

fn normalize_key_path(input: &str) -> String {
    let trimmed = input.trim().trim_matches(|c| c == '\\' || c == '/');
    // Strip the optional HKLM\ / HKCU\ / HKU\ prefix the agent might
    // include — only the path inside the hive matters here.
    let without_prefix = trimmed
        .strip_prefix("HKLM\\")
        .or_else(|| trimmed.strip_prefix("HKEY_LOCAL_MACHINE\\"))
        .or_else(|| trimmed.strip_prefix("HKCU\\"))
        .or_else(|| trimmed.strip_prefix("HKEY_CURRENT_USER\\"))
        .or_else(|| trimmed.strip_prefix("HKU\\"))
        .or_else(|| trimmed.strip_prefix("HKEY_USERS\\"))
        .unwrap_or(trimmed);
    // Normalize forward slashes to backslashes to match the underlying
    // crate's expectation.
    without_prefix.replace('/', "\\")
}

// 116444736000000000 ticks = FILETIME for 1970-01-01 (Unix epoch).
const FILETIME_UNIX_EPOCH_TICKS: i64 = 116_444_736_000_000_000;

fn filetime_to_iso(raw: u64) -> Option<String> {
    if raw == 0 {
        return None;
    }
    let unix_100ns = i64::try_from(raw).ok()? - FILETIME_UNIX_EPOCH_TICKS;
    let secs = unix_100ns / 10_000_000;
    let nanos = u32::try_from((unix_100ns % 10_000_000) * 100).ok()?;
    let dt = chrono::DateTime::<chrono::Utc>::from_timestamp(secs, nanos)?;
    Some(dt.format("%Y-%m-%dT%H:%M:%SZ").to_string())
}
