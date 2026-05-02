# Spec #3 — Layered Test Sandbox (L0-L3)

> **Status: SHIPPED.** L0 (lint, GHA), L1 (Docker compose, GHA + local), L3 (QEMU microvm Packer build) all live. L2 (Sysbox SIFT-lite) is advisory-only per CLAUDE.md. Live wiring: `.github/workflows/l[0-3]-*.yml` + `docker/l1-compose.yml` + `packer/sift-microvm.pkr.hcl`. Local smoke loop: `bash scripts/run-all-smokes.sh` (14/14 green).

**Date:** 2026-04-23
**Status:** Design — awaiting user approval
**Blocks:** Spec #1 (Build Swarm), Spec #2 (Product)
**Parent:** `2026-04-23-find-evil-automation-master-design.md`

---

## 1. Problem statement

The build swarm needs to iterate 50-100 times per night against code it's writing, each PR validated for lint, build, unit tests, and DFIR integration. The shipped Product must be verified end-to-end against the judges' actual SIFT VM before every release. One environment can't do both: fast iteration needs speed; shipped-product verification needs parity. Solution: **four layers**, each tuned for a different question.

## 2. Questions each layer answers

| Layer | Answers |
|---|---|
| **L0** | "Does this code even lint / typecheck?" |
| **L1** | "Do unit tests + isolated build pass?" |
| **L2** | "Do DFIR tools actually produce expected output on sample evidence?" |
| **L3** | "Would this pass on the judges' real SIFT VM?" |

A PR that passes L0+L1 can merge. L2 runs per PR but is non-blocking. L3 runs nightly on main + weekly goldens, authoritative for release gates.

## 3. Architecture

```
┌─────────── L0: Lint / Static ───────────┐
│ GHA ubuntu-24.04, no containers        │  ~30-60s
│ hadolint / shellcheck / ruff / eslint  │
│ cargo check / cargo clippy / tsc --noEmit │
└─────────────────────────────────────────┘
             │ pass
             ▼
┌─────────── L1: Unit / Build ────────────┐
│ Docker Compose, Ubuntu 22.04            │  ~2-5min
│ cargo test / pytest / pnpm build+test   │
│ No privileged, no FUSE, no evidence     │
└─────────────────────────────────────────┘
             │ pass
             ▼
┌─────────── L2: SIFT-lite ───────────────┐
│ Sysbox runtime (rootless systemd+FUSE)  │  ~5-10min
│ cast install teamdfir/sift inside       │
│ Run DFIR tools on small OTRF fixtures   │
└─────────────────────────────────────────┘
             │ merge allowed after L2 non-blocking
             ▼
┌─────────── L3: Full SIFT parity ────────┐
│ QEMU microvm + qcow2 snapshot-restore  │  ~1-3min (warm)
│ Packer-built from sift-2026.03.24.ova   │  ~35-55s (cold)
│ GHA KVM larger runners (4-core Linux)   │
│ Nightly on main + weekly goldens        │
└─────────────────────────────────────────┘
```

## 4. Layer specifications

### 4.1 L0 — Lint / Static Analysis

**Runtime:** GitHub Actions `ubuntu-24.04`, no containers, no KVM.
**Triggers:** every push / PR.
**Budget:** 30-60s wall clock.
**Tools:**
- `hadolint` — Dockerfiles
- `shellcheck` — `.sh` scripts
- `yamllint` — YAML config
- `ruff check` + `ruff format --check` — Python
- `cargo check` + `cargo clippy --deny warnings` — Rust
- `pnpm run lint` (ESLint + Prettier) — TypeScript
- `tsc --noEmit` — TypeScript typecheck
- `artifacts lint` (Velociraptor-style) — custom YAML artifact definitions (future)

**Pass criterion:** all checks green.

**File:** `.github/workflows/l0-static.yml`

---

### 4.2 L1 — Unit / Build

**Runtime:** Docker Compose on dev laptop + GHA standard runner (no KVM required).
**Base image:** `ubuntu:22.04` (matches SIFT's Ubuntu base per teamdfir/sift-saltstack).
**Triggers:** every push / PR.
**Budget:** 2-5min wall clock.

**Image layers (`docker/l1-devbase.Dockerfile`):**
```dockerfile
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y \
    build-essential curl git pkg-config libssl-dev \
    python3.11 python3.11-venv python3-pip \
    libyara-dev libewf-dev libafflib-dev \
    sleuthkit \
    postgresql-client \
 && rm -rf /var/lib/apt/lists/*

# Rust toolchain (pinned)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    --default-toolchain 1.83.0 --component clippy rustfmt

# Node via corepack + pnpm pinned
RUN curl -fsSL https://fnm.vercel.app/install | bash && \
    ~/.local/share/fnm/fnm install 20 && \
    corepack enable && corepack prepare pnpm@9.12.0 --activate

# Python deps via uv (fast)
RUN pip install uv==0.5.8
WORKDIR /workspace
```

**Tests run:**
- `cargo test --workspace --locked`
- `cargo build --release --locked`
- `uv run pytest -xvs --cov`
- `pnpm install --frozen-lockfile && pnpm build && pnpm test`

**Pass criterion:** all green. **PR merge gated on L1 passing.**

**File:** `.github/workflows/l1-unit.yml` + `docker/l1-devbase.Dockerfile`

---

### 4.3 L2 — SIFT-lite (Sysbox)

**Runtime:** Sysbox runtime (Apache-2.0). Gives systemd + dockerd + FUSE + loopback inside a rootless container **without `--privileged`**.
**Triggers:** every push / PR (non-blocking — advisory).
**Budget:** 5-10min wall clock.

**Why Sysbox (not plain Docker):**
- SIFT installs ship as salt states that expect systemd
- Volatility3 / plaso need loop-mount access for E01/raw images
- `--privileged` is a gaping hole if this ever runs untrusted code — the build swarm's worker code qualifies as untrusted
- Sysbox gives the capabilities we need without the blast radius

**Image build (`docker/l2-siftlite.Dockerfile`):**
```dockerfile
# Build-time: run cast inside Sysbox to install SIFT's saltstack
FROM nestybox/ubuntu-22.04-systemd:latest
RUN apt-get update && apt-get install -y \
    git python3-pip curl && \
    pip install teamdfir-cast && \
    cast install teamdfir/sift --profile server-minimal
# Result image: SIFT userland minus GUI, ~2-3GB compressed
```

**Runtime invocation:**
```bash
sudo dockerd --add-runtime=sysbox-runc=/usr/bin/sysbox-runc
docker run --runtime=sysbox-runc --rm \
  -v $(pwd)/fixtures:/fixtures:ro \
  -v $(pwd)/services/mcp/target/release/findevil-mcp:/usr/local/bin/findevil-mcp:ro \
  findevil/l2-siftlite:latest \
  /usr/local/bin/run-dfir-smoke.sh
```

**Tests run:**
- Hayabusa Sigma scan on OTRF Security-Datasets sample EVTX
- Chainsaw MFT timeline on small fixture
- Volatility3 pslist on Volatility Foundation memory sample
- Rust MCP server round-trip (`case_open` → `evtx_query` → result validation)

**Pass criterion:** all 4 smoke tests produce expected output hashes. Advisory only — does **not** block PR merge (prevents flaky DFIR tools from stalling the swarm).

**File:** `.github/workflows/l2-sift-lite.yml` + `docker/l2-siftlite.Dockerfile`

---

### 4.4 L3 — Full SIFT VM parity

**Runtime:** QEMU `-machine microvm` with direct kernel boot + qcow2 snapshot-restore, on GHA KVM-enabled larger runners (`ubuntu-latest-4-core-kvm` or equivalent).
**Triggers:** nightly on `main` + manual for release candidates.
**Budget:** 3-8s warm resume + 5-15min test run = ~5-20min total.

**Why not Firecracker:** Firecracker forbids legacy PCI + VirtIO-GPU. SIFT's OVA uses virtio-scsi + e1000; conversion = boot failure. Parity loss > speed win.

**Why not plain Vagrant:** no snapshot-restore, 2-3min cold boot every run, no CI-friendly headless mode.

**One-time Packer build (`packer/sift-microvm.pkr.hcl`):**
```hcl
source "qemu" "sift_microvm" {
  iso_url          = "./sift-2026.03.24.ova"
  iso_checksum     = "none"   # local file
  disk_size        = "40G"
  format           = "qcow2"
  headless         = true
  machine_type     = "microvm"
  cpus             = 4
  memory           = 8192
  accelerator      = "kvm"
  qemuargs = [
    ["-kernel", "./sift-kernel/vmlinuz"],
    ["-append", "console=ttyS0 root=/dev/vda1 rw"],
    ["-netdev", "user,id=net0,hostfwd=tcp::2222-:22"],
    ["-device", "virtio-net-device,netdev=net0"]
  ]
  ssh_username     = "sansforensics"
  ssh_password     = "forensics"
  ssh_timeout      = "10m"
  boot_wait        = "30s"
  shutdown_command = "sudo shutdown -P now"
}

build {
  sources = ["source.qemu.sift_microvm"]
  provisioner "file" {
    source      = "./scripts/sift-setup.sh"
    destination = "/tmp/sift-setup.sh"
  }
  provisioner "shell" {
    inline = [
      "sudo bash /tmp/sift-setup.sh",
      # snapshot the post-login state for -loadvm
      "sudo qemu-img snapshot -c warm /var/qemu/sift.qcow2"
    ]
  }
  post-processor "compress" {
    output = "./artifacts/sift-microvm-warm.qcow2.zst"
  }
}
```

**Per-CI-run invocation:**
```bash
# Pull cached warm image from GHA cache / OCI registry
zstd -d < sift-microvm-warm.qcow2.zst > sift.qcow2

# Boot to snapshot in 3-8s
qemu-system-x86_64 \
  -machine microvm,accel=kvm \
  -cpu host -smp 4 -m 8G \
  -drive file=sift.qcow2,if=virtio,format=qcow2 \
  -netdev user,hostfwd=tcp::2222-:22 \
  -device virtio-net-device,netdev=net0 \
  -loadvm warm \
  -nographic -serial stdio &

# Wait for SSH
until nc -z localhost 2222; do sleep 0.5; done

# Deploy built Product + fixtures, run golden test
scp -P 2222 -r ./release/ sansforensics@localhost:~/findevil/
scp -P 2222 ./fixtures/nist-hacking-case.E01 sansforensics@localhost:~/
ssh -p 2222 sansforensics@localhost \
  "~/findevil/find-evil run --case ~/nist-hacking-case.E01 --unattended" \
  > run.log

# Verify verdict matches golden
diff <(jq '.findings' run.log) ./goldens/nist-hacking-case.findings.json
```

**Tests run (golden-run matrix):**
- NIST CFReDS Hacking Case → expect 14 known findings, verdict "CONFIRMED_EVIL"
- OTRF Mordor APT3 replay → expect lateral movement signals
- Synthetic benign image → expect verdict "NO_EVIL"

**Pass criterion:** all goldens match. **Release candidate gated on L3 green.**

**GHA workflow (`.github/workflows/l3-sift-goldens.yml`):**
```yaml
jobs:
  golden-run:
    runs-on: ubuntu-latest-4-core-kvm
    if: ${{ runner.labels contains 'kvm' }}
    steps:
      - uses: actions/checkout@v4
      - name: Pull warm image from cache
        uses: actions/cache@v4
        with:
          path: sift-microvm-warm.qcow2.zst
          key: sift-microvm-${{ hashFiles('packer/**') }}
      - name: Boot + run goldens
        run: ./scripts/l3-run-goldens.sh
      - name: Upload verdict artifacts
        uses: actions/upload-artifact@v4
        with:
          name: l3-verdicts
          path: run.log
```

## 5. Fixtures (license-clean, shippable)

| Name | Size | License | Where used |
|---|---|---|---|
| NIST CFReDS Hacking Case | ~4.5GB E01 | Public domain (17 USC 105) | L3 golden |
| DFRWS Rodeo USB challenges | ~500MB DD each | Public domain | L1/L2 smoke |
| OTRF Security-Datasets (was Mordor) | MB each | MIT | L2 DFIR tool smoke |
| Volatility Foundation memory samples | variable | CC-BY | L2 + L3 memory tests |

**Storage:** Git LFS for sub-100MB fixtures, release asset + pull-cache for larger. NIST Hacking Case never touches the git tree — pulled by L3 script directly from `cfreds.nist.gov`.

## 6. CI platform choice

**Primary: GitHub Actions.**

| Concern | GHA stance |
|---|---|
| L0/L1 runners (no KVM) | Free tier covers swarm's 100 PRs/day |
| L2 with Sysbox | Needs `sudo` + systemd; run on GHA-hosted runners (works; Sysbox ships binaries) |
| L3 with KVM | GHA "larger runners" with KVM exposed — ~$0.016/min (~$0.08/run × 100/day = ~$240/mo) |
| Cost ceiling | Monitor monthly; if > $300, switch to Actuated ($250/mo flat) |

**Explicitly avoided:** BuildJet (shut down Jan 2026). Jenkins (too much ops). CircleCI (no advantage over GHA).

## 7. Budget (sandbox only)

| Line | Estimate |
|---|---|
| L0/L1 on GHA free tier | $0 |
| L2 on GHA standard Linux | ~$20/mo (advisory PR runs) |
| L3 on GHA KVM larger runners | ~$240-300/mo |
| Storage (GHA cache + LFS) | $0-10/mo |
| **Total** | **~$260-330/mo** |

## 8. Acceptance criteria

- [ ] `.github/workflows/l0-static.yml` runs on PR, green in <60s on a trivial PR
- [ ] `docker/l1-devbase.Dockerfile` builds locally and on GHA; `docker compose up l1` runs cargo/pytest/pnpm successfully
- [ ] `docker/l2-siftlite.Dockerfile` builds via Sysbox (locally); smoke-tests Hayabusa + Chainsaw + Volatility on fixtures
- [ ] `packer/sift-microvm.pkr.hcl` produces `sift-microvm-warm.qcow2.zst` from the OVA
- [ ] `scripts/l3-run-goldens.sh` boots warm snapshot in ≤10s on KVM runner
- [ ] L3 runs the NIST Hacking Case and matches `./goldens/nist-hacking-case.findings.json`
- [ ] Fixture URLs documented in `docs/fixtures.md` with SHA-256 hashes
- [ ] Monthly cost stays under $350 at 100 PR/day + nightly L3

## 9. Risks

| # | Risk | Mitigation |
|---|---|---|
| S1 | Sysbox unavailable on GHA-hosted runners | Fallback: run L2 only on self-hosted runner; if impossible, fallback to plain Docker + `--privileged` (documented security compromise) |
| S2 | SIFT kernel updates break microvm qcow2 | Re-run Packer build; pin kernel version in OVA filename |
| S3 | GHA KVM larger runners deprecated | Switch to Actuated ($250 flat); fallback tested in week 1 |
| S4 | qcow2 warm image > 5GB (GHA cache cap) | Chunk + reassemble, or use OCI artifact registry |
| S5 | Fixture license change | Pin NIST CFReDS to known-permanent URL; store SHA-256 hash for integrity |

## 10. Out of scope

- Windows/macOS/Linux cross-platform testing (Find Evil is Windows-evidence-focused)
- Network-based evidence (pcap) — deferred; not in v2 plan
- Anti-forensics simulation — deferred; covered by OTRF datasets if needed
- Graphical demos on L3 — headless only; demo recordings use local SIFT VM

## 11. Open questions (for user)

Only one:
1. Do you want `main` branch protection enabled to require L0+L1 green before merge? (Strongly recommend yes; default in implementation unless you object.)

(OVA filename `sift-2026.03.24.ova` confirmed present at repo root; Packer reads it from there directly.)
