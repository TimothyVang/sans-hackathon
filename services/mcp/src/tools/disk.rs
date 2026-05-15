//! Disk image mount/extract helpers.
//!
//! These tools intentionally expose a narrow typed surface rather than a
//! generic shell runner. Real mounting is best-effort on Unix/SIFT via fixed
//! tool invocations; tests and Windows use the explicit `mock` mode so normal
//! CI never needs FUSE, libewf, or administrator privileges.

use std::collections::BTreeMap;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::process::Command;

use chrono::Utc;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use thiserror::Error;
use uuid::Uuid;

const LEDGER_NAME: &str = "session_resources.json";
const STDERR_TAIL_BYTES: usize = 4096;
const DEFAULT_MAX_ARTIFACT_BYTES: u64 = 512 * 1024 * 1024;

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum DiskMode {
    Auto,
    Mock,
}

impl Default for DiskMode {
    fn default() -> Self {
        Self::Auto
    }
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ArtifactKind {
    Mft,
    UsnJrnl,
    Prefetch,
    Registry,
    Evtx,
    YaraTarget,
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DiskMountInput {
    pub case_id: String,
    pub image_path: PathBuf,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub mount_point: Option<PathBuf>,
    #[serde(default)]
    pub mode: DiskMode,
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DiskExtractArtifactsInput {
    pub case_id: String,
    pub mount_id: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub artifact_kinds: Vec<ArtifactKind>,
    #[serde(default = "default_limit")]
    pub limit: usize,
    #[serde(default = "default_max_artifact_bytes")]
    pub max_artifact_bytes: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DiskUnmountInput {
    pub case_id: String,
    pub mount_id: String,
    #[serde(default)]
    pub mode: DiskMode,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
pub struct DiskMountOutput {
    pub case_id: String,
    pub mount_id: String,
    pub status: String,
    pub image_path: PathBuf,
    pub mount_point: PathBuf,
    pub fs_root: PathBuf,
    pub ledger_path: PathBuf,
    pub command: Vec<String>,
    pub stderr_tail: String,
    pub note: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
pub struct ExtractedDiskArtifact {
    pub artifact_class: String,
    pub source_path: PathBuf,
    pub extracted_path: PathBuf,
    pub size_bytes: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
pub struct DiskExtractArtifactsOutput {
    pub case_id: String,
    pub mount_id: String,
    pub extract_id: String,
    pub output_dir: PathBuf,
    pub artifacts: Vec<ExtractedDiskArtifact>,
    pub artifacts_seen: usize,
    pub artifacts_skipped_oversize: usize,
    pub max_artifact_bytes: u64,
    pub ledger_path: PathBuf,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
pub struct DiskUnmountOutput {
    pub case_id: String,
    pub mount_id: String,
    pub status: String,
    pub ledger_path: PathBuf,
    pub command: Vec<String>,
    pub stderr_tail: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
pub struct SessionResource {
    pub id: String,
    pub resource_type: String,
    pub status: String,
    pub created_at: String,
    pub updated_at: String,
    pub image_path: Option<PathBuf>,
    pub mount_point: Option<PathBuf>,
    pub fs_root: Option<PathBuf>,
    pub parent_id: Option<String>,
    pub output_dir: Option<PathBuf>,
    pub artifacts: Vec<ExtractedDiskArtifact>,
    pub command: Vec<String>,
    pub note: String,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
struct SessionLedger {
    resources: Vec<SessionResource>,
}

#[derive(Debug, Error)]
pub enum DiskError {
    #[error("case not found: {0}")]
    CaseNotFound(String),
    #[error("evidence image not found: {0}")]
    ImageNotFound(PathBuf),
    #[error("mount resource not found: {0}")]
    MountNotFound(String),
    #[error("mount resource is not mounted: {0}")]
    MountNotMounted(String),
    #[error("mount root not found: {0}")]
    MountRootNotFound(PathBuf),
    #[error("unsupported on this platform without mode=mock")]
    UnsupportedPlatform,
    #[error("subprocess failed ({status}): {stderr_tail}")]
    SubprocessFailed { status: String, stderr_tail: String },
    #[error("io error at {path}: {source}")]
    Io { path: PathBuf, source: io::Error },
    #[error("cannot serialize session resource ledger: {0}")]
    Serialize(#[from] serde_json::Error),
}

pub fn disk_mount(input: &DiskMountInput) -> Result<DiskMountOutput, DiskError> {
    let case_dir = case_dir(&input.case_id)?;
    if !input.image_path.is_file() {
        return Err(DiskError::ImageNotFound(input.image_path.clone()));
    }
    let ledger_path = case_dir.join(LEDGER_NAME);
    let mount_id = format!("disk-mount-{}", Uuid::new_v4());
    let mount_point = input
        .mount_point
        .clone()
        .unwrap_or_else(|| case_dir.join("mounts").join(&mount_id));
    create_dir(&mount_point)?;

    let (status, fs_root, command, stderr_tail, note) = match input.mode {
        DiskMode::Mock => (
            "mounted".to_string(),
            mount_point.clone(),
            vec!["mock".to_string(), "disk_mount".to_string()],
            String::new(),
            "mock mount registered; no privileged filesystem operation ran".to_string(),
        ),
        DiskMode::Auto => auto_mount(&input.image_path, &mount_point)?,
    };

    let now = now_iso();
    let resource = SessionResource {
        id: mount_id.clone(),
        resource_type: "disk_mount".to_string(),
        status: status.clone(),
        created_at: now.clone(),
        updated_at: now,
        image_path: Some(input.image_path.clone()),
        mount_point: Some(mount_point.clone()),
        fs_root: Some(fs_root.clone()),
        parent_id: None,
        output_dir: None,
        artifacts: vec![],
        command: command.clone(),
        note: note.clone(),
    };
    upsert_resource(&ledger_path, resource)?;

    Ok(DiskMountOutput {
        case_id: input.case_id.clone(),
        mount_id,
        status,
        image_path: input.image_path.clone(),
        mount_point,
        fs_root,
        ledger_path,
        command,
        stderr_tail,
        note,
    })
}

pub fn disk_extract_artifacts(
    input: &DiskExtractArtifactsInput,
) -> Result<DiskExtractArtifactsOutput, DiskError> {
    let case_dir = case_dir(&input.case_id)?;
    let ledger_path = case_dir.join(LEDGER_NAME);
    let mut ledger = read_ledger(&ledger_path)?;
    let mount = ledger
        .resources
        .iter()
        .find(|r| r.id == input.mount_id && r.resource_type == "disk_mount")
        .cloned()
        .ok_or_else(|| DiskError::MountNotFound(input.mount_id.clone()))?;
    if mount.status != "mounted" {
        return Err(DiskError::MountNotMounted(input.mount_id.clone()));
    }
    let fs_root = mount
        .fs_root
        .ok_or_else(|| DiskError::MountNotMounted(input.mount_id.clone()))?;
    if !fs_root.is_dir() {
        return Err(DiskError::MountRootNotFound(fs_root));
    }

    let extract_id = format!("disk-extract-{}", Uuid::new_v4());
    let output_dir = case_dir.join("extracted").join("disk").join(&extract_id);
    create_dir(&output_dir)?;
    let wanted = wanted_kinds(&input.artifact_kinds);
    let mut artifacts = Vec::new();
    let mut artifacts_skipped_oversize = 0;
    let collection = ArtifactCollection {
        root: &fs_root,
        output_dir: &output_dir,
        wanted: &wanted,
        limit: input.limit,
        max_artifact_bytes: input.max_artifact_bytes,
    };
    collect_artifacts(
        &collection,
        &fs_root,
        &mut artifacts,
        &mut artifacts_skipped_oversize,
    )?;

    let now = now_iso();
    ledger.resources.push(SessionResource {
        id: extract_id.clone(),
        resource_type: "disk_extract_artifacts".to_string(),
        status: "extracted".to_string(),
        created_at: now.clone(),
        updated_at: now,
        image_path: mount.image_path,
        mount_point: mount.mount_point,
        fs_root: Some(fs_root),
        parent_id: Some(input.mount_id.clone()),
        output_dir: Some(output_dir.clone()),
        artifacts: artifacts.clone(),
        command: vec![
            "internal".to_string(),
            "copy_selected_artifacts".to_string(),
        ],
        note: "copied selected disk artifacts from mounted read-only view".to_string(),
    });
    write_ledger(&ledger_path, &ledger)?;

    Ok(DiskExtractArtifactsOutput {
        case_id: input.case_id.clone(),
        mount_id: input.mount_id.clone(),
        extract_id,
        output_dir,
        artifacts_seen: artifacts.len(),
        artifacts_skipped_oversize,
        max_artifact_bytes: input.max_artifact_bytes,
        artifacts,
        ledger_path,
    })
}

pub fn disk_unmount(input: &DiskUnmountInput) -> Result<DiskUnmountOutput, DiskError> {
    let case_dir = case_dir(&input.case_id)?;
    let ledger_path = case_dir.join(LEDGER_NAME);
    let mut ledger = read_ledger(&ledger_path)?;
    let idx = ledger
        .resources
        .iter()
        .position(|r| r.id == input.mount_id && r.resource_type == "disk_mount")
        .ok_or_else(|| DiskError::MountNotFound(input.mount_id.clone()))?;
    let mount_point = ledger.resources[idx]
        .mount_point
        .clone()
        .ok_or_else(|| DiskError::MountNotMounted(input.mount_id.clone()))?;

    let (status, command, stderr_tail) = match input.mode {
        DiskMode::Mock => (
            "unmounted".to_string(),
            vec!["mock".to_string(), "disk_unmount".to_string()],
            String::new(),
        ),
        DiskMode::Auto => auto_unmount(&mount_point)?,
    };
    ledger.resources[idx].status.clone_from(&status);
    ledger.resources[idx].updated_at = now_iso();
    ledger.resources[idx].command.clone_from(&command);
    write_ledger(&ledger_path, &ledger)?;

    Ok(DiskUnmountOutput {
        case_id: input.case_id.clone(),
        mount_id: input.mount_id.clone(),
        status,
        ledger_path,
        command,
        stderr_tail,
    })
}

fn auto_mount(
    image_path: &Path,
    mount_point: &Path,
) -> Result<(String, PathBuf, Vec<String>, String, String), DiskError> {
    if cfg!(windows) {
        return Err(DiskError::UnsupportedPlatform);
    }
    let ext = image_path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    if ext == "e01" || ext == "ex01" {
        let ewf_dir = mount_point.join("ewf");
        create_dir(&ewf_dir)?;
        let bin = std::env::var("EWF_MOUNT_BIN").unwrap_or_else(|_| "ewfmount".to_string());
        let args = vec![
            image_path.to_string_lossy().to_string(),
            ewf_dir.to_string_lossy().to_string(),
        ];
        let result = run_fixed(&bin, &args)?;
        if !result.0 {
            return Err(DiskError::SubprocessFailed {
                status: result.1,
                stderr_tail: result.2,
            });
        }
        return Ok((
            "mounted".to_string(),
            ewf_dir,
            std::iter::once(bin).chain(args).collect(),
            result.2,
            "mounted EWF container read-only; filesystem volume may require SIFT loop/TSK extraction".to_string(),
        ));
    }
    let bin = std::env::var("FINDEVIL_MOUNT_BIN").unwrap_or_else(|_| "mount".to_string());
    let args = vec![
        "-o".to_string(),
        "ro,loop".to_string(),
        image_path.to_string_lossy().to_string(),
        mount_point.to_string_lossy().to_string(),
    ];
    let result = run_fixed(&bin, &args)?;
    if !result.0 {
        return Err(DiskError::SubprocessFailed {
            status: result.1,
            stderr_tail: result.2,
        });
    }
    Ok((
        "mounted".to_string(),
        mount_point.to_path_buf(),
        std::iter::once(bin).chain(args).collect(),
        result.2,
        "mounted raw image read-only with loop device".to_string(),
    ))
}

fn auto_unmount(mount_point: &Path) -> Result<(String, Vec<String>, String), DiskError> {
    if cfg!(windows) {
        return Err(DiskError::UnsupportedPlatform);
    }
    let bin = std::env::var("FINDEVIL_UMOUNT_BIN").unwrap_or_else(|_| "umount".to_string());
    let args = vec![mount_point.to_string_lossy().to_string()];
    let result = run_fixed(&bin, &args)?;
    if !result.0 {
        return Err(DiskError::SubprocessFailed {
            status: result.1,
            stderr_tail: result.2,
        });
    }
    Ok((
        "unmounted".to_string(),
        std::iter::once(bin).chain(args).collect(),
        result.2,
    ))
}

fn run_fixed(bin: &str, args: &[String]) -> Result<(bool, String, String), DiskError> {
    let output = Command::new(bin)
        .args(args)
        .output()
        .map_err(|source| DiskError::Io {
            path: PathBuf::from(bin),
            source,
        })?;
    Ok((
        output.status.success(),
        output.status.to_string(),
        tail_utf8_lossy(&output.stderr),
    ))
}

struct ArtifactCollection<'a> {
    root: &'a Path,
    output_dir: &'a Path,
    wanted: &'a BTreeMap<&'static str, bool>,
    limit: usize,
    max_artifact_bytes: u64,
}

fn collect_artifacts(
    collection: &ArtifactCollection<'_>,
    dir: &Path,
    out: &mut Vec<ExtractedDiskArtifact>,
    skipped_oversize: &mut usize,
) -> Result<(), DiskError> {
    if out.len() >= collection.limit {
        return Ok(());
    }
    for entry in fs::read_dir(dir).map_err(|source| DiskError::Io {
        path: dir.to_path_buf(),
        source,
    })? {
        let entry = entry.map_err(|source| DiskError::Io {
            path: dir.to_path_buf(),
            source,
        })?;
        let path = entry.path();
        let ft = entry.file_type().map_err(|source| DiskError::Io {
            path: path.clone(),
            source,
        })?;
        if ft.is_dir() {
            collect_artifacts(collection, &path, out, skipped_oversize)?;
        } else if ft.is_file() {
            if let Some(class) = classify_artifact(collection.root, &path) {
                if collection.wanted.get(class).copied().unwrap_or(false) {
                    copy_artifact(
                        collection.root,
                        &path,
                        collection.output_dir,
                        class,
                        collection.max_artifact_bytes,
                        out,
                        skipped_oversize,
                    )?;
                    if out.len() >= collection.limit {
                        return Ok(());
                    }
                }
            }
        }
    }
    Ok(())
}

fn copy_artifact(
    root: &Path,
    source: &Path,
    output_dir: &Path,
    class: &str,
    max_artifact_bytes: u64,
    out: &mut Vec<ExtractedDiskArtifact>,
    skipped_oversize: &mut usize,
) -> Result<(), DiskError> {
    let source_size = fs::metadata(source)
        .map_err(|source_err| DiskError::Io {
            path: source.to_path_buf(),
            source: source_err,
        })?
        .len();
    if source_size > max_artifact_bytes {
        *skipped_oversize += 1;
        return Ok(());
    }
    let rel = source.strip_prefix(root).unwrap_or(source);
    let dest = output_dir.join(class).join(rel);
    if let Some(parent) = dest.parent() {
        create_dir(parent)?;
    }
    fs::copy(source, &dest).map_err(|source_err| DiskError::Io {
        path: source.to_path_buf(),
        source: source_err,
    })?;
    let size = fs::metadata(&dest)
        .map_err(|source_err| DiskError::Io {
            path: dest.clone(),
            source: source_err,
        })?
        .len();
    out.push(ExtractedDiskArtifact {
        artifact_class: class.to_string(),
        source_path: source.to_path_buf(),
        extracted_path: dest,
        size_bytes: size,
    });
    Ok(())
}

fn classify_artifact(root: &Path, path: &Path) -> Option<&'static str> {
    let name = path.file_name()?.to_string_lossy().to_ascii_lowercase();
    let rel = path
        .strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
        .to_ascii_lowercase();
    if name == "$mft" || name == "mft" {
        Some("mft")
    } else if name == "$j" || rel.contains("$usnjrnl") || has_extension(&name, "usn") {
        Some("usnjrnl")
    } else if has_extension(&name, "pf") {
        Some("prefetch")
    } else if matches!(
        name.as_str(),
        "software" | "system" | "sam" | "security" | "ntuser.dat" | "usrclass.dat"
    ) {
        Some("registry")
    } else if has_extension(&name, "evtx") {
        Some("evtx")
    } else if rel.starts_with("users/")
        || rel.contains("/users/")
        || rel.starts_with("programdata/")
        || rel.contains("/programdata/")
        || rel.starts_with("windows/temp/")
        || rel.contains("/windows/temp/")
    {
        Some("yara_target")
    } else {
        None
    }
}

fn wanted_kinds(kinds: &[ArtifactKind]) -> BTreeMap<&'static str, bool> {
    let mut wanted = BTreeMap::new();
    let classes: Vec<&'static str> = if kinds.is_empty() {
        vec![
            "mft",
            "usnjrnl",
            "prefetch",
            "registry",
            "evtx",
            "yara_target",
        ]
    } else {
        kinds
            .iter()
            .map(|k| match k {
                ArtifactKind::Mft => "mft",
                ArtifactKind::UsnJrnl => "usnjrnl",
                ArtifactKind::Prefetch => "prefetch",
                ArtifactKind::Registry => "registry",
                ArtifactKind::Evtx => "evtx",
                ArtifactKind::YaraTarget => "yara_target",
            })
            .collect()
    };
    for class in classes {
        wanted.insert(class, true);
    }
    wanted
}

fn case_dir(case_id: &str) -> Result<PathBuf, DiskError> {
    let dir = findevil_home()?.join("cases").join(case_id);
    if dir.is_dir() {
        Ok(dir)
    } else {
        Err(DiskError::CaseNotFound(case_id.to_string()))
    }
}

fn findevil_home() -> Result<PathBuf, DiskError> {
    if let Ok(v) = std::env::var("FINDEVIL_HOME") {
        if !v.is_empty() {
            return Ok(PathBuf::from(v));
        }
    }
    if let Ok(h) = std::env::var("HOME") {
        if !h.is_empty() {
            return Ok(PathBuf::from(h).join(".findevil"));
        }
    }
    if let Ok(p) = std::env::var("USERPROFILE") {
        if !p.is_empty() {
            return Ok(PathBuf::from(p).join(".findevil"));
        }
    }
    Err(DiskError::CaseNotFound("FINDEVIL_HOME".to_string()))
}

fn read_ledger(path: &Path) -> Result<SessionLedger, DiskError> {
    if !path.exists() {
        return Ok(SessionLedger::default());
    }
    let text = fs::read_to_string(path).map_err(|source| DiskError::Io {
        path: path.to_path_buf(),
        source,
    })?;
    serde_json::from_str(&text).map_err(DiskError::Serialize)
}

fn write_ledger(path: &Path, ledger: &SessionLedger) -> Result<(), DiskError> {
    let text = serde_json::to_string_pretty(ledger)?;
    fs::write(path, text).map_err(|source| DiskError::Io {
        path: path.to_path_buf(),
        source,
    })
}

fn upsert_resource(path: &Path, resource: SessionResource) -> Result<(), DiskError> {
    let mut ledger = read_ledger(path)?;
    ledger.resources.retain(|r| r.id != resource.id);
    ledger.resources.push(resource);
    write_ledger(path, &ledger)
}

fn create_dir(path: &Path) -> Result<(), DiskError> {
    fs::create_dir_all(path).map_err(|source| DiskError::Io {
        path: path.to_path_buf(),
        source,
    })
}

fn now_iso() -> String {
    Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string()
}

const fn default_limit() -> usize {
    500
}

const fn default_max_artifact_bytes() -> u64 {
    DEFAULT_MAX_ARTIFACT_BYTES
}

fn has_extension(name: &str, ext: &str) -> bool {
    Path::new(name)
        .extension()
        .is_some_and(|actual| actual.eq_ignore_ascii_case(ext))
}

fn tail_utf8_lossy(bytes: &[u8]) -> String {
    let start = bytes.len().saturating_sub(STDERR_TAIL_BYTES);
    String::from_utf8_lossy(&bytes[start..]).to_string()
}
