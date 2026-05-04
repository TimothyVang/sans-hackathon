# Researched DFIR Automation Improvement Prompt

Date: 2026-05-04

Use this prompt in a coding-agent session to improve Find Evil! automation with public research from MITRE ATT&CK, SANS course themes, GitHub tool projects, DFIR blogs, and Reddit/community practitioner signals. The goal is sharper investigation automation and better coverage reporting, not a claim that the product replaces certified GCFA, GNFA, or GREM analysts.

## Research Basis

Primary anchors:

- MITRE ATT&CK data sources: process `DS0009`, network traffic `DS0029`, Windows Registry `DS0024`, file `DS0022`, command `DS0017`, script `DS0012`, scheduled job `DS0003`, service `DS0019`, kernel `DS0008`, module `DS0011`, logon session `DS0028`, domain name `DS0038`.
- MITRE ATT&CK automation model: use STIX/TAXII or pinned static mappings for technique/data-source coverage and keep mappings explainable in reports.
- MITRE ATT&CK techniques to prioritize: `T1059` command and scripting interpreter, `T1059.001` PowerShell, `T1059.003` Windows Command Shell, `T1047` WMI, `T1021.001` RDP, `T1003.001` LSASS credential dumping, `T1014` rootkit, `T1027` obfuscated files or information, `T1036` masquerading, `T1053` scheduled task/job, `T1071` application layer protocol, `T1071.001` web protocols, `T1071.004` DNS, `T1105` ingress tool transfer, `T1041` exfiltration over C2 channel, `T1562` impair defenses, `T1543.003` Windows service, `T1547.001` Run Keys/Startup Folder.
- SANS FOR508/GCFA public themes: endpoint evidence, Windows logs, memory forensics, timeline reconstruction, persistence, lateral movement, execution proof, root cause, and false-positive discipline.
- SANS FOR572/GNFA public themes: PCAP, DNS, proxy, NetFlow, HTTP/SMB, file extraction from network traffic, network timelines, C2 and exfil scoping.
- SANS FOR610/GREM public themes: static triage, behavioral triage, scripts/documents, unpacking leads, capability extraction, IOCs, C2 behavior, anti-analysis indicators.
- NIST SP 800-61 incident handling: analysis and documented evidence support response decisions; tool output alone is not the incident conclusion.
- Plaso/log2timeline and Timesketch public docs: useful model for normalized multi-source timelines, source-aware event provenance, targeted filtering, analyst annotations, and separating timeline context from findings.
- Volatility 3 public docs: useful model for memory plugin output provenance, process-view comparison, malware-in-memory triage, and the limits of memory-only conclusions.

Tool and community anchors:

- SigmaHQ/sigma: structured, shareable log detection rules; threat-hunting and emerging-threat rules are leads that require analyst validation and false-positive handling.
- Yamato-Security/hayabusa: fast Windows EVTX timeline and threat hunting, Sigma support, ATT&CK tactic mapping, log metrics, logon summaries, Base64 extraction, and JSON/JSONL/CSV outputs.
- Zeek: network security monitor for PCAP-derived structured logs and protocol-semantic analysis, especially `conn.log`, `dns.log`, `http.log`, `files.log`, `ssl.log`, `x509.log`, `smb_*`, `rdp.log`, `notice.log`, and `weird.log`.
- Velociraptor: VQL artifact-based endpoint collection; useful for targeted state capture and offline collection zips.
- Mandiant capa: executable capability detection with ATT&CK mappings; good for static and sandbox-report triage, with explicit limitations for packed/obfuscated samples.
- Neo23x0 Loki and YARA practice: filename/hash/C2/YARA IOC scanning is useful triage, but findings need corroboration and false-positive review.
- The DFIR Report public cases: useful report shape for timeline, ATT&CK-mapped case narrative, evidence-by-phase, IOCs, detections, and cross-artifact reasoning.
- Red Canary Threat Detection Report: useful detection-engineering model: map analytics to ATT&CK, list data sources, test visibility with Atomic Red Team-style emulations, and filter benign/testing/PUP-like noise from threat metrics.
- Elastic Security Labs: useful engineering themes: root-cause workflows, higher-order multi-signal correlation, rootkit behavioral detection beyond static matches, beaconing/DGA/network anomaly analytics, and repeatable telemetry-to-verdict workflows.
- Reddit community signals from r/DFIR, r/computerforensics, and r/blueteamsec: practitioners discuss evidence preservation, verification, AI-assisted forensics caution, network forensics, memory forensics, MCP-enabled forensic tooling, deterministic IOC extraction, and repeatable triage. Treat Reddit as prioritization signal only, not as authoritative evidence.

Timeline, reporting, and visual-evidence anchors:

- Timeline charts and event tables should be generated from parsed tool outputs, not from screenshots or hand-entered analyst prose.
- Visual evidence panels should make a cited finding easier to understand: show the relevant row/snippet/chart, cite the `tool_call_id`, explain why the pattern is suspicious, and link to a source citation.
- Evidence images are supporting exhibits only. They must never replace parsed tool output, create a finding by themselves, or upgrade confidence without cross-artifact corroboration.

Medium/blog note:

- MITRE links its ATT&CK blog on Medium and several ATT&CK references point to Medium-hosted threat research. If Medium pages are blocked, do not invent details. Use accessible MITRE ATT&CK pages and accessible original vendor/blog sources as the authoritative basis.

Suggested source citation IDs for implementation and reports:

- `CITE-MITRE-ATTACK-DATASOURCES`: MITRE ATT&CK Data Sources, `https://attack.mitre.org/datasources/`.
- `CITE-MITRE-T1003-001`: MITRE ATT&CK T1003.001 LSASS Memory, `https://attack.mitre.org/techniques/T1003/001/`.
- `CITE-MITRE-T1014`: MITRE ATT&CK T1014 Rootkit, `https://attack.mitre.org/techniques/T1014/`.
- `CITE-NIST-800-61R2`: NIST SP 800-61 Rev. 2, `https://csrc.nist.gov/pubs/sp/800/61/r2/final`.
- `CITE-PLASO`: Plaso/log2timeline documentation, `https://plaso.readthedocs.io/`.
- `CITE-TIMESKETCH`: Timesketch documentation, `https://timesketch.org/`.
- `CITE-VOLATILITY3`: Volatility 3 documentation, `https://volatility3.readthedocs.io/`.
- `CITE-ZEEK-LOGS`: Zeek log documentation, `https://docs.zeek.org/en/current/logs/index.html`.
- `CITE-VELOCIRAPTOR-ARTIFACTS`: Velociraptor artifact documentation, `https://docs.velociraptor.app/docs/artifacts/`.
- `CITE-SIGMAHQ`: SigmaHQ rules repository, `https://github.com/SigmaHQ/sigma`.
- `CITE-HAYABUSA`: Hayabusa repository, `https://github.com/Yamato-Security/hayabusa`.
- `CITE-CAPA`: capa repository, `https://github.com/mandiant/capa`.

## Copy/Paste Prompt

You are working in the Find Evil! repo as a pragmatic senior DFIR automation engineer.

Repo:

```text
C:\Users\newbi\Desktop\PUG Projects\SANS-Hackathon
```

Goal:

Improve Find Evil! automation so it more closely matches a real SANS-style practitioner workflow across endpoint DFIR, network forensics, and malware triage while preserving the repo's strict evidence, confidence, and MCP constraints. The result must be implementation-ready, test-backed, and honest about what is automated versus what still requires analyst judgment.

Hard constraints:

- Read and obey `CLAUDE.md` before editing.
- Preserve Amendment A2: Claude Code is the primary investigation interface.
- Preserve Amendment A5: do not reintroduce OpenTimestamps, `ots_stamp`, `ots_verify`, or Bitcoin timestamp claims.
- Preserve typed MCP surfaces; do not add `execute_shell`, shell passthrough, command passthrough, or generic script-runner tools.
- Evidence remains read-only.
- AGPL/GPL tools remain subprocess-only and are never linked.
- Every Finding must cite `tool_call_id`.
- Execution claims require at least two artifact classes.
- Confidence labels are only `CONFIRMED`, `INFERRED`, and `HYPOTHESIS`.
- Do not assert attribution.
- Treat Sigma, Hayabusa, YARA, capa, and anomaly hits as triage leads until corroborated.
- Treat `covered_no_finding` as limited coverage only; never say clean, cleared, disproven, or absence of evidence.
- Do not claim the product automates GCFA, GNFA, or GREM certification-level judgment.
- Do not stage generated evidence, memory images, EVTX, PCAP, output directories, `tmp`, `target`, `node_modules`, VM images, or private notes.

Start by inspecting:

```text
git status --short --branch
git diff
CLAUDE.md
README.md
QUICKSTART.md
agent-config/SOUL.md
agent-config/PLAYBOOK.md
agent-config/TOOLS.md
agent-config/MEMORY.md
docs/false-positives.md
docs/verdict-semantics.md
docs/runbooks/practical-sans-dfir-completion-prompt.md
scripts/find_evil_auto.py
scripts/render_report.py
scripts/verdict-policy-smoke.py
scripts/rust-mcp-smoke.py
services/mcp/src/tools/
services/mcp/README.md
services/agent_mcp/tests/test_stdio_smoke.py
```

Research translation:

- MITRE ATT&CK should become an explicit coverage contract, not just labels on findings.
- GCFA-style endpoint automation is the strongest current lane: memory, EVTX, registry, persistence, execution, lateral movement, and timelines.
- GNFA-style network automation is partial until PCAP, Zeek logs, proxy logs, DNS logs, or NetFlow are supplied.
- GREM-style malware automation is triage only: YARA, malfind, static metadata, strings/IOC extraction, capa-style capabilities if available, and anti-analysis/packing warnings.
- NIST incident-response framing means the report should separate evidence, analysis, next response actions, and unresolved gaps.
- Reddit/community signals emphasize repeatable evidence preservation, deterministic outputs, network/memory coverage, and AI caution. Encode that as schemas, tests, and overclaim-prevention text.
- Timeline reconstruction should normalize event rows from each artifact class while preserving source timestamp names, source tool calls, hashes, and parser limitations.
- Visual PDF reporting should show charts, snippets, and evidence panels that explain why an observable matters, but every panel must trace back to parsed output and source citations.

Implement one focused vertical slice named `attck_practitioner_coverage`, with supporting timeline and report-evidence data only where it improves the same verdict/report path.

Required `verdict.json` output:

```json
{
  "attck_practitioner_coverage": {
    "version": 1,
    "research_basis": [
      "MITRE ATT&CK data sources and techniques",
      "SANS FOR508/FOR572/FOR610 public course themes",
      "Zeek, Velociraptor, Sigma/Hayabusa, YARA, capa public docs",
      "DFIR Report, Red Canary, Elastic Security Labs practitioner reporting patterns",
      "Reddit DFIR/computerforensics/blueteamsec prioritization signals"
    ],
    "lanes": {
      "GCFA_endpoint": {
        "status": "automated|partial|not_covered|blocked",
        "artifact_classes_seen": [],
        "tools_run": [],
        "findings_linked": [],
        "attck_techniques_observed": [],
        "attck_data_sources_seen": [],
        "coverage_gaps": [],
        "next_actions": []
      },
      "GNFA_network": {
        "status": "automated|partial|not_covered|blocked",
        "artifact_classes_seen": [],
        "tools_run": [],
        "findings_linked": [],
        "attck_techniques_observed": [],
        "attck_data_sources_seen": [],
        "coverage_gaps": [],
        "next_actions": []
      },
      "GREM_malware": {
        "status": "automated|partial|not_covered|blocked",
        "artifact_classes_seen": [],
        "tools_run": [],
        "findings_linked": [],
        "attck_techniques_observed": [],
        "attck_data_sources_seen": [],
        "coverage_gaps": [],
        "next_actions": []
      }
    },
    "technique_coverage": [],
    "data_source_coverage": [],
    "overclaim_guardrails_applied": [],
    "source_citation_ids": []
  },
  "normalized_timeline": {
    "version": 1,
    "events": [
      {
        "event_id": "timeline-001",
        "timestamp_utc": "2026-05-04T00:00:00Z",
        "timestamp_source": "source field name, such as Event.System.TimeCreated",
        "artifact_class": "EVTX|memory|registry|prefetch|mft|usnjrnl|zeek|pcap|file",
        "tool_call_id": "tool-call-id",
        "source_record_ref": "output path plus row, record id, or offset",
        "summary": "short factual event text",
        "significance": "context|triage_lead|finding_support",
        "linked_finding_ids": [],
        "attck_techniques": [],
        "confidence": "CONFIRMED|INFERRED|HYPOTHESIS",
        "citation_ids": [],
        "limitations": []
      }
    ],
    "source_coverage": [],
    "limitations": []
  },
  "report_evidence_cards": [
    {
      "card_id": "evidence-card-001",
      "title": "short exhibit title",
      "linked_finding_ids": [],
      "tool_call_id": "tool-call-id",
      "source_record_refs": [],
      "visual_asset": "relative path under the run figures directory",
      "snippet": "short redacted row or value excerpt",
      "why_suspicious": "plain-language explanation tied to citations and case context",
      "confidence": "CONFIRMED|INFERRED|HYPOTHESIS",
      "citation_ids": [],
      "caveats": []
    }
  ],
  "source_bibliography": [
    {
      "citation_id": "CITE-MITRE-ATTACK-DATASOURCES",
      "title": "MITRE ATT&CK Data Sources",
      "url": "https://attack.mitre.org/datasources/",
      "accessed_utc": "2026-05-04T00:00:00Z",
      "supports": ["ATT&CK data-source coverage mapping"]
    }
  ],
  "malware_triage": {
    "version": 1,
    "scope": "triage_only",
    "summary": {},
    "observables": [],
    "aggregate_iocs": {},
    "analysis_constraints": [],
    "next_actions": []
  },
  "analysis_limitations": []
}
```

Coverage lane rules:

- `automated`: the lane had relevant evidence, ran relevant typed tools, and linked findings or covered-no-finding observations to concrete tool outputs.
- `partial`: the lane had some evidence or tools, but material artifact classes were missing or the evidence only supports triage.
- `not_covered`: the lane had no supplied evidence and no relevant tool output.
- `blocked`: evidence was supplied but could not be parsed or relevant typed tooling failed; include the exact blocker and next action.

ATT&CK mapping rules:

- Map each finding to both techniques and data sources when possible.
- Map each covered evidence class to data sources even when there is no finding.
- Use stable, explicit mappings first; do not fetch live ATT&CK data during normal investigation unless the repo already supports a pinned cache.
- Suggested data-source mappings: EVTX/Hayabusa to `DS0017`, `DS0028`, `DS0003`, `DS0019`, `DS0009`; memory process tools to `DS0009`, `DS0008`, `DS0011`; registry to `DS0024`; YARA/file scans to `DS0022`, `DS0011`, `DS0012`; Zeek/PCAP/proxy/DNS/NetFlow to `DS0029`, `DS0038`, `DS0018`; Velociraptor collections to the artifact-specific data source represented by each collected item.
- Suggested technique mappings: DKOM/process-view divergence to `T1014`; suspicious PowerShell/cmd to `T1059.001`/`T1059.003`; WMI remote execution to `T1047`; RDP movement to `T1021.001`; LSASS dump to `T1003.001`; service persistence to `T1543.003`; run keys/startup to `T1547.001`; scheduled tasks to `T1053`; web/DNS C2 to `T1071.001`/`T1071.004`; ingress transfer to `T1105`; C2-channel exfil to `T1041`; obfuscation or packed samples to `T1027`; masqueraded binaries to `T1036`; defense-tool/log tampering to `T1562`.

Timeline generation rules:

- Normalize timeline events from EVTX/Hayabusa, MFT, USN Journal, Prefetch, registry, memory process outputs, Zeek logs, Velociraptor collections, and malware triage outputs when those artifacts are present.
- Preserve UTC ISO-8601 timestamps with trailing `Z`, the original timestamp field name, source artifact class, parser/tool name, `tool_call_id`, source output path, and row/record/offset reference.
- Keep event existence separate from interpretation. A parsed row can be `CONFIRMED` as an observed event while its malicious meaning remains `HYPOTHESIS` or `INFERRED`.
- Deduplicate only when timestamp, host/user/process/path/network tuple, artifact class, and source record identity make the duplicate relationship explicit; otherwise keep both rows.
- Mark each event as `context`, `triage_lead`, or `finding_support`; do not let high event volume or visual clustering create a finding without supporting artifact facts.
- Include timeline limitations: missing time zone context, parser failures, truncated logs, memory-only scope, clock skew, collection window gaps, and artifacts not supplied.

Evidence card and visual PDF rules:

- Generate visual assets from parsed outputs: timeline histograms, per-lane coverage tables, ATT&CK data-source heatmaps, process-view comparison charts, logon/network summaries, IOC tables, and small record snippets.
- Each evidence card must include `card_id`, `linked_finding_ids`, `tool_call_id`, `source_record_refs`, `why_suspicious`, `confidence`, `citation_ids`, and caveats.
- `why_suspicious` must cite both case evidence and an external source when making a technique or data-source claim, such as `CITE-MITRE-T1014` for DKOM/rootkit process-view divergence or `CITE-MITRE-T1003-001` for LSASS credential access.
- Screenshots, charts, and snippets are exhibits. They must not create a finding without parsed tool output, and they must not upgrade confidence without cross-artifact support.
- Do not embed large raw logs or evidence files into the PDF. Use concise snippets, row references, hashes, and relative paths to generated figures under the run output directory.
- Reports must include a source bibliography resolving every `citation_id` used by `attck_practitioner_coverage`, `normalized_timeline`, or `report_evidence_cards`.

Malware triage rules:

- Build `malware_triage` from existing typed outputs first, especially `vol_malfind` and any future safe `yara_scan` output.
- Keep malware triage observables at `HYPOTHESIS` unless the normal judge/correlator path upgrades a separate Finding with cross-artifact support.
- Extract strings and IOCs deterministically from bounded previews only; do not promise full payload extraction unless dumped bytes exist.
- Do not identify who operated code, malware family, campaign, attribution, execution, or intent from malfind/YARA/string evidence alone.

Disk auto-mode rules:

- `case_open` on a disk image is chain-of-custody registration only. It is not a Finding.
- Disk-only auto mode without mounted/extracted artifacts must report an analysis limitation and `INDETERMINATE`, not `NO_EVIL`.
- Deep disk analysis should wait for mounted artifacts or explicit typed-tool inputs for MFT, USN Journal, Prefetch, Registry, EVTX, and YARA.

GNFA follow-up rule:

- The next safe network slice is a narrow typed Zeek-log parser for existing `conn.log`, `dns.log`, `http.log`, `files.log`, `ssl.log`, `notice.log`, and `weird.log`. Do not add PCAP conversion or arbitrary Zeek scripts until the typed log parser is covered by tests.

Minimal implementation sequence:

1. Add failing smoke tests in `scripts/verdict-policy-smoke.py` for `attck_practitioner_coverage`, `normalized_timeline`, `report_evidence_cards`, and `source_bibliography`.
2. Implement small helpers in `scripts/find_evil_auto.py` that build coverage, normalized timeline rows, visual evidence-card data, and citation bibliography from existing `tool_calls`, `findings`, `case_completeness`, `attack_coverage`, timeline events, and output artifact names.
3. Reuse existing tool outputs first: `evtx_query`, `hayabusa_scan`, `vol_pslist`, `vol_psscan`, `vol_psxview`, `vol_malfind`, `yara_scan`, `registry_query`, `prefetch_parse`, `mft_timeline`, `usnjrnl_query`, `vel_collect`.
4. Generate report figures from parsed output in `scripts/render_report.py`: timeline histogram, practitioner coverage table, ATT&CK data-source view, and finding-linked evidence cards when findings exist.
5. Do not add a new MCP tool unless existing typed outputs cannot represent the supplied evidence. If network automation is needed, prefer a narrow typed Zeek-log parser or PCAP-to-Zeek subprocess wrapper with fixed arguments and JSON output.
6. Add report rendering in `scripts/render_report.py` under concise `Practitioner Coverage`, `Timeline`, `Visual Evidence`, and `Sources` sections.
7. Update `agent-config/PLAYBOOK.md` and `agent-config/MEMORY.md` with caveats: GCFA strongest, GNFA evidence-dependent, GREM triage only, ATT&CK mapping is behavior classification not attribution, and visual exhibits do not replace tool output.
8. Update `docs/verdict-semantics.md` if the new verdict fields need a documented contract.

If adding a narrow network slice:

- Prefer support for existing Zeek logs before PCAP conversion.
- Parse only known TSV/JSON logs and summarize counts, top talkers, DNS queries, HTTP hosts/URIs, file transfers, TLS SNI/certs, SMB/RDP indicators, notices, weird events, and large outbound flows.
- If wrapping Zeek for PCAP, expose a typed MCP tool with fixed command construction, fixed output directory under the run workspace, input path allow-listing, timeouts, and SHA-256 of outputs.
- Do not call arbitrary tcpdump, tshark, zeek scripts, or shell strings supplied by the model/user.
- Findings from network logs must cite the parser/wrapper `tool_call_id` and remain `HYPOTHESIS` or `INFERRED` unless corroborated by endpoint artifacts or multiple independent network artifacts.

If adding a narrow malware slice:

- Start with file metadata, hashes, size, type, strings/IOC extraction, YARA results, malfind output, suspicious memory protection, and capa-style capabilities only if the tool is already available or can be safely subprocess-wrapped.
- Flag packer/obfuscation/anti-analysis indicators as analysis constraints, not malware-family proof.
- Extract IOCs deterministically into a stable JSON shape: hashes, paths, domains, URLs, IPs, emails, registry keys, mutex-like strings, user agents, and ATT&CK-relevant capability labels.
- Never claim malware family, actor, campaign, or attribution unless the evidence includes authoritative labels and the report still frames them as external labels.

Tests that must prevent overclaiming:

- EVTX-only run must not claim GNFA or GREM automation.
- Memory-only DKOM run must not claim cross-artifact proof or execution proof.
- YARA-only or malfind-only hit must remain a triage lead unless corroborated.
- Zeek/PCAP-only C2-like traffic must not become confirmed endpoint compromise.
- `NO_EVIL` with limited evidence must still list blind spots and next actions.
- `covered_no_finding` must never render as clean/cleared/disproven/absence.
- ATT&CK techniques must not appear without either a finding link or covered-no-finding coverage note.
- Any lane with `blocked` status must include a concrete blocker and next action.
- Every timeline event must include timestamp provenance, `artifact_class`, `tool_call_id`, and `source_record_ref`; missing provenance fails the smoke.
- Every evidence card must link to at least one finding or explicit covered-no-finding coverage note, cite a `tool_call_id`, and resolve all `citation_ids` in `source_bibliography`.
- Visual assets must not promote a finding confidence label or create a technique mapping without the underlying parsed tool output.
- Any `why_suspicious` paragraph that names a technique or data source must include at least one external citation ID and one case evidence reference.

Expected report behavior:

- Add `Practitioner Coverage` with one row per lane.
- Add `Timeline` with a source-aware event summary, not just a raw row dump.
- Add `Visual Evidence` cards with charts/snippets/images for findings and important coverage observations.
- Add `Sources` with bibliography entries for every source citation ID used in the verdict or report.
- Explain that GCFA/GNFA/GREM are practitioner skill domains and certifications, not capabilities the product fully automates.
- Show evidence supplied, tools run, ATT&CK data sources seen, techniques implicated, linked findings, blind spots, and next analyst actions.
- For each evidence card, explain why the observable is suspicious or relevant, what artifact proves it exists, what external source supports the interpretation, and what caveats remain.
- Keep the report concise and useful to a SANS judge: what ran, what was found, what is missing, what to do next.

Acceptance criteria:

```text
python scripts/verdict-policy-smoke.py
python scripts/rust-mcp-smoke.py --real-evidence
uv run --directory services/agent_mcp python -m pytest -q
ruff check .
ruff format --check .
git diff --check
```

Real evidence expectations:

- Real EVTX run still produces `NO_EVIL`, zero findings, timeline output, clear blind spots, and `attck_practitioner_coverage` with GCFA endpoint coverage only.
- Real EVTX report includes a timeline chart and coverage visuals, but no finding evidence card unless a finding exists.
- Real memory run still produces `INDETERMINATE` when process-view divergence exists, writes `psscan.json` and `psxview.json`, keeps memory-only findings at `HYPOTHESIS`, and reports no cross-artifact proof.
- Real memory report includes a process-view comparison visual tied to `vol_psscan`/`vol_psxview` tool output and `CITE-MITRE-T1014` when discussing DKOM/rootkit technique relevance.
- Reports include `Practitioner Coverage`, `Timeline`, `Visual Evidence`, and `Sources`.
- No generated evidence artifacts are staged.

Completion response:

- Summarize files changed.
- Summarize validation commands run and results.
- Mention any unavailable research source or tool explicitly.
- State that the implementation improves triage/orchestration coverage and does not automate or replace GCFA/GNFA/GREM analyst judgment.
