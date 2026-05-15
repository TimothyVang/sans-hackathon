# Protocol SIFT Integration Reference

> **Status: RESEARCH (external reference, NOT authoritative).** Where this doc disagrees with the project's own specs/plans, the specs win — see CLAUDE.md "External 'Protocol SIFT' reference" for the three known reconciled contradictions. Kept for background reading only.

**Status:** Reference material — NOT authoritative for the Find Evil! submission.
**Source:** Protocol SIFT's recommended Claude Code integration pattern (external project).
**Use:** Read for context on how upstream Protocol SIFT configures Claude Code, not as instructions for our submission. Where this material conflicts with our specs/plans, our specs/plans win.

---

To provide Claude Code with the full context of **Protocol SIFT**, you should create several specific files in your project root or the `~/.claude/` directory. Claude Code is designed to automatically ingest these files at the start of every session to establish its role, rules, and tool knowledge.

The following sections contain the essential text you need to feed into Claude Code.

### 1. Authoritative Project Memory (`CLAUDE.md`)
This file is the "brain" of the integration. It defines the AI's role and operational boundaries.

```markdown
# Protocol SIFT: Authoritative Project Memory

## WHY (Purpose)
Protocol SIFT is a framework for orchestrating the 400+ forensic tools in the SANS SIFT Workstation ecosystem. It shifts the analyst from manual execution to high-level orchestration to match the speed of modern AI-driven adversarial attacks.

## WHAT (Environment)
- **Role**: Principal DFIR Orchestrator.
- **Environment**: SANS SIFT Workstation (Ubuntu 22.04 LTS).
- **Evidence Mode**: Strict read-only handling to maintain the chain of custody.

## HOW (Operational Rules)
- **Autonomous Operation**: Run workflows start-to-finish without check-ins or confirmation prompts unless a destructive action is detected.
- **Hierarchical Context**: Use progressive disclosure. Read `SKILL.md` files in the `skills/` directory only when specific tools are required.
- **Standard Formatting**: Timestamps must always be in UTC.
- **Chain of Custody**: Document all actions in `./analysis/forensic_audit.log` via automated hooks.

## Routing Table (Core Skills)
- **Timeline Analysis**: Use Plaso (`log2timeline.py`, `psort.py`).
- **Memory Forensics**: Use Volatility 3.
- **Filesystem**: Use The Sleuth Kit (TSK) tools like `fls` and `icat`.
- **Windows Artifacts**: Use Eric Zimmerman's (EZ) Tools natively via .NET.
- **Threat Hunting**: Deploy YARA rules across memory and disk.
```

---

### 2. Global Permissions and Auditing (`settings.json`)
This file configures the underlying software engine to allow forensic tools to run without constant "Allow?" prompts.

```json
{
  "permissions": {
    "allowedTools": [
      "Read",
      "Write(./analysis/*)",
      "Write(./reports/*)",
      "Bash(log2timeline.py *)",
      "Bash(psort.py *)",
      "Bash(volatility *)",
      "Bash(fls *)",
      "Bash(icat *)",
      "Bash(yara *)",
      "Bash(exiftool *)",
      "Bash(md5sum *)",
      "Bash(grep *)"
    ],
    "deny": [
      "rm -rf",
      "dd",
      "wget",
      "curl",
      "WebFetch"
    ],
    "defaultMode": "acceptEdits"
  },
  "hooks": {
    "Stop": [
      {
        "type": "command",
        "command": "echo \"$(date -u): $CONVERSATION_SUMMARY\" >> ./analysis/forensic_audit.log"
      }
    ]
  }
}
```

---

### 3. Progressive Disclosure Architecture
To manage the complexity of SIFT, you must use **Progressive Disclosure**. Instead of one giant file, place tool-specific instructions in a `skills/` folder.

**Skill Template (`~/.claude/skills/volatility/SKILL.md`):**
```markdown
---
name: memory-forensics
description: Use for analyzing RAM captures via Volatility 3. Triggers on "memory", "dump", or "process list".
allowed-tools: Bash, Read
---
# Volatility 3 Memory Forensics
1. Always begin by detecting the OS profile using `imageinfo`.
2. Identify anomalies by comparing `pslist` and `psscan` (hidden processes).
3. Check for code injection using the `malfind` plugin.
4. Extract suspicious processes using `procdump` to the `./exports/memdump/` directory.
```

---

### 4. Self-Learning Loop (Ralph Wiggum)
For long-running refactors or complex investigations, Protocol SIFT utilizes a **Self-Learning Loop**. This is a **Stop hook** that prevents Claude from exiting if a task is incomplete or if errors persist.

**Mechanism:**
- **Trigger**: The `/ralph-loop` initiates the session.
- **Interceptor**: A Stop hook blocks the exit and re-injects the original prompt along with the terminal error output.
- **Verification**: The loop only terminates when a predefined "completion promise" (e.g., `<promise>COMPLETE</promise>`) is output by the model.

### 5. Installation and Setup Text
**Binary Installation command:**
`curl -fsSL https://claude.ai/install.sh | bash`

**Authentication**:
Run `claude` and complete the OAuth flow via the browser to link your **Anthropic Pro/Max** subscription or API key.

**Initialization**:
Run `/init` in a new case folder to let Claude analyze the evidence structure and create a case-specific memory file.

---

## How this reference relates to our submission

- The **allowedTools/deny** pattern in §2 is useful conceptually, but our submission uses **architectural** guardrails (typed Rust MCP server with no `execute_shell`) rather than Claude Code permission lists. Denying `curl`/`wget`/`WebFetch` at the Claude Code level would break our competitor-watch script and fixture fetch scripts.
- The **"Autonomous Operation"** framing in §1 conflicts with Rob Lee's judging preference for "orchestrator, not autonomous responder" (see `project_judging_signals.md`). Our UI default is human-in-the-loop via AI SDK 6 `needsApproval`; `--unattended` mode exists but is secondary.
- The **Ralph Wiggum self-learning loop** in §4 is Protocol SIFT's approach to iterating until success. Our analogue is the build swarm's critic subagent + dry-run gate + Postgres checkpoint — structurally similar but embedded in CI rather than a Stop hook.
- The **progressive-disclosure skill pattern** in §3 is interesting for documentation organization. Our equivalent is `agent-config/*.md` (SOUL/AGENTS/TOOLS/MEMORY/HEARTBEAT/JUDGING) loaded by the runtime agent, not Claude Code.
- The **installation URL** `curl -fsSL https://claude.ai/install.sh | bash` is the Claude Code install, not our Product install. Our one-liner pattern mirrors Protocol SIFT's `curl -fsSL .../install.sh | bash` but points to our own repo.

## Concrete adaptation in this repo (mapping table)

The four Protocol SIFT components above were converted into the
following concrete files in this tree. This is the operational
artifact set — the prose above is the rationale for each substitution.

| Protocol SIFT §  | Upstream form                                  | Adapted form in this repo                          | Why it differs                                                                                              |
|------------------|------------------------------------------------|----------------------------------------------------|--------------------------------------------------------------------------------------------------------------|
| §1 CLAUDE.md     | Generic SIFT-Workstation orchestrator brief    | `CLAUDE.md` (root) — A2-aware, spec-stack-aware    | Our CLAUDE.md must encode Amendments A1/A2, vocabulary rules, spec/code divergences, and the agent prompt    |
| §2 settings.json | Allows specific DFIR binaries, denies curl/wget | `.claude/settings.json` — allows our build/MCP surface, no DFIR binaries in Bash, no curl/wget deny | DFIR tools are reached through the typed Rust MCP server (architectural guard); fetch scripts need curl/wget |
| §3 Skills dir    | `~/.claude/skills/<tool>/SKILL.md` per tool    | `agent-config/{SOUL,AGENTS,PLAYBOOK,TOOLS,MEMORY,HEARTBEAT,JUDGING}.md` | Our DFIR persona is loaded by the agent itself at investigation start, not as Claude Code skills             |
| §4 /ralph-loop   | Stop-hook self-learning loop                   | `scripts/autonomous-loop.sh` (24h `claude --print` driver) + `services/swarm/session_guard.py` (rate-limit halt) | Subprocess loop is simpler to reason about than a Stop hook and matches the build-swarm worker pattern        |
| §5 Install + auth | `curl -fsSL https://claude.ai/install.sh \| bash` + `claude` OAuth | `scripts/find-evil` (local) + `scripts/find-evil-sift` (SIFT-VM SSH) + Amendment A1 three-mode credential detection | We launch *into* an investigation; Protocol SIFT launches a generic Claude Code session                       |

If you change any of the adapted files, update the corresponding
upstream-section reference here so the next session can see the
mapping intact. If a new Protocol SIFT version ships a new section,
add a row with "Adapted form in this repo: TBD" until a deliberate
adoption decision is made — silent adoption breaks the architectural
guard story.
