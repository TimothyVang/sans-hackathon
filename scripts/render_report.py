#!/usr/bin/env python3
"""Render an investigation report from a finished case dir.

Called by find_evil_auto.py at the end of an investigation. Generates
figures (matplotlib) + Markdown (templated) + HTML + PDF (Chrome
headless) inside the case's local directory.

Self-contained: can also be run standalone against any case dir that
has the required artifacts:

    python scripts/render_report.py /path/to/case-dir/
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

PANDOC = r"C:\Program Files\Pandoc\pandoc.exe"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "savefig.dpi": 140,
        "savefig.bbox": "tight",
        "figure.facecolor": "white",
    }
)


# ---------------------------------------------------------------------------
# Figure generators (produce PNGs in <case_dir>/figures/)
# ---------------------------------------------------------------------------


def fig_audit_chain(
    audit: list[dict[str, Any]], manifest: dict[str, Any], out: Path
) -> None:
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.axis("off")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)

    def box(x, y, w, h, txt, color="#e3f2fd", border="#1565c0", fs=9):
        p = FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.05",
            facecolor=color,
            edgecolor=border,
            linewidth=1.2,
        )
        ax.add_patch(p)
        ax.text(
            x + w / 2,
            y + h / 2,
            txt,
            ha="center",
            va="center",
            fontsize=fs,
            family="monospace",
        )

    def arrow(x1, y1, x2, y2):
        ax.add_patch(
            FancyArrowPatch(
                (x1, y1),
                (x2, y2),
                arrowstyle="-|>",
                mutation_scale=12,
                color="#1565c0",
                linewidth=1.2,
            )
        )

    ax.text(
        5,
        5.6,
        "Cryptographic chain of custody — manifest_finalize output",
        ha="center",
        fontsize=12,
        fontweight="bold",
    )

    ax.text(
        0.2,
        5.0,
        "audit.jsonl (hash-chained)",
        fontsize=9,
        fontweight="bold",
        color="#6a1b9a",
    )
    for i, rec in enumerate(audit[:5]):
        ph = rec.get("prev_hash", "") or "<genesis>"
        box(
            0.2,
            4.4 - i * 0.55,
            3.6,
            0.45,
            f"seq={rec['seq']} kind={rec['kind'][:14]}\nprev_hash={ph[:14]}…",
            color="#f3e5f5",
            border="#6a1b9a",
            fs=7,
        )

    box(
        0.2,
        1.2,
        3.6,
        0.5,
        f"audit_log_final_hash:\n{manifest['audit_log_final_hash'][:32]}…",
        color="#fff3e0",
        border="#ef6c00",
    )

    ax.text(
        5.5,
        5.0,
        "Merkle leaves (per tool_call_output)",
        fontsize=9,
        fontweight="bold",
        color="#1565c0",
    )
    for i in range(min(manifest["leaf_count"], 4)):
        box(
            5.5,
            4.4 - i * 0.55,
            3.6,
            0.45,
            f"leaf {i}: tool_call output_hash digest",
            color="#e3f2fd",
            border="#1565c0",
            fs=8,
        )

    box(
        5.5,
        1.2,
        3.6,
        0.5,
        f"merkle_root_hex:\n{manifest['merkle_root_hex'][:32]}…",
        color="#fffde7",
        border="#f9a825",
    )

    sig_sha = manifest["signature"]["payload_sha256"]
    box(
        2,
        0.2,
        6,
        0.7,
        f"run.manifest.json (signed via sigstore StubSigner)\n"
        f"signature_payload_sha256: {sig_sha[:32]}…",
        color="#e8f5e9",
        border="#2e7d32",
        fs=8,
    )

    arrow(2.0, 1.2, 4.5, 0.9)
    arrow(8.0, 1.2, 5.5, 0.9)

    fig.savefig(out)
    plt.close(fig)


def fig_psscan_timeline(psscan: list[dict[str, Any]], out: Path) -> None:
    """Process creation timeline from psscan output."""
    common = {
        n.lower()
        for n in {
            "System",
            "smss.exe",
            "csrss.exe",
            "winlogon.exe",
            "lsass.exe",
            "services.exe",
            "svchost.exe",
            "explorer.exe",
            "vmtoolsd.exe",
            "WmiPrvSE.exe",
            "spoolsv.exe",
            "lsm.exe",
            "wininit.exe",
            "dllhost.exe",
            "conhost.exe",
            "wmiprvse.exe",
            "taskhost.exe",
            "taskhostw.exe",
            "RuntimeBroker.exe",
        }
    }
    events = []
    for p in psscan:
        ts = p.get("CreateTime")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            continue
        events.append(
            {
                "dt": dt,
                "pid": p["PID"],
                "ppid": p["PPID"],
                "name": p["ImageFileName"],
                "threads": p.get("Threads", 0),
            }
        )
    events.sort(key=lambda e: e["dt"])
    if not events:
        return
    fig, ax = plt.subplots(figsize=(12, 6))
    times = [e["dt"] for e in events]
    pids = [e["pid"] for e in events]
    sizes = [max(20, min(200, e["threads"] * 3)) for e in events]
    colors = [
        "#c62828" if e["name"].lower() not in common else "#1565c0" for e in events
    ]
    ax.scatter(
        times, pids, c=colors, s=sizes, alpha=0.7, edgecolors="black", linewidths=0.5
    )
    ax.set_xlabel("Process creation time (UTC)")
    ax.set_ylabel("PID")
    ax.set_title(
        f"Process creation timeline ({len(events)} processes via psscan)\n"
        "Red = uncommon image name; Blue = standard Windows process"
    )
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
    ax.grid(True, alpha=0.3)
    ax.legend(
        handles=[
            mpatches.Patch(color="#1565c0", label="Standard Windows process"),
            mpatches.Patch(color="#c62828", label="Uncommon image name"),
        ],
        loc="upper left",
        fontsize=8,
    )
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def fig_findings_table(findings: list[dict[str, Any]], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 0.5 + 0.4 * max(1, len(findings))))
    ax.axis("off")
    if not findings:
        ax.text(
            0.5,
            0.5,
            "No merged findings",
            ha="center",
            va="center",
            fontsize=11,
            color="#777",
        )
        fig.savefig(out)
        plt.close(fig)
        return
    table_data = [["Conf.", "Pool", "MITRE", "Description"]]
    for f in findings[:20]:
        table_data.append(
            [
                f.get("confidence", "?")[:9],
                f.get("pool_origin", "?")[:1],
                (f.get("mitre_technique") or "—")[:10],
                (f.get("description", ""))[:90],
            ]
        )
    table = ax.table(
        cellText=table_data,
        loc="center",
        cellLoc="left",
        colWidths=[0.10, 0.05, 0.10, 0.75],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.4)
    for i in range(len(table_data[0])):
        cell = table[(0, i)]
        cell.set_facecolor("#1565c0")
        cell.set_text_props(color="white", fontweight="bold")
    fig.savefig(out)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Markdown report template
# ---------------------------------------------------------------------------


def md_cell(value: Any) -> str:
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)
    return str(value or "").replace("\n", " ").replace("|", "\\|")


def build_false_positive_caveats(
    merged: list[dict[str, Any]],
    completeness: dict[str, Any] | None,
    attack_coverage: dict[str, Any] | None,
) -> list[str]:
    caveats = [
        "Sigma/Hayabusa rule hits, if present, are triage leads that require raw EVTX review, tuning, and corroboration before compromise claims.",
    ]
    targets = attack_coverage.get("targets", []) if attack_coverage else []
    if any(row.get("status") == "covered_no_finding" for row in targets):
        caveats.append(
            "ATT&CK `covered_no_finding` means scoped tools ran without qualifying evidence; it does not mean clean, cleared, disproven, or absence of the technique."
        )
    checks = {
        c.get("artifact_class"): c for c in (completeness or {}).get("checks", [])
    }
    if not checks.get("network", {}).get("touched"):
        caveats.append(
            "Network telemetry was not touched in this run, so exfiltration and C2 are neither proven nor disproven."
        )
    if not checks.get("disk/filesystem", {}).get("touched"):
        caveats.append(
            "Disk/filesystem artifacts were not deeply parsed in this run; memory-only or EVTX-only observations do not prove execution."
        )
    if any(f.get("confidence") == "HYPOTHESIS" for f in merged):
        caveats.append(
            "HYPOTHESIS findings are single-source or speculative leads and should not drive response actions without further artifact corroboration."
        )
    return caveats


def write_markdown(
    case_dir: Path,
    manifest: dict[str, Any],
    merged: list[dict[str, Any]],
    contras: int,
    kept: int,
    downgraded: int,
    evidence: str,
    verdict: str,
    has_psscan: bool,
    audit: list[dict[str, Any]] | None = None,
    completeness: dict[str, Any] | None = None,
    attack_coverage: dict[str, Any] | None = None,
    next_actions: list[dict[str, Any]] | None = None,
    timeline: list[dict[str, Any]] | None = None,
    timeline_csv_exists: bool = False,
    evtx_summary: dict[str, Any] | None = None,
) -> Path:
    md = case_dir / "REPORT.md"
    fa = manifest["audit_log_final_hash"]
    mr = manifest["merkle_root_hex"]
    sig = manifest["signature"]["payload_sha256"]
    cf = manifest["signature"]["cert_fingerprint"]

    selfscore_section = ""
    if audit:
        selfscores = sorted(
            (r for r in audit if r.get("kind") == "judge_selfscore"),
            key=lambda r: r.get("payload", {}).get("criterion", 99),
        )
        if selfscores:
            rows = ["| # | Criterion | Score |", "|---:|---|---|"]
            for r in selfscores:
                p = r.get("payload", {})
                rows.append(
                    f"| {p.get('criterion', '?')} | "
                    f"{p.get('question', '')} | "
                    f"`{p.get('answer', '')}` |"
                )
            selfscore_section = (
                "\n## Judge self-score (agent's own assessment)\n\n"
                "*Per `agent-config/JUDGING.md` §End-of-investigation, "
                "the agent emits one `kind=judge_selfscore` audit record "
                "per SANS Find Evil! 2026 rubric criterion BEFORE "
                "`manifest_finalize` — so the score below is itself part "
                "of the cryptographic attestation. The agent doesn't get "
                "to revise it after seeing the score it actually got.*\n\n"
                + "\n".join(rows)
                + "\n\n---\n"
            )

    findings_md_lines = []
    for i, f in enumerate(merged, 1):
        findings_md_lines.append(
            f"### Finding {i} — confidence: {f.get('confidence', '?')}, "
            f"pool: {f.get('pool_origin', '?')}, "
            f"MITRE: {f.get('mitre_technique') or 'n/a'}"
        )
        findings_md_lines.append("")
        findings_md_lines.append(f.get("description", "") + "\n")
        findings_md_lines.append(f"- `tool_call_id`: `{f.get('tool_call_id', 'n/a')}`")
        findings_md_lines.append(f"- artifact: `{f.get('artifact_path', 'n/a')}`")
        findings_md_lines.append("")
    findings_section = (
        "\n".join(findings_md_lines) if findings_md_lines else "*No merged findings.*"
    )

    psscan_fig_block = ""
    if has_psscan:
        psscan_fig_block = (
            "\n### Process creation timeline\n\n"
            "![Process creation timeline](figures/psscan_timeline.png)\n"
        )

    completeness_section = ""
    if completeness:
        rows = [
            "| Artifact Class | Available | Touched | Tools | Confidence Impact |",
            "|---|:---:|:---:|---|---|",
        ]
        for check in completeness.get("checks", []):
            rows.append(
                "| {artifact_class} | {available} | {touched} | `{tools}` | {impact} |".format(
                    artifact_class=check.get("artifact_class", "?"),
                    available="yes" if check.get("available") else "no",
                    touched="yes" if check.get("touched") else "no",
                    tools=", ".join(check.get("tools", [])) or "none",
                    impact=check.get("confidence_impact", ""),
                )
            )
        completeness_section = (
            "\n## Case Completeness\n\n"
            f"{completeness.get('summary', '')}\n\n" + "\n".join(rows) + "\n\n"
        )

    attack_section = ""
    if attack_coverage:
        rows = [
            "| Technique | Tactic | Status | Tools Observed | Gap / Analyst Value |",
            "|---|---|---|---|---|",
        ]
        status_label = {
            "finding": "finding",
            "covered_no_finding": "covered, no finding (limited)",
            "available_not_examined": "available, not examined",
            "blind_spot": "blind spot",
        }
        for row in attack_coverage.get("targets", []):
            technique = (
                f"{row.get('technique_id', '?')} "
                f"{row.get('technique_name', '')}".strip()
            )
            if row.get("finding_confidence"):
                status = (
                    f"{status_label.get(row.get('status'), row.get('status'))} "
                    f"({row.get('finding_confidence')})"
                )
            else:
                status = status_label.get(row.get("status"), row.get("status", "?"))
            tools = ", ".join(row.get("tools_observed") or []) or "none"
            gap = row.get("gap") or row.get("analyst_value", "")
            rows.append(
                f"| {md_cell(technique)} | {md_cell(row.get('tactic', ''))} | "
                f"{md_cell(status)} | `{md_cell(tools)}` | {md_cell(gap)} |"
            )
        attack_section = (
            "\n## ATT&CK Coverage\n\n"
            f"{attack_coverage.get('summary', '')}\n\n" + "\n".join(rows) + "\n\n"
        )

    evtx_section = ""
    if evtx_summary:
        top = (
            ", ".join(
                f"EID {row.get('event_id')} x{row.get('count')}"
                for row in evtx_summary.get("top_event_ids", [])[:5]
            )
            or "none"
        )
        channels = ", ".join(evtx_summary.get("channels", [])) or "none"
        evtx_section = (
            "\n## EVTX Summary\n\n"
            f"* Records seen: {evtx_summary.get('records_seen', 0)}\n"
            f"* Rows returned: {evtx_summary.get('row_count', 0)}\n"
            f"* Parse errors: {evtx_summary.get('parse_errors', 0)}\n"
            f"* Channels: {channels}\n"
            f"* Top Event IDs: {top}\n"
            f"* Verdict contribution: {evtx_summary.get('verdict_contribution', 'none')} — {evtx_summary.get('reason', '')}\n\n"
        )

    actions_section = ""
    if next_actions:
        rows = [
            "| Priority | Action | Why | Based On | Expected Evidence |",
            "|---|---|---|---|---|",
        ]
        for item in next_actions[:5]:
            rows.append(
                f"| {md_cell(item.get('priority', ''))} | "
                f"{md_cell(item.get('action', ''))} | "
                f"{md_cell(item.get('why', ''))} | "
                f"{md_cell(item.get('based_on', []))} | "
                f"{md_cell(item.get('expected_evidence', ''))} |"
            )
        actions_section = "\n## Next 5 Analyst Actions\n\n" + "\n".join(rows) + "\n\n"

    timeline_section = ""
    if timeline:
        timeline_exports = "`timeline.json`"
        if timeline_csv_exists:
            timeline_exports += " and analyst-friendly `timeline.csv`"
        rows = [
            "| UTC Time | Source | Artifact Class | Description | Tool Call |",
            "|---|---|---|---|---|",
        ]
        for event in timeline[:25]:
            rows.append(
                "| {ts} | `{source}` | {artifact_class} | {desc} | `{tcid}` |".format(
                    ts=event.get("ts", "?"),
                    source=event.get("source", "?"),
                    artifact_class=event.get("artifact_class", "?"),
                    desc=event.get("description", "")[:120],
                    tcid=event.get("tool_call_id", "?"),
                )
            )
        timeline_section = (
            "\n## Unified Timeline\n\n"
            f"Normalized timeline events: {len(timeline)}. "
            f"First 25 events shown below; full data is in {timeline_exports}.\n\n"
            + "\n".join(rows)
            + "\n\n"
        )

    caveats = build_false_positive_caveats(merged, completeness, attack_coverage)
    caveat_section = (
        "\n## False-positive caveats\n\n"
        + "\n".join(f"* {c}" for c in caveats)
        + "\n\n"
    )

    md.write_text(
        f"""# Find Evil! — Automated Investigation Report

**Case ID:** `{manifest['case_id']}`
**Run ID:** `{manifest['run_id']}`
**Started:** {manifest['started_at']}
**Finalized:** {manifest['finalized_at']}
**Evidence:** `{evidence}`
**Verdict:** **{verdict}**

> **Cryptographic attestation:**
> Merkle root `{mr}`
> Audit log final hash `{fa}`
> Sigstore signature SHA-256 `{sig}`
> Cert fingerprint `{cf}`

---

## Summary

* **Total merged findings:** {len(merged)}
* **By confidence:**
  - CONFIRMED: {sum(1 for m in merged if m.get('confidence') == 'CONFIRMED')}
  - INFERRED:  {sum(1 for m in merged if m.get('confidence') == 'INFERRED')}
  - HYPOTHESIS: {sum(1 for m in merged if m.get('confidence') == 'HYPOTHESIS')}
* **Contradictions surfaced (Pool A vs Pool B):** {contras}
* **SOUL.md correlator:** {kept} kept, {downgraded} downgraded

---

## Findings overview

![Findings table](figures/findings_table.png)

{actions_section}

{completeness_section}

{attack_section}

{evtx_section}

{timeline_section}

{caveat_section}

## Findings detail

{findings_section}

---

## Cryptographic chain of custody

![Cryptographic chain of custody](figures/chain_of_custody.png)
{psscan_fig_block}
---
{selfscore_section}

## Verification

This investigation produced a `run.manifest.json` that any third party can
verify offline:

```bash
manifest_verify <run.manifest.json>
# → returns overall=True if audit chain + Merkle root + signature all valid
```

The verifier rebuilds:
1. The audit chain by walking `prev_hash` SHA-256 links (catches backdated edits).
2. The Merkle tree from the manifest's `leaves[]` array (catches selective redaction).
3. The sigstore signature against the canonical body (catches body tampering).

A tamper test against this manifest's `merkle_root_hex` (overwrite with `ff…ff`) was
not run automatically. To execute it:

```bash
python -c "import shutil;shutil.copyfile('run.manifest.json','run.manifest.tamper.json')"
python -c "import json,pathlib;p=pathlib.Path('run.manifest.tamper.json');d=json.loads(p.read_text());d['merkle_root_hex']='ff'*32;p.write_text(json.dumps(d,indent=2,sort_keys=True))"
manifest_verify run.manifest.tamper.json    # → overall=False, with diagnostic
```

---

*Produced by `find-evil-auto` (the Find Evil! automated investigation orchestrator).
The cryptographic attestation values shown are the actual outputs of this run; every
quantitative claim above is independently verifiable from the artifacts in this
directory (`audit.jsonl`, `run.manifest.json`, `verdict.json`).*
""",
        encoding="utf-8",
    )
    return md


# ---------------------------------------------------------------------------
# Pandoc + Chrome render
# ---------------------------------------------------------------------------


def render_html_pdf(md_path: Path) -> tuple[Path, Path | None]:
    case_dir = md_path.parent
    html = case_dir / "REPORT.html"
    pdf = case_dir / "REPORT.pdf"

    style_path = Path(__file__).resolve().parent / "_report_style.css"
    if not style_path.exists():
        style_path.write_text(_DEFAULT_CSS, encoding="utf-8")

    subprocess.run(
        [
            PANDOC,
            str(md_path),
            "--standalone",
            "--embed-resources",
            "--css",
            str(style_path),
            "-o",
            str(html),
        ],
        check=True,
        capture_output=True,
    )

    pdf_out: Path | None = None
    if Path(CHROME).exists():
        # Chrome can't overwrite a PDF that's open in a viewer (Windows
        # locks the file). Render to a sibling .new.pdf first; if the
        # final rename fails, the rendered output still survives and
        # the user gets a clear message naming both paths.
        pdf_tmp = pdf.with_suffix(".new.pdf")
        try:
            html_url = "file:///" + str(html).replace("\\", "/").replace("C:/", "C:/")
            subprocess.run(
                [
                    CHROME,
                    "--headless",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--print-to-pdf=" + str(pdf_tmp),
                    "--print-to-pdf-no-header",
                    "--virtual-time-budget=10000",
                    html_url,
                ],
                capture_output=True,
                timeout=120,
            )
            if pdf_tmp.exists() and pdf_tmp.stat().st_size > 1000:
                try:
                    pdf_tmp.replace(pdf)
                    pdf_out = pdf
                except OSError:
                    # Target locked (likely open in a viewer). Keep the
                    # rendered .new.pdf so the operator can see it.
                    print(
                        f"  WARN: could not overwrite {pdf} (likely open "
                        f"in a viewer); rendered output left at {pdf_tmp}"
                    )
                    pdf_out = pdf_tmp
        except Exception:
            pass
    return html, pdf_out


_DEFAULT_CSS = """
body { font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
       max-width: 980px; margin: 2em auto; padding: 0 2.5em; line-height: 1.65;
       color: #222; background: #fafafa; }
h1 { color: #1565c0; border-bottom: 3px solid #1565c0; padding-bottom: 0.4em; font-size: 2em; }
h2 { color: #1565c0; border-bottom: 1px solid #ccc; padding-bottom: 0.25em; margin-top: 2.5em; font-size: 1.4em; }
h3 { color: #6a1b9a; margin-top: 1.6em; font-size: 1.15em; }
img { max-width: 100%; display: block; margin: 2em auto; border: 1px solid #ddd;
      box-shadow: 0 4px 12px rgba(0,0,0,0.08); border-radius: 4px;
      background: white; padding: 8px; }
code { background: #eef2f5; padding: 0.1em 0.4em; border-radius: 3px;
       font-family: "Consolas", monospace; font-size: 0.92em; color: #c62828; }
pre { background: #2c3e50; color: #ecf0f1; padding: 1em 1.4em; border-radius: 4px; overflow-x: auto; }
pre code { background: none; padding: 0; color: inherit; }
blockquote { border-left: 4px solid #1565c0; padding: 0.7em 1.2em; margin: 1.2em 0;
             background: #e3f2fd; border-radius: 0 4px 4px 0; }
table { border-collapse: collapse; margin: 1.2em 0; width: 100%; }
th, td { padding: 0.55em 0.9em; border: 1px solid #ddd; text-align: left; }
th { background: #1565c0; color: white; font-weight: 600; }
tr:nth-child(even) td { background: #f5f7fa; }
strong { color: #1565c0; }
"""


# ---------------------------------------------------------------------------
# Public entrypoint (called from find_evil_auto.py)
# ---------------------------------------------------------------------------


def render_report(
    case_dir: Path,
    manifest: dict[str, Any],
    merged: list[dict[str, Any]],
    contras: int,
    kept: int,
    downgraded: int,
    evidence: str,
    verdict: str,
) -> Path:
    case_dir = Path(case_dir)
    fig_dir = case_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    audit = []
    audit_path = case_dir / "audit.jsonl"
    if audit_path.exists():
        for line in audit_path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    audit.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    fig_audit_chain(audit, manifest, fig_dir / "chain_of_custody.png")
    fig_findings_table(merged, fig_dir / "findings_table.png")

    has_psscan = False
    psscan_path = case_dir / "psscan.json"
    if psscan_path.exists():
        try:
            psscan = json.loads(psscan_path.read_text())
            if isinstance(psscan, list) and psscan:
                fig_psscan_timeline(psscan, fig_dir / "psscan_timeline.png")
                has_psscan = True
        except json.JSONDecodeError:
            pass

    verdict_obj = {}
    verdict_path = case_dir / "verdict.json"
    if verdict_path.exists():
        try:
            verdict_obj = json.loads(verdict_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            verdict_obj = {}

    timeline = []
    timeline_path = case_dir / "timeline.json"
    if timeline_path.exists():
        try:
            loaded_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
            if isinstance(loaded_timeline, list):
                timeline = loaded_timeline
        except json.JSONDecodeError:
            timeline = []
    timeline_csv_exists = (case_dir / "timeline.csv").exists()

    md = write_markdown(
        case_dir,
        manifest,
        merged,
        contras,
        kept,
        downgraded,
        evidence,
        verdict,
        has_psscan,
        audit=audit,
        completeness=verdict_obj.get("case_completeness", {}),
        attack_coverage=verdict_obj.get("attack_coverage", {}),
        next_actions=verdict_obj.get("next_actions", []),
        timeline=timeline,
        timeline_csv_exists=timeline_csv_exists,
        evtx_summary=verdict_obj.get("evtx_summary"),
    )
    html, pdf = render_html_pdf(md)
    return pdf if pdf else html


def main() -> int:
    p = argparse.ArgumentParser(description="Render report for a finished case dir")
    p.add_argument(
        "case_dir",
        help="Directory containing audit.jsonl + " "run.manifest.json + verdict.json",
    )
    args = p.parse_args()
    case_dir = Path(args.case_dir)
    manifest = json.loads((case_dir / "run.manifest.json").read_text())
    verdict_obj = json.loads((case_dir / "verdict.json").read_text())
    merged = verdict_obj.get("findings", [])
    summary = verdict_obj.get("findings_summary", {})
    out = render_report(
        case_dir,
        manifest,
        merged,
        summary.get("contradictions_surfaced", 0),
        summary.get("soul_md_kept", 0),
        summary.get("soul_md_downgraded", 0),
        verdict_obj.get("evidence_path", "?"),
        verdict_obj.get("verdict", "?"),
    )
    print(f"rendered: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
