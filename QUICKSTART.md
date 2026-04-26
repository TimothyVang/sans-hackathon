# Find Evil! — Quickstart

Three things to get you investigating evidence with the agent.

---

## 1. Pick your environment (one-time, ~15 min)

Two paths. Pick whichever matches your situation.

### Path A — SIFT VM (recommended; matches the SANS judging environment)

```bash
# From the repo root, on Windows with VMware Workstation installed
# and the OVA at sift-2026.03.24.ova in the repo root:
bash scripts/sift-vm-bootstrap.sh
```

This converts the OVA, boots the VM headless, installs Rust + DFIR tools inside, sets up the SSH transport, and rewrites `.mcp.json.sift` to point at the running VM. Runs ~15 min on first invocation; subsequent runs detect existing state and skip.

### Path B — Local Windows host (faster iteration)

```bash
# Install the four DFIR-tool binaries on Windows (one-time):
winget install Volatility3 || pip install volatility3
winget install Hayabusa  # or download from github.com/Yamato-Security/hayabusa/releases
winget install Velociraptor  # or github.com/Velocidex/velociraptor/releases
# YARA-X is already in our crate; no separate install needed.

# That's it — `.mcp.json` points at local subprocesses by default.
```

---

## 2. Open Claude Code in this repo

Two equivalent commands:

```bash
# Local mode:
scripts/find-evil
# or:
claude-code .

# SIFT-VM mode:
bash scripts/find-evil-sift
```

`.mcp.json` (or `.mcp.json.sift`, swapped automatically) tells Claude Code to spawn both MCP servers — `findevil-mcp` (Rust, 11 typed DFIR tools) and `findevil-agent-mcp` (Python, 10 typed crypto/ACH tools). The agent now has its tool surface.

---

## 3. Investigate

In the Claude Code session, prompt:

> investigate `<path-to-evidence>`

Examples:

```
# A disk image:
investigate /mnt/hgfs/evidence/disk-images/base-dc-cdrive.E01

# A memory image:
investigate /mnt/hgfs/evidence/extracted/base-dc/base-dc-memory.img

# A single EVTX:
investigate /mnt/hgfs/evidence/single-evtx/Security.evtx
```

The agent reads `agent-config/SOUL.md` → `AGENTS.md` → `PLAYBOOK.md` → `TOOLS.md` → `MEMORY.md` → `HEARTBEAT.md` at session start, then drives the playbook tool sequence for that evidence type. You'll see:

1. `case_open` — SHA-256 of the evidence (chain of custody starts here)
2. **Pool A** (persistence) and **Pool B** (exfil) subagents fork in parallel and run their tool sequences
3. Findings emerge tagged with `tool_call_id`, MITRE ATT&CK technique, and confidence (CONFIRMED / INFERRED / HYPOTHESIS)
4. `detect_contradictions` surfaces Pool A vs Pool B disagreements **before** the judge merges
5. `judge_findings` + `correlate_findings` apply credibility weighting + the SOUL.md ≥2 artifact-class rule
6. `manifest_finalize` builds the Merkle tree, signs with sigstore, writes `run.manifest.json`
7. (Optional) `ots_stamp` anchors the manifest to Bitcoin via OpenTimestamps for FRE 902(14) self-authentication

Output lands at `~/.findevil/cases/<case_id>/` (or inside the VM at `/home/sansforensics/find-evil/tmp/<case_id>/` in SIFT-VM mode).

---

## Recommended reading order if anything goes wrong

| Question | File to read |
|---|---|
| "How do I avoid false positives?" | `docs/false-positives.md` |
| "What does the agent actually do during an investigation?" | `agent-config/PLAYBOOK.md` |
| "What's the architecture?" | `docs/architecture.md` |
| "What evidence is available?" | `docs/DATASET.md` |
| "What if a tool is missing?" | The agent will return `BinaryNotFound -32602`. Install the binary OR set the env var pointing at it (e.g. `VOLATILITY_BIN=/path/to/vol`). |
| "How do I verify a manifest someone else produced?" | `manifest_verify` MCP tool. Or `ots verify run.manifest.ots` for the Bitcoin anchor. |
| "How do I extend the tool surface?" | Each new MCP wrapper takes ~30-60 minutes following the pattern at `services/mcp/src/tools/vol_pslist.rs`. See the existing 11 tools for templates. |

---

## Anti-patterns

* **Don't** trust HYPOTHESIS-tier findings without verification. The agent prefixes them with the literal word "hypothesis:" — those are leads, not facts.
* **Don't** skip the synthetic-benign baseline (`goldens/synthetic-benign/`) — running on benign data first calibrates your false-positive floor.
* **Don't** modify evidence files. The chain-of-custody invariant (CLAUDE.md) is filesystem-enforced; any write to `/evidence/<case_id>/` from outside the agent invalidates the manifest's claims.
* **Don't** add `execute_shell` or any tool that takes arbitrary commands. The "narrow typed surface" is the architectural pitch; widening it forfeits that.

---

## End-of-investigation checklist

1. [ ] `manifest_verify` returns `overall=True`, all four sub-checks green
2. [ ] Findings table reviewed; CONFIRMED-tier findings traced back to their `tool_call_id` in `audit.jsonl`
3. [ ] Contradictions resolved or explicitly flagged in the report
4. [ ] Cross-host corroboration done (if multi-host case)
5. [ ] Synthetic-benign baseline run produced zero findings
6. [ ] `ots_stamp` Bitcoin anchor receipt obtained (if outbound network available)
7. [ ] Report rendered to PDF (the agent can do this; see `docs/reports/2026-04-26-srl2018-dc-investigation.pdf` for an example)

If all 7 are checked, you're done. If any are skipped, document the reason in the report's §8 (Limitations).
