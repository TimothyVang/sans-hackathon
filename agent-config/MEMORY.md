# MEMORY.md — Tier 1 (always loaded)

## Artifact semantics (common misreads)
- Amcache `LastModified` is catalog-registration time, NOT execution time.
- ShimCache order is LRU-ish on <Win8, insertion-order on >=Win8.1; presence != execution on modern Windows.
- Prefetch disabled on SSDs by some builds/GPOs — absence is not evidence of absence.
- `$MFT` $SI timestamps are trivially stompable; prefer $FN for tamper detection.
- UsnJrnl wraps; gaps are normal, not suspicious by themselves.
- EVTX EID 4624 Type 3 = network logon; Type 10 = RemoteInteractive (RDP).
- Sysmon EID 1 ProcessGuid is the correlation key, not PID.
- Sigma/Hayabusa hits are triage leads until the raw EVTX and a corroborating artifact class support the claim.
- Memory-only process or injection evidence does not prove disk execution or exfiltration.
- `covered_no_finding` means scoped tools ran without qualifying evidence; it is not clean, cleared, disproven, or absence of the technique.

## Attacker tradecraft priors
- LOLBins to check first: rundll32, regsvr32, mshta, wmic, certutil, bitsadmin.
- Scheduled Tasks in `\Microsoft\Windows\` namespace are a classic hiding spot.
- Run/RunOnce, Services, WMI event subscriptions, Image File Execution Options = persistence top-5.

## Reporting conventions
- All timestamps UTC, ISO-8601, trailing Z.
- Hashes: SHA-256 preferred, MD5 only when tool-limited.
- Never assert attribution.
