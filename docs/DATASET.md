# Dataset Documentation

**Devpost Required Component #5** — what the agent was tested against, source of data, and what it found.

This document covers every fixture the Find Evil! submission was tested against. All fixtures are either public domain, permissively licensed, or pulled from SANS's own starter case data. None are bundled in the git tree; `scripts/fetch-fixtures.sh` pulls them at CI time.

---

## Primary golden: SANS starter case data

| Attribute | Value |
|---|---|
| Source | SANS Find Evil! official starter case data |
| URL | `https://sansorg.egnyte.com/fl/HhH7crTYT4JK` |
| License | Distributed as hackathon starter data by SANS Institute |
| Content | Sample disk images + memory captures (hackathon-specific) |
| Purpose | **Primary** L3 golden-run fixture — what judges are most likely to test submissions against |
| SHA-256 | *(recorded by `scripts/fetch-fixtures.sh` at first download; see `fixtures/sha256sums.txt`)* |
| Expected findings | *(enumerated in `goldens/sans-starter/expected-findings.json` after first manual walk-through)* |

**Rationale for primary status:** This dataset ships with the hackathon and is what Rob Lee and the judges are most familiar with. Optimizing for it aligns our accuracy metrics with the judging experience.

---

## Secondary: NIST CFReDS Hacking Case

| Attribute | Value |
|---|---|
| Source | NIST Computer Forensics Reference Data Sets |
| URL | `https://cfreds.nist.gov/all/NIST/HackingCase` |
| License | Public domain (17 USC 105 — U.S. government works are not copyrightable) |
| Content | EnCase E01 (~4.5 GB compressed / ~4.8 GB raw NTFS); Windows host evidence |
| Purpose | Canonical DFIR benchmark case; industry-standard ground truth |
| SHA-256 | *(recorded on first pull)* |
| Expected findings | **14 canonical findings** — enumerated in `goldens/nist-hacking-case/expected-findings.json` |
| Verdict | `CONFIRMED_EVIL` |

**Rationale:** NIST's authority makes this a standard reference. Multiple DFIR tools publish accuracy against it, so our DFIR-Metric score is directly comparable to any competitor.

### Lightweight extract — single Security.evtx for fast smoke

For developer-laptop iteration we don't always want the 4.5 GB E01. `scripts/fetch-nist-fixture.sh` pulls **one small Security.evtx** at `fixtures/single-evtx/Security.evtx`, used by `python scripts/rust-mcp-smoke.py --real-evidence`. Source URL is intentionally NOT hardcoded — set via env vars so operators can point at a vetted mirror without an upstream URL change breaking CI:

```sh
NIST_FIXTURE_URL=https://example.org/path/to/Security.evtx \
NIST_FIXTURE_SHA256=<64-hex-digits> \
bash scripts/fetch-nist-fixture.sh
```

Vetted candidate sources (any one is sufficient):
- An OTRF Security-Datasets sample with a single standalone `.evtx` payload (the `datasets/atomic/windows/credential_access` and `datasets/atomic/windows/defense_evasion` subtrees ship sub-MB EVTX files).
- An internal team mirror of CFReDS Hacking Case `Security.evtx` extracted via The Sleuth Kit's `fls`+`icat` from `SCHARDT.001`.
- A small synthetic EVTX produced by `wevtutil epl` on a clean Win10 host.

The fetch script is deliberately strict: SHA pin enforced when supplied, magic-byte sanity check (`ElfFile\0`) on every download, atomic rename, provenance recorded at `fixtures/single-evtx/PROVENANCE.txt`. The smoke harness skips silently when the fixture is absent so offline runs still pass.

---

## Secondary: OTRF Security-Datasets (formerly Mordor)

| Attribute | Value |
|---|---|
| Source | Open Threat Research Forge |
| URL | `https://github.com/OTRF/Security-Datasets` |
| License | MIT License |
| Content | EVTX / JSON / Zeek replay datasets for specific attack scenarios (APT3, APT29, Empire, Covenant, Cobalt Strike) |
| Purpose | Behavior-specific validation; exercises Hayabusa Sigma rules and event-correlation paths |
| SHA-256 | *(per-dataset, recorded on pull)* |
| Expected findings | Per-dataset; scenario-specific (e.g., APT3-Mordor expects lateral movement T1021.006) |
| Verdict | Varies per dataset |

**Rationale:** Each dataset isolates a named attack pattern, so Hayabusa rule coverage can be validated precisely. Used in L2 smoke tests (non-blocking advisory) and L3 matrix runs.

---

## Secondary: Volatility Foundation Memory Samples

| Attribute | Value |
|---|---|
| Source | Volatility Foundation |
| URL | `https://github.com/volatilityfoundation/volatility/wiki/Memory-Samples` |
| License | Creative Commons Attribution (CC-BY) — redistribute with attribution |
| Content | Known-good + known-malicious memory dumps (Cridex, Stuxnet, SpyEye samples, etc.) |
| Purpose | Volatility3 plugin validation; exercises `vol_pslist`, `vol_malfind`, cross-artifact memory→disk correlation |
| SHA-256 | *(per-sample)* |
| Expected findings | Per-sample (e.g., Cridex: injected PID list, malfind RWX regions) |
| Verdict | Varies per sample |

**Rationale:** Memory-specific ground truth. Windows profile auto-detection tested here before L3 runs.

---

## Synthetic benign baseline

| Attribute | Value |
|---|---|
| Source | Internal, synthetic (generated by the build process) |
| URL | *(not applicable — produced at CI time)* |
| License | MIT (our own generation script) |
| Content | Clean Windows 10 install, patched, no tradecraft, representative baseline activity only |
| Purpose | Negative control — the agent must NOT produce false-positive findings |
| SHA-256 | *(per-generation)* |
| Expected findings | **0** (verdict: `NO_EVIL`) |
| Verdict | `NO_EVIL` |

**Rationale:** A submission that only finds evil on evil data is useless. This fixture verifies that the agent distinguishes benign systems from compromised ones — addresses the "hallucination" criticism that Valhuntir explicitly warns about but does not measure.

---

## DFIR-Metric benchmark suite

| Attribute | Value |
|---|---|
| Source | DFIR-Metric research project |
| URL | `https://github.com/DFIR-Metric` |
| Paper | `https://arxiv.org/abs/2505.19973` |
| License | *(per repo — permissive, verified at Week 6)* |
| Content | 700 MCQs + 150 CTF tasks + 500 NIST cases, designed to evaluate LLMs on DFIR |
| Purpose | Standardized accuracy metric; external validation of agent quality |
| SHA-256 | *(per benchmark release)* |
| Expected findings | *(per case in the benchmark — documented by DFIR-Metric, not by us)* |
| Verdict | Scored per DFIR-Metric rubric |

**Rationale:** The only public DFIR-specific benchmark. Publishing our score here (via the M1 leaderboard) differentiates us from Valhuntir, which explicitly declines to publish any accuracy metric.

---

## DFRWS Rodeo and USB challenges

| Attribute | Value |
|---|---|
| Source | Digital Forensic Research Workshop, hosted on NIST CFReDS |
| URL | `https://cfreds.nist.gov/` |
| License | Public domain |
| Content | Small USB DD images (~500 MB each) with deliberate artifacts |
| Purpose | Fast smoke tests in L1/L2 (images small enough to cache in CI) |
| SHA-256 | *(per-image)* |
| Expected findings | Per-challenge (documented per-case) |
| Verdict | Varies |

**Rationale:** Small size + public domain = ideal for L1/L2 rapid iteration where full SIFT VM isn't needed.

---

## Fixture caching and integrity

All fixtures are fetched by `scripts/fetch-fixtures.sh` (Spec #3 Task 10). On first pull, each file's SHA-256 is computed and recorded in `fixtures/sha256sums.txt`. Subsequent runs verify the checksum; mismatches abort with clear error. This prevents a fixture swap from silently altering benchmark scores.

Storage policy:
- **Never committed to git.** `.gitignore` excludes `*.E01`, `*.ova`, `*.raw`, `*.mem`, `*.dd`, `*.aff`, `*.aff4`.
- **Not bundled in Devpost submission zip.** Fixture URLs documented here; judges fetch via `scripts/fetch-fixtures.sh`.
- **Cached in GHA via `actions/cache`** keyed on `fixtures/sha256sums.txt` hash.

---

## Findings corpus (what the agent found)

*(Populated incrementally as Week 5 acceptance criteria (AC-01 through AC-10) are verified against each fixture. Each subdirectory contains the full agent run manifest, audit.jsonl, and OTS receipt.)*

```
goldens/
├── sans-starter/
│   ├── expected-findings.json    (ground truth — populated from manual walkthrough)
│   ├── run-manifest.json         (cryptographically-signed)
│   ├── audit.jsonl               (hash-chained audit log)
│   └── run-manifest.ots          (OpenTimestamps Bitcoin receipt)
├── nist-hacking-case/
│   └── …same layout…
├── otrf-apt3-mordor/
│   └── …same layout…
├── volatility-cridex/
│   └── …same layout…
└── synthetic-benign/
    └── …same layout (expected empty findings)…
```

Each `run.manifest.json` is verifiable offline by any third party — under Amendment A2 the entry points are the `verify_manifest` library function (`from findevil_agent.crypto.manifest import verify_manifest`) or the `manifest_verify` MCP tool. The pre-A2 `find-evil verify <manifest>` CLI was dropped along with `findevil_agent/cli.py`. See `docs/cryptographic-attestation.md` "How a third party verifies offline" for the working recipe.

---

## Licensing summary

| Fixture | License | Redistribute? |
|---|---|---|
| SANS starter data | Hackathon starter | No (fetch from SANS) |
| NIST CFReDS | Public domain | Yes, by URL reference |
| OTRF Security-Datasets | MIT | Yes, by URL reference (attribution via fetch script) |
| Volatility samples | CC-BY | Yes, by URL reference (attribution via fetch script) |
| Synthetic benign | MIT (our script) | Yes |
| DFIR-Metric | Permissive (verified Week 6) | Yes, by URL reference |
| DFRWS Rodeo | Public domain | Yes |

None of these licenses contaminate our MIT-licensed submission repo because we redistribute only URLs and SHA-256 hashes, not the fixtures themselves.
