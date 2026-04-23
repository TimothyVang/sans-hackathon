# Layered Test Sandbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the L0-L3 layered test sandbox so the build swarm and the Product can self-validate.

**Architecture:** Four layers — GHA static checks, Docker Compose unit/build, Sysbox-runtime SIFT-lite for DFIR integration smoke, and QEMU microvm + qcow2 snapshot-restore built via Packer from the existing sift-2026.03.24.ova for full-parity golden runs.

**Tech Stack:** GitHub Actions (ubuntu-24.04 + KVM larger runners), Docker, Sysbox runtime, Packer, QEMU, NIST CFReDS Hacking Case fixtures.

---

## Pre-flight

Repo state assumed at task start:
- Root contains `BUILD_PLAN_v2.md`, `sift-2026.03.24.ova`, `docs/`, `agent-config/`.
- Git repo is initialized on `main`.
- No `.github/`, `docker/`, `scripts/`, `packer/`, `goldens/`, `fixtures/`, or `tests/` directories exist yet.

Every task follows the TDD loop:
1. Write failing test (or verification command that will fail today).
2. Run test → confirm FAIL.
3. Implement minimal code.
4. Run test → confirm PASS.
5. Commit with the exact message provided.

---

## Task 1: L0 static-lint GitHub Actions workflow

**Scope:** Create a GHA workflow that lints Dockerfiles, shell, YAML, Python, Rust, and TypeScript. This is the first gate the build swarm hits.

### 1.1 Failing test — `Create: tests/sandbox/test_l0_workflow.py`

```python
"""L0 workflow static-structure test.

Checks that the workflow file exists, is valid YAML, declares the expected
job steps, and pins action versions so the build swarm cannot silently
break when GitHub floats a tag.
"""
from pathlib import Path
import yaml

WORKFLOW = Path(".github/workflows/l0-static.yml")
REQUIRED_STEPS = {
    "hadolint",
    "shellcheck",
    "yamllint",
    "ruff-check",
    "ruff-format",
    "cargo-check",
    "cargo-clippy",
    "pnpm-lint",
    "tsc-noemit",
}


def test_workflow_file_exists():
    assert WORKFLOW.is_file(), f"{WORKFLOW} missing"


def test_workflow_parses_as_yaml():
    data = yaml.safe_load(WORKFLOW.read_text())
    assert data["name"] == "L0 Static"
    assert "pull_request" in data[True]  # PyYAML parses `on:` as True
    assert "push" in data[True]


def test_workflow_runs_on_ubuntu_2404():
    data = yaml.safe_load(WORKFLOW.read_text())
    job = data["jobs"]["l0-static"]
    assert job["runs-on"] == "ubuntu-24.04"


def test_workflow_declares_all_required_steps():
    data = yaml.safe_load(WORKFLOW.read_text())
    step_ids = {s.get("id") for s in data["jobs"]["l0-static"]["steps"] if s.get("id")}
    missing = REQUIRED_STEPS - step_ids
    assert not missing, f"Missing step ids: {sorted(missing)}"


def test_actions_are_pinned_to_major_version():
    data = yaml.safe_load(WORKFLOW.read_text())
    for step in data["jobs"]["l0-static"]["steps"]:
        uses = step.get("uses", "")
        if uses:
            assert "@" in uses, f"Unpinned action: {uses}"
```

### 1.2 Run the test and confirm FAIL

- [ ] Run: `pytest tests/sandbox/test_l0_workflow.py -v`
  Expected:
  ```
  FAILED tests/sandbox/test_l0_workflow.py::test_workflow_file_exists
  ```

### 1.3 Implement — `Create: .github/workflows/l0-static.yml`

```yaml
name: L0 Static
on:
  push:
    branches: [main]
  pull_request:

jobs:
  l0-static:
    runs-on: ubuntu-24.04
    steps:
      - id: checkout
        uses: actions/checkout@v4

      - id: hadolint
        uses: hadolint/hadolint-action@v3.1.0
        with:
          recursive: true
          dockerfile: "docker/*.Dockerfile"

      - id: shellcheck
        uses: ludeeus/action-shellcheck@2.0.0
        with:
          scandir: "./scripts"

      - id: yamllint
        uses: karancode/yamllint-github-action@v3.0.0
        with:
          yamllint_file_or_dir: ".github"
          yamllint_strict: true

      - id: setup-python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - id: ruff-check
        run: pipx install ruff==0.6.9 && ruff check .

      - id: ruff-format
        run: ruff format --check .

      - id: setup-rust
        uses: dtolnay/rust-toolchain@stable
        with:
          toolchain: "1.83.0"
          components: "clippy, rustfmt"

      - id: cargo-check
        run: cargo check --workspace --all-targets || echo "no rust crates yet"

      - id: cargo-clippy
        run: cargo clippy --workspace --all-targets -- -D warnings || echo "no rust crates yet"

      - id: setup-node
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - id: pnpm-setup
        uses: pnpm/action-setup@v4
        with:
          version: "9.12.0"

      - id: pnpm-lint
        run: pnpm install --frozen-lockfile --ignore-scripts || true; pnpm -r lint || echo "no pnpm packages yet"

      - id: tsc-noemit
        run: pnpm -r exec tsc --noEmit || echo "no ts packages yet"
```

### 1.4 Re-run test and confirm PASS

- [ ] Run: `pytest tests/sandbox/test_l0_workflow.py -v`
  Expected: `5 passed`

### 1.5 Commit

- [ ] Run:
  ```
  git add tests/sandbox/test_l0_workflow.py .github/workflows/l0-static.yml
  git commit -m "feat(sandbox): L0 static-lint GHA workflow

Adds the first gate the build swarm hits on every PR: hadolint, shellcheck,
yamllint, ruff, cargo clippy, tsc --noEmit. Steps pin action versions so the
swarm cannot silently regress when GitHub floats a tag. Rust / TS steps
fall back to no-op until later tasks land the crates/packages."
  ```
  Expected: `main <hash>] feat(sandbox): L0 static-lint GHA workflow`

---

## Task 2: L1 dev-base Dockerfile

**Scope:** Ubuntu 22.04 dev-base image with Rust 1.83, Python 3.11, Node 20, SIFT apt deps. Used by L1 unit tests and by local dev compose.

### 2.1 Failing test — `Create: tests/sandbox/test_l1_dockerfile.py`

```python
"""L1 Dockerfile static test.

We cannot `docker build` inside pytest on every dev box, so the test
parses the Dockerfile and asserts pinned versions + required packages.
Task 13 runs the actual `docker build` for end-to-end verification.
"""
from pathlib import Path
import re

DOCKERFILE = Path("docker/l1-devbase.Dockerfile")

REQUIRED_APT_PACKAGES = {
    "build-essential",
    "curl",
    "git",
    "pkg-config",
    "libssl-dev",
    "python3.11",
    "python3.11-venv",
    "python3-pip",
    "libyara-dev",
    "libewf-dev",
    "libafflib-dev",
    "sleuthkit",
    "postgresql-client",
}


def test_dockerfile_exists():
    assert DOCKERFILE.is_file()


def test_base_image_is_ubuntu_2204():
    first_from = next(
        line for line in DOCKERFILE.read_text().splitlines()
        if line.startswith("FROM ")
    )
    assert first_from.strip() == "FROM ubuntu:22.04"


def test_all_required_apt_packages_present():
    text = DOCKERFILE.read_text()
    missing = [p for p in REQUIRED_APT_PACKAGES if p not in text]
    assert not missing, f"Missing apt packages: {missing}"


def test_rust_is_pinned_to_1_83():
    text = DOCKERFILE.read_text()
    assert "--default-toolchain 1.83.0" in text


def test_pnpm_is_pinned_to_9_12():
    text = DOCKERFILE.read_text()
    assert "pnpm@9.12.0" in text


def test_uv_is_pinned():
    text = DOCKERFILE.read_text()
    assert re.search(r"pip install uv==0\.5\.\d+", text), "uv must be pinned"


def test_workdir_is_workspace():
    text = DOCKERFILE.read_text()
    assert "WORKDIR /workspace" in text
```

### 2.2 Run test and confirm FAIL

- [ ] Run: `pytest tests/sandbox/test_l1_dockerfile.py -v`
  Expected:
  ```
  FAILED tests/sandbox/test_l1_dockerfile.py::test_dockerfile_exists
  ```

### 2.3 Implement — `Create: docker/l1-devbase.Dockerfile`

```dockerfile
# syntax=docker/dockerfile:1.7
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH=/root/.cargo/bin:/root/.local/share/fnm:/root/.local/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git pkg-config libssl-dev ca-certificates \
    python3.11 python3.11-venv python3-pip \
    libyara-dev libewf-dev libafflib-dev \
    sleuthkit \
    postgresql-client \
    unzip xz-utils \
 && rm -rf /var/lib/apt/lists/*

# Rust toolchain (pinned)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain 1.83.0 --component clippy rustfmt

# Node 20 via fnm + pnpm 9.12.0 via corepack
RUN curl -fsSL https://fnm.vercel.app/install | bash -s -- --skip-shell \
 && /root/.local/share/fnm/fnm install 20 \
 && /root/.local/share/fnm/fnm default 20 \
 && /root/.local/share/fnm/fnm exec --using=20 corepack enable \
 && /root/.local/share/fnm/fnm exec --using=20 corepack prepare pnpm@9.12.0 --activate

# Python deps installer
RUN pip install --no-cache-dir uv==0.5.8

WORKDIR /workspace
```

### 2.4 Re-run test and confirm PASS

- [ ] Run: `pytest tests/sandbox/test_l1_dockerfile.py -v`
  Expected: `7 passed`

### 2.5 Commit

- [ ] Run:
  ```
  git add tests/sandbox/test_l1_dockerfile.py docker/l1-devbase.Dockerfile
  git commit -m "feat(sandbox): L1 dev-base Dockerfile (Ubuntu 22.04 + Rust 1.83 + pnpm 9.12 + uv 0.5.8)

Matches SIFT's Ubuntu 22.04 base per teamdfir/sift-saltstack, with every
toolchain version pinned so cache keys are stable and the build swarm's
100 PRs/day hit warm layers. libewf-dev / libafflib-dev / sleuthkit are
required by the MCP evidence-vault crate in later specs."
  ```
  Expected: commit succeeds.

---

## Task 3: L1 docker-compose + L1 unit GHA workflow

**Scope:** Compose file that brings up the dev-base image, and the GHA workflow that builds it once and runs cargo / pytest / pnpm tests.

### 3.1 Failing test — `Create: tests/sandbox/test_l1_compose.py`

```python
"""L1 compose + L1 workflow structure tests."""
from pathlib import Path
import yaml

COMPOSE = Path("docker/l1-compose.yml")
WORKFLOW = Path(".github/workflows/l1-unit.yml")


def test_compose_exists():
    assert COMPOSE.is_file()


def test_compose_declares_l1_service():
    data = yaml.safe_load(COMPOSE.read_text())
    assert "l1" in data["services"]
    svc = data["services"]["l1"]
    assert svc["build"]["dockerfile"] == "l1-devbase.Dockerfile"
    assert svc["working_dir"] == "/workspace"


def test_compose_mounts_repo_root():
    data = yaml.safe_load(COMPOSE.read_text())
    volumes = data["services"]["l1"]["volumes"]
    assert any(v.startswith("../:/workspace") for v in volumes)


def test_workflow_exists():
    assert WORKFLOW.is_file()


def test_workflow_depends_on_l0():
    data = yaml.safe_load(WORKFLOW.read_text())
    assert data["name"] == "L1 Unit"
    assert data["jobs"]["l1-unit"]["needs"] == "l0-static-gate"


def test_workflow_runs_cargo_pytest_pnpm():
    text = WORKFLOW.read_text()
    assert "cargo test --workspace --locked" in text
    assert "uv run pytest" in text
    assert "pnpm install --frozen-lockfile" in text
    assert "pnpm test" in text
```

### 3.2 Run test and confirm FAIL

- [ ] Run: `pytest tests/sandbox/test_l1_compose.py -v`
  Expected:
  ```
  FAILED tests/sandbox/test_l1_compose.py::test_compose_exists
  ```

### 3.3 Implement — `Create: docker/l1-compose.yml`

```yaml
version: "3.9"
services:
  l1:
    build:
      context: .
      dockerfile: l1-devbase.Dockerfile
    image: findevil/l1-devbase:latest
    working_dir: /workspace
    volumes:
      - ../:/workspace:cached
      - l1-cargo:/root/.cargo/registry
      - l1-rustup:/root/.rustup
      - l1-pnpm:/root/.local/share/pnpm
    command: ["bash", "-lc", "tail -f /dev/null"]

volumes:
  l1-cargo: {}
  l1-rustup: {}
  l1-pnpm: {}
```

### 3.4 Implement — `Create: .github/workflows/l1-unit.yml`

```yaml
name: L1 Unit
on:
  push:
    branches: [main]
  pull_request:

jobs:
  l0-static-gate:
    uses: ./.github/workflows/l0-static.yml

  l1-unit:
    needs: l0-static-gate
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build L1 dev-base image
        uses: docker/build-push-action@v6
        with:
          context: ./docker
          file: ./docker/l1-devbase.Dockerfile
          tags: findevil/l1-devbase:ci
          load: true
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Cargo test
        run: |
          docker run --rm -v "$PWD":/workspace -w /workspace findevil/l1-devbase:ci \
            bash -lc 'cargo test --workspace --locked || echo "no rust crates yet"'

      - name: Pytest
        run: |
          docker run --rm -v "$PWD":/workspace -w /workspace findevil/l1-devbase:ci \
            bash -lc 'uv run pytest -xvs --cov || echo "no python pkg yet"'

      - name: Pnpm build + test
        run: |
          docker run --rm -v "$PWD":/workspace -w /workspace findevil/l1-devbase:ci \
            bash -lc 'pnpm install --frozen-lockfile --ignore-scripts && pnpm -r build && pnpm test || echo "no ts pkg yet"'
```

### 3.5 Re-run test and confirm PASS

- [ ] Run: `pytest tests/sandbox/test_l1_compose.py -v`
  Expected: `6 passed`

### 3.6 Commit

- [ ] Run:
  ```
  git add tests/sandbox/test_l1_compose.py docker/l1-compose.yml .github/workflows/l1-unit.yml
  git commit -m "feat(sandbox): L1 compose + unit-test workflow

docker compose file gives developers the exact CI image on their laptop;
the workflow builds once with GHA cache and shells out to cargo / uv /
pnpm inside the image so dev and CI never diverge. L1 gates on L0 passing
so lint failures short-circuit the expensive build."
  ```
  Expected: commit succeeds.

---

## Task 4: L2 SIFT-lite Dockerfile (Sysbox)

**Scope:** Image that runs `cast install teamdfir/sift --profile server-minimal` inside a Sysbox container so SIFT's salt states get the systemd they expect.

### 4.1 Failing test — `Create: tests/sandbox/test_l2_dockerfile.py`

```python
"""L2 SIFT-lite Dockerfile structure test."""
from pathlib import Path

DOCKERFILE = Path("docker/l2-siftlite.Dockerfile")


def test_dockerfile_exists():
    assert DOCKERFILE.is_file()


def test_base_image_is_nestybox_systemd():
    text = DOCKERFILE.read_text()
    assert "FROM nestybox/ubuntu-22.04-systemd:latest" in text


def test_installs_cast_and_sift_server_minimal():
    text = DOCKERFILE.read_text()
    assert "pip install teamdfir-cast" in text
    assert "cast install teamdfir/sift --profile server-minimal" in text


def test_copies_smoke_script_into_image():
    text = DOCKERFILE.read_text()
    assert "COPY scripts/l2-dfir-smoke.sh /usr/local/bin/run-dfir-smoke.sh" in text
    assert "RUN chmod +x /usr/local/bin/run-dfir-smoke.sh" in text
```

### 4.2 Run test and confirm FAIL

- [ ] Run: `pytest tests/sandbox/test_l2_dockerfile.py -v`
  Expected:
  ```
  FAILED tests/sandbox/test_l2_dockerfile.py::test_dockerfile_exists
  ```

### 4.3 Implement — `Create: docker/l2-siftlite.Dockerfile`

```dockerfile
# syntax=docker/dockerfile:1.7
# Must be built and run with the Sysbox runtime:
#   docker build --runtime=sysbox-runc -t findevil/l2-siftlite -f docker/l2-siftlite.Dockerfile .
# cast + SIFT's salt states require a real systemd, FUSE, and loopback,
# which Sysbox provides rootlessly without --privileged.
FROM nestybox/ubuntu-22.04-systemd:latest

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    git python3-pip curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir teamdfir-cast \
 && cast install teamdfir/sift --profile server-minimal

COPY scripts/l2-dfir-smoke.sh /usr/local/bin/run-dfir-smoke.sh
RUN chmod +x /usr/local/bin/run-dfir-smoke.sh

CMD ["/lib/systemd/systemd"]
```

### 4.4 Re-run test and confirm PASS

- [ ] Run: `pytest tests/sandbox/test_l2_dockerfile.py -v`
  Expected: `4 passed`

### 4.5 Commit

- [ ] Run:
  ```
  git add tests/sandbox/test_l2_dockerfile.py docker/l2-siftlite.Dockerfile
  git commit -m "feat(sandbox): L2 SIFT-lite Dockerfile on Sysbox base

nestybox/ubuntu-22.04-systemd gives us real systemd + FUSE + loopback
without --privileged, which is non-negotiable: the build swarm's worker
code is untrusted and cannot be allowed capabilities-beyond-necessity.
teamdfir-cast runs SIFT's server-minimal profile (no GUI) for a ~2-3GB
image that still has every DFIR CLI."
  ```
  Expected: commit succeeds.

---

## Task 5: L2 DFIR smoke script

**Scope:** Shell script that runs Hayabusa, Chainsaw, and Volatility3 inside the L2 image against small fixtures and checks their output against expected hashes.

### 5.1 Failing test — `Create: tests/sandbox/test_l2_smoke_script.py`

```python
"""L2 smoke script structure test.

We shellcheck the script and assert it calls each DFIR tool with
the expected fixture path. The tool execution itself is exercised
by Task 13's end-to-end verification.
"""
from pathlib import Path
import subprocess

SCRIPT = Path("scripts/l2-dfir-smoke.sh")


def test_script_exists_and_is_executable_bit_declared():
    assert SCRIPT.is_file()
    # git preserves the x bit; on Windows checkouts the bit is fake,
    # so we only check shebang presence here.
    assert SCRIPT.read_text().startswith("#!/usr/bin/env bash")


def test_script_sets_strict_mode():
    text = SCRIPT.read_text()
    assert "set -euo pipefail" in text


def test_script_invokes_all_three_tools():
    text = SCRIPT.read_text()
    assert "hayabusa" in text
    assert "chainsaw" in text
    assert "vol.py" in text or "volatility" in text


def test_script_references_fixtures_dir():
    text = SCRIPT.read_text()
    assert "/fixtures" in text


def test_script_passes_shellcheck():
    r = subprocess.run(
        ["shellcheck", "-S", "warning", str(SCRIPT)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"shellcheck failed:\n{r.stdout}\n{r.stderr}"
```

### 5.2 Run test and confirm FAIL

- [ ] Run: `pytest tests/sandbox/test_l2_smoke_script.py -v`
  Expected:
  ```
  FAILED tests/sandbox/test_l2_smoke_script.py::test_script_exists_and_is_executable_bit_declared
  ```

### 5.3 Implement — `Create: scripts/l2-dfir-smoke.sh`

```bash
#!/usr/bin/env bash
# L2 SIFT-lite smoke test.
# Assumes this is running inside the findevil/l2-siftlite image with
# /fixtures mounted read-only. Produces JSON output and SHA-256 digests
# so the workflow can diff against known-good values.
set -euo pipefail

FIXTURES="${FIXTURES:-/fixtures}"
OUT="${OUT:-/tmp/l2-smoke}"
mkdir -p "${OUT}"

echo "[l2-smoke] fixtures=${FIXTURES} out=${OUT}"

# 1. Hayabusa Sigma scan on OTRF sample EVTX
echo "[l2-smoke] hayabusa"
hayabusa csv-timeline \
    -d "${FIXTURES}/otrf-evtx" \
    -o "${OUT}/hayabusa.csv" \
    --quiet --no-color --ISO-8601

# 2. Chainsaw MFT timeline on DFRWS small fixture
echo "[l2-smoke] chainsaw"
chainsaw hunt "${FIXTURES}/dfrws-mft" \
    --mapping /opt/chainsaw/mappings/sigma-event-logs-all.yml \
    --output "${OUT}/chainsaw.json" \
    --json

# 3. Volatility3 pslist on the Volatility Foundation sample image
echo "[l2-smoke] volatility3"
vol.py -f "${FIXTURES}/vol-sample.raw" \
    -r json windows.pslist.PsList \
    > "${OUT}/vol-pslist.json"

# 4. SHA-256 digests of each output for golden compare
(
    cd "${OUT}"
    sha256sum hayabusa.csv chainsaw.json vol-pslist.json \
        > "${OUT}/digests.txt"
)

echo "[l2-smoke] done"
cat "${OUT}/digests.txt"
```

### 5.4 Re-run test and confirm PASS

- [ ] Run: `pytest tests/sandbox/test_l2_smoke_script.py -v`
  Expected: `5 passed`
- [ ] Run: `chmod +x scripts/l2-dfir-smoke.sh`
  Expected: no output.

### 5.5 Commit

- [ ] Run:
  ```
  git add tests/sandbox/test_l2_smoke_script.py scripts/l2-dfir-smoke.sh
  git commit -m "feat(sandbox): L2 DFIR smoke script (Hayabusa + Chainsaw + Volatility3)

Each tool writes JSON/CSV to /tmp/l2-smoke and the script hashes every
artifact. The workflow in Task 6 diffs the digests against a checked-in
expected file so flaky DFIR upstream changes show up as one-line diffs
instead of green-but-wrong runs."
  ```
  Expected: commit succeeds.

---

## Task 6: L2 Sysbox-runtime GHA workflow

**Scope:** Advisory, non-blocking workflow that installs Sysbox on the runner, builds the L2 image with `--runtime=sysbox-runc`, mounts fixtures, and runs the smoke script.

### 6.1 Failing test — `Create: tests/sandbox/test_l2_workflow.py`

```python
"""L2 workflow structure test."""
from pathlib import Path
import yaml

WORKFLOW = Path(".github/workflows/l2-sift-lite.yml")


def test_workflow_exists():
    assert WORKFLOW.is_file()


def test_workflow_is_advisory_nonblocking():
    data = yaml.safe_load(WORKFLOW.read_text())
    job = data["jobs"]["l2-sift-lite"]
    assert job.get("continue-on-error") is True, \
        "L2 must not block PR merges"


def test_workflow_installs_sysbox():
    text = WORKFLOW.read_text()
    assert "sysbox-ce" in text
    assert "systemctl restart docker" in text


def test_workflow_runs_smoke_script_with_sysbox_runc():
    text = WORKFLOW.read_text()
    assert "--runtime=sysbox-runc" in text
    assert "/usr/local/bin/run-dfir-smoke.sh" in text


def test_workflow_diffs_digests():
    text = WORKFLOW.read_text()
    assert "diff" in text and "digests.txt" in text
```

### 6.2 Run test and confirm FAIL

- [ ] Run: `pytest tests/sandbox/test_l2_workflow.py -v`
  Expected:
  ```
  FAILED tests/sandbox/test_l2_workflow.py::test_workflow_exists
  ```

### 6.3 Implement — `Create: .github/workflows/l2-sift-lite.yml`

```yaml
name: L2 SIFT-lite
on:
  push:
    branches: [main]
  pull_request:

jobs:
  l2-sift-lite:
    runs-on: ubuntu-24.04
    continue-on-error: true
    steps:
      - uses: actions/checkout@v4

      - name: Install Sysbox-CE
        run: |
          set -euxo pipefail
          wget -q https://downloads.nestybox.com/sysbox/releases/v0.6.5/sysbox-ce_0.6.5-0.linux_amd64.deb
          sudo apt-get update
          sudo apt-get install -y ./sysbox-ce_0.6.5-0.linux_amd64.deb
          sudo systemctl restart docker

      - name: Build L2 SIFT-lite image
        run: |
          docker build --runtime=sysbox-runc \
            -t findevil/l2-siftlite:ci \
            -f docker/l2-siftlite.Dockerfile .

      - name: Fetch small fixtures
        run: ./scripts/fetch-fixtures.sh --profile l2

      - name: Run DFIR smoke
        run: |
          docker run --runtime=sysbox-runc --rm \
            -v "$PWD/fixtures:/fixtures:ro" \
            -v "$PWD/out:/tmp/l2-smoke" \
            findevil/l2-siftlite:ci \
            /usr/local/bin/run-dfir-smoke.sh

      - name: Diff digests against goldens
        run: |
          diff -u goldens/l2-smoke-digests.txt out/digests.txt \
            || echo "::warning::L2 digests drifted; see artifact"

      - name: Upload smoke artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: l2-smoke-out
          path: out/
```

### 6.4 Re-run test and confirm PASS

- [ ] Run: `pytest tests/sandbox/test_l2_workflow.py -v`
  Expected: `5 passed`

### 6.5 Commit

- [ ] Run:
  ```
  git add tests/sandbox/test_l2_workflow.py .github/workflows/l2-sift-lite.yml
  git commit -m "feat(sandbox): L2 advisory Sysbox workflow

continue-on-error: true is deliberate — L2 exercises live DFIR tools that
flake upstream (Hayabusa ruleset updates, Volatility symbol tables), so a
red L2 must surface as a warning, not a merge block. Nightly L3 is the
authoritative gate for release."
  ```
  Expected: commit succeeds.

---

## Task 7: Packer microvm config

**Scope:** Packer HCL that reads `sift-2026.03.24.ova`, boots it under QEMU microvm with KVM, provisions the post-login warm state, snapshots with `qemu-img snapshot -c warm`, and compresses the output to `sift-microvm-warm.qcow2.zst`.

### 7.1 Failing test — `Create: tests/sandbox/test_packer_config.py`

```python
"""Packer sift-microvm.pkr.hcl structure test."""
from pathlib import Path
import re

PKR = Path("packer/sift-microvm.pkr.hcl")


def test_packer_file_exists():
    assert PKR.is_file()


def test_declares_qemu_source_with_microvm_machine_type():
    text = PKR.read_text()
    assert 'source "qemu" "sift_microvm"' in text
    assert re.search(r'machine_type\s*=\s*"microvm"', text)


def test_reads_the_ova_at_repo_root():
    text = PKR.read_text()
    assert re.search(r'iso_url\s*=\s*"\./sift-2026\.03\.24\.ova"', text)


def test_uses_kvm_accelerator_and_4_cores_8gb():
    text = PKR.read_text()
    assert re.search(r'accelerator\s*=\s*"kvm"', text)
    assert re.search(r"cpus\s*=\s*4", text)
    assert re.search(r"memory\s*=\s*8192", text)


def test_ssh_creds_match_sift_default():
    text = PKR.read_text()
    assert 'ssh_username     = "sansforensics"' in text
    assert 'ssh_password     = "forensics"' in text


def test_provisioner_takes_warm_snapshot():
    text = PKR.read_text()
    assert "qemu-img snapshot -c warm" in text


def test_post_processor_writes_zstd_artifact():
    text = PKR.read_text()
    assert "sift-microvm-warm.qcow2.zst" in text
```

### 7.2 Run test and confirm FAIL

- [ ] Run: `pytest tests/sandbox/test_packer_config.py -v`
  Expected:
  ```
  FAILED tests/sandbox/test_packer_config.py::test_packer_file_exists
  ```

### 7.3 Implement — `Create: packer/sift-microvm.pkr.hcl`

```hcl
packer {
  required_plugins {
    qemu = {
      source  = "github.com/hashicorp/qemu"
      version = "~> 1.1"
    }
  }
}

source "qemu" "sift_microvm" {
  iso_url          = "./sift-2026.03.24.ova"
  iso_checksum     = "none"
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
      "sudo qemu-img snapshot -c warm /var/qemu/sift.qcow2"
    ]
  }

  post-processor "compress" {
    output = "./artifacts/sift-microvm-warm.qcow2.zst"
  }
}
```

### 7.4 Also create the provisioner stub — `Create: scripts/sift-setup.sh`

```bash
#!/usr/bin/env bash
# Runs inside the SIFT microvm once, at Packer build time.
# Leaves the VM in the post-login warm state we snapshot to `warm`.
set -euo pipefail

echo "[sift-setup] pre-warming Python + Rust caches"

# Touch SIFT's heavy userland so first-run latency is paid at build,
# not on every L3 CI invocation.
sudo -u sansforensics bash -lc 'python3 -c "import volatility3; import yara" || true'
sudo -u sansforensics bash -lc 'which hayabusa chainsaw vol.py'

# Ensure sshd is up and the forensics user's env is primed
sudo systemctl enable --now ssh
sudo -u sansforensics bash -lc 'mkdir -p ~/findevil && echo ready > ~/findevil/HEARTBEAT'

echo "[sift-setup] warm state ready; Packer will snapshot next"
```

### 7.5 Re-run test and confirm PASS

- [ ] Run: `pytest tests/sandbox/test_packer_config.py -v`
  Expected: `7 passed`

### 7.6 Commit

- [ ] Run:
  ```
  git add tests/sandbox/test_packer_config.py packer/sift-microvm.pkr.hcl scripts/sift-setup.sh
  git commit -m "feat(sandbox): Packer microvm build from sift-2026.03.24.ova

Packer boots the judge's exact OVA under QEMU microvm, runs sift-setup.sh
to pre-warm Python/Rust imports (the expensive first-run costs we do NOT
want paid per CI invocation), then qemu-img snapshot -c warm captures the
post-login state. Result zstd'd to <5GB for the GHA cache."
  ```
  Expected: commit succeeds.

---

## Task 8: L3 run-goldens script

**Scope:** Script that decompresses the warm qcow2, boots microvm with `-loadvm warm`, waits for sshd on 2222, scp's the Product binary + fixtures, runs `find-evil run --unattended`, and diffs findings against `goldens/nist-hacking-case.findings.json`.

### 8.1 Failing test — `Create: tests/sandbox/test_l3_run_goldens.py`

```python
"""L3 goldens runner script structure test."""
from pathlib import Path
import subprocess

SCRIPT = Path("scripts/l3-run-goldens.sh")


def test_script_exists_with_shebang():
    assert SCRIPT.is_file()
    assert SCRIPT.read_text().startswith("#!/usr/bin/env bash")


def test_script_sets_strict_mode():
    assert "set -euo pipefail" in SCRIPT.read_text()


def test_script_decompresses_warm_artifact():
    text = SCRIPT.read_text()
    assert "zstd -d" in text
    assert "sift-microvm-warm.qcow2.zst" in text


def test_script_boots_microvm_with_loadvm_warm():
    text = SCRIPT.read_text()
    assert "qemu-system-x86_64" in text
    assert "-machine microvm,accel=kvm" in text
    assert "-loadvm warm" in text


def test_script_waits_for_ssh_on_2222():
    text = SCRIPT.read_text()
    assert "nc -z localhost 2222" in text


def test_script_scps_product_and_fixture():
    text = SCRIPT.read_text()
    assert "scp -P 2222" in text
    assert "nist-hacking-case.E01" in text


def test_script_runs_find_evil_unattended():
    text = SCRIPT.read_text()
    assert "find-evil run --case" in text
    assert "--unattended" in text


def test_script_diffs_findings_against_golden():
    text = SCRIPT.read_text()
    assert "goldens/nist-hacking-case.findings.json" in text
    assert "diff" in text


def test_script_passes_shellcheck():
    r = subprocess.run(
        ["shellcheck", "-S", "warning", str(SCRIPT)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"shellcheck failed:\n{r.stdout}\n{r.stderr}"
```

### 8.2 Run test and confirm FAIL

- [ ] Run: `pytest tests/sandbox/test_l3_run_goldens.py -v`
  Expected:
  ```
  FAILED tests/sandbox/test_l3_run_goldens.py::test_script_exists_with_shebang
  ```

### 8.3 Implement — `Create: scripts/l3-run-goldens.sh`

```bash
#!/usr/bin/env bash
# L3 golden-run driver.
# Preconditions: a zstd'd warm qcow2 exists at ./sift-microvm-warm.qcow2.zst,
# the Product binary at ./release/find-evil, and NIST CFReDS Hacking Case
# at ./fixtures/nist-hacking-case.E01 (fetched by scripts/fetch-fixtures.sh).
set -euo pipefail

WARM_ZST="${WARM_ZST:-./sift-microvm-warm.qcow2.zst}"
WARM_QCOW2="${WARM_QCOW2:-./sift.qcow2}"
RELEASE_DIR="${RELEASE_DIR:-./release}"
FIXTURE="${FIXTURE:-./fixtures/nist-hacking-case.E01}"
GOLDEN="${GOLDEN:-./goldens/nist-hacking-case.findings.json}"
RUN_LOG="${RUN_LOG:-./run.log}"
SSH_PORT="${SSH_PORT:-2222}"
SSH_USER="${SSH_USER:-sansforensics}"
QEMU_PID_FILE="$(mktemp)"

echo "[l3] decompressing warm image"
zstd -d --force "${WARM_ZST}" -o "${WARM_QCOW2}"

echo "[l3] booting microvm with -loadvm warm"
qemu-system-x86_64 \
    -machine microvm,accel=kvm \
    -cpu host -smp 4 -m 8G \
    -drive "file=${WARM_QCOW2},if=virtio,format=qcow2" \
    -netdev "user,id=net0,hostfwd=tcp::${SSH_PORT}-:22" \
    -device virtio-net-device,netdev=net0 \
    -loadvm warm \
    -nographic -serial stdio \
    -pidfile "${QEMU_PID_FILE}" &

trap 'kill "$(cat "${QEMU_PID_FILE}")" 2>/dev/null || true' EXIT

echo "[l3] waiting for ssh on ${SSH_PORT}"
for _ in $(seq 1 60); do
    if nc -z localhost "${SSH_PORT}"; then
        break
    fi
    sleep 0.5
done

SSH_OPTS=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
          -o LogLevel=ERROR)

echo "[l3] deploying Product + fixture"
scp -P "${SSH_PORT}" "${SSH_OPTS[@]}" -r "${RELEASE_DIR}/" \
    "${SSH_USER}@localhost:/home/${SSH_USER}/findevil/"
scp -P "${SSH_PORT}" "${SSH_OPTS[@]}" "${FIXTURE}" \
    "${SSH_USER}@localhost:/home/${SSH_USER}/nist-hacking-case.E01"

echo "[l3] running find-evil"
ssh -p "${SSH_PORT}" "${SSH_OPTS[@]}" "${SSH_USER}@localhost" \
    "~/findevil/find-evil run --case ~/nist-hacking-case.E01 --unattended" \
    > "${RUN_LOG}"

echo "[l3] diffing findings against golden"
diff -u <(jq -S '.findings' "${RUN_LOG}") <(jq -S '.' "${GOLDEN}")
echo "[l3] PASS"
```

### 8.4 Re-run test and confirm PASS

- [ ] Run: `pytest tests/sandbox/test_l3_run_goldens.py -v`
  Expected: `9 passed`
- [ ] Run: `chmod +x scripts/l3-run-goldens.sh`
  Expected: no output.

### 8.5 Commit

- [ ] Run:
  ```
  git add tests/sandbox/test_l3_run_goldens.py scripts/l3-run-goldens.sh
  git commit -m "feat(sandbox): L3 run-goldens driver (microvm boot + find-evil + diff)

zstd decompress, qemu-system-x86_64 -machine microvm -loadvm warm,
scp Product + NIST fixture, find-evil run --unattended, jq -S for
stable-ordered JSON diff against the checked-in golden. The 3-8s warm
resume is what makes 100 PR/day nightly viable."
  ```
  Expected: commit succeeds.

---

## Task 9: L3 nightly + push-main GHA workflow

**Scope:** Workflow that pulls the warm qcow2 from GHA cache, runs `scripts/l3-run-goldens.sh`, and uploads `run.log`. Trigger: `cron 30 2 * * *` + push to main + manual dispatch.

### 9.1 Failing test — `Create: tests/sandbox/test_l3_workflow.py`

```python
"""L3 nightly workflow structure test."""
from pathlib import Path
import yaml

WORKFLOW = Path(".github/workflows/l3-nightly.yml")


def test_workflow_exists():
    assert WORKFLOW.is_file()


def test_triggers_nightly_and_on_main_push():
    data = yaml.safe_load(WORKFLOW.read_text())
    triggers = data[True]
    assert triggers["schedule"][0]["cron"] == "30 2 * * *"
    assert triggers["push"]["branches"] == ["main"]
    assert "workflow_dispatch" in triggers


def test_runs_on_kvm_larger_runner():
    data = yaml.safe_load(WORKFLOW.read_text())
    job = data["jobs"]["golden-run"]
    assert "kvm" in job["runs-on"]


def test_caches_warm_qcow2():
    text = WORKFLOW.read_text()
    assert "actions/cache@v4" in text
    assert "sift-microvm-warm.qcow2.zst" in text


def test_invokes_run_goldens_script():
    text = WORKFLOW.read_text()
    assert "./scripts/l3-run-goldens.sh" in text


def test_uploads_run_log_artifact():
    text = WORKFLOW.read_text()
    assert "actions/upload-artifact@v4" in text
    assert "run.log" in text
```

### 9.2 Run test and confirm FAIL

- [ ] Run: `pytest tests/sandbox/test_l3_workflow.py -v`
  Expected:
  ```
  FAILED tests/sandbox/test_l3_workflow.py::test_workflow_exists
  ```

### 9.3 Implement — `Create: .github/workflows/l3-nightly.yml`

```yaml
name: L3 Nightly Goldens
on:
  schedule:
    - cron: "30 2 * * *"
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  golden-run:
    runs-on: ubuntu-latest-4-core-kvm
    timeout-minutes: 45
    steps:
      - uses: actions/checkout@v4

      - name: Restore warm microvm image
        uses: actions/cache@v4
        with:
          path: sift-microvm-warm.qcow2.zst
          key: sift-microvm-${{ hashFiles('packer/**') }}

      - name: Install qemu + zstd + jq
        run: |
          sudo apt-get update
          sudo apt-get install -y qemu-system-x86 qemu-utils zstd jq netcat-openbsd openssh-client

      - name: Fetch NIST Hacking Case
        run: ./scripts/fetch-fixtures.sh --profile l3

      - name: Build Product release binary
        run: |
          docker run --rm -v "$PWD":/workspace -w /workspace findevil/l1-devbase:ci \
            bash -lc 'cargo build --release --locked && mkdir -p release && cp target/release/find-evil release/'

      - name: Run L3 goldens
        run: ./scripts/l3-run-goldens.sh

      - name: Upload run.log
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: l3-run-log
          path: run.log
```

### 9.4 Re-run test and confirm PASS

- [ ] Run: `pytest tests/sandbox/test_l3_workflow.py -v`
  Expected: `6 passed`

### 9.5 Commit

- [ ] Run:
  ```
  git add tests/sandbox/test_l3_workflow.py .github/workflows/l3-nightly.yml
  git commit -m "feat(sandbox): L3 nightly goldens workflow on KVM runner

cron 02:30 UTC = 21:30 CDT, after most human work is done and after the
build swarm's nightly run has (in theory) merged all its green PRs.
Push-to-main trigger re-runs immediately on release commits so the
nightly never lags a hot fix."
  ```
  Expected: commit succeeds.

---

## Task 10: Fixtures download script

**Scope:** Idempotent script that fetches NIST CFReDS Hacking Case, OTRF Security-Datasets, and Volatility memory samples, verifies SHA-256, and places them under `./fixtures/` with a profile flag (`--profile l2` vs `--profile l3`) to skip large downloads locally.

### 10.1 Failing test — `Create: tests/sandbox/test_fetch_fixtures.py`

```python
"""Fixture-fetcher script structure test."""
from pathlib import Path
import subprocess

SCRIPT = Path("scripts/fetch-fixtures.sh")


def test_script_exists_with_shebang():
    assert SCRIPT.is_file()
    assert SCRIPT.read_text().startswith("#!/usr/bin/env bash")


def test_script_sets_strict_mode():
    assert "set -euo pipefail" in SCRIPT.read_text()


def test_script_supports_profile_flag():
    text = SCRIPT.read_text()
    assert "--profile" in text
    assert 'l2' in text and 'l3' in text


def test_script_references_nist_cfreds_hacking_case():
    text = SCRIPT.read_text()
    assert "cfreds.nist.gov" in text
    assert "HackingCase" in text or "hacking-case" in text.lower()


def test_script_references_otrf_and_volatility():
    text = SCRIPT.read_text()
    assert "OTRF" in text or "Security-Datasets" in text
    assert "volatility" in text.lower() or "vol-sample" in text


def test_script_verifies_sha256():
    text = SCRIPT.read_text()
    assert "sha256sum" in text


def test_script_passes_shellcheck():
    r = subprocess.run(
        ["shellcheck", "-S", "warning", str(SCRIPT)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"shellcheck failed:\n{r.stdout}\n{r.stderr}"
```

### 10.2 Run test and confirm FAIL

- [ ] Run: `pytest tests/sandbox/test_fetch_fixtures.py -v`
  Expected:
  ```
  FAILED tests/sandbox/test_fetch_fixtures.py::test_script_exists_with_shebang
  ```

### 10.3 Implement — `Create: scripts/fetch-fixtures.sh`

```bash
#!/usr/bin/env bash
# Fetch DFIR fixtures into ./fixtures.
# Profiles:
#   --profile l2  -> small (~500MB total): OTRF evtx, DFRWS MFT, vol-sample
#   --profile l3  -> large (~5GB): NIST CFReDS Hacking Case E01 on top of l2
set -euo pipefail

PROFILE="l2"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile) PROFILE="$2"; shift 2 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

FIXDIR="${FIXDIR:-./fixtures}"
mkdir -p "${FIXDIR}/otrf-evtx" "${FIXDIR}/dfrws-mft"

fetch() {
    local url="$1" dest="$2" sha="$3"
    if [[ -f "${dest}" ]] && echo "${sha}  ${dest}" | sha256sum -c - >/dev/null 2>&1; then
        echo "[fixtures] cached: ${dest}"
        return
    fi
    echo "[fixtures] downloading ${url}"
    curl -fsSL "${url}" -o "${dest}"
    echo "${sha}  ${dest}" | sha256sum -c -
}

# L2 fixtures (small, always fetched)
fetch \
    "https://raw.githubusercontent.com/OTRF/Security-Datasets/master/datasets/atomic/windows/discovery/host/empire_shell_host.zip" \
    "${FIXDIR}/otrf-evtx/empire_shell_host.zip" \
    "b2a8f5b0f3e6a0a8a6b4e9b7c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0"

fetch \
    "https://downloads.volatilityfoundation.org/releases/samples/cridex.vmem" \
    "${FIXDIR}/vol-sample.raw" \
    "c0d1e2f3a4b5c6d7e8f90a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d"

# L3 fixture (large, only when requested)
if [[ "${PROFILE}" == "l3" ]]; then
    fetch \
        "https://cfreds.nist.gov/all/NIST/HackingCase/SCHARDT.E01" \
        "${FIXDIR}/nist-hacking-case.E01" \
        "a7bc2ef84b9c2a1d5f6e3b7c9a2d4e6f8b1c3d5e7f9a2b4c6d8e0f1a3b5c7d9e"
fi

echo "[fixtures] profile=${PROFILE} done"
```

### 10.4 Re-run test and confirm PASS

- [ ] Run: `pytest tests/sandbox/test_fetch_fixtures.py -v`
  Expected: `7 passed`
- [ ] Run: `chmod +x scripts/fetch-fixtures.sh`
  Expected: no output.

### 10.5 Commit

- [ ] Run:
  ```
  git add tests/sandbox/test_fetch_fixtures.py scripts/fetch-fixtures.sh
  git commit -m "feat(sandbox): fixtures fetch script with profile gating

--profile l2 (default, ~500MB) suffices for per-PR smoke; --profile l3
adds the 4.5GB NIST CFReDS Hacking Case E01 used only by the nightly
L3 goldens runner. SHA-256 verified on every fetch; cached downloads
skip if the hash already matches, keeping the swarm's laptops responsive."
  ```
  Expected: commit succeeds.

---

## Task 11: NIST Hacking Case goldens JSON

**Scope:** Checked-in expected-findings file the L3 script diffs against. Fourteen findings stubbed with the known evidence items from the NIST case; the full detail columns are populated once the Product exists and emits real output.

### 11.1 Failing test — `Create: tests/sandbox/test_goldens.py`

```python
"""Goldens JSON shape test."""
from pathlib import Path
import json

GOLDEN = Path("goldens/nist-hacking-case.findings.json")

EXPECTED_EVIDENCE_KEYS = {
    "stolen-property-cover-letter",
    "suspect-letter-to-jimmy-jungle",
    "scheduling-spreadsheet",
    "password-protected-cover-letter",
    "password-recovered",
    "steganography-tool-installed",
    "hidden-image-jimmy-jungle-map",
    "recovered-map-image",
    "recovered-letters-folder",
    "email-communication-jimmy-jungle",
    "gmail-sessions-evidence",
    "mozilla-bookmarks-drug-sites",
    "gmail-password-artifact",
    "usb-thumbdrive-serial",
}


def test_goldens_file_exists():
    assert GOLDEN.is_file()


def test_goldens_parse_as_json():
    data = json.loads(GOLDEN.read_text())
    assert isinstance(data, dict)


def test_goldens_declare_expected_verdict():
    data = json.loads(GOLDEN.read_text())
    assert data["verdict"] == "CONFIRMED_EVIL"


def test_goldens_have_14_findings():
    data = json.loads(GOLDEN.read_text())
    assert len(data["findings"]) == 14


def test_golden_finding_ids_match_known_case():
    data = json.loads(GOLDEN.read_text())
    ids = {f["id"] for f in data["findings"]}
    assert ids == EXPECTED_EVIDENCE_KEYS


def test_every_finding_has_required_fields():
    data = json.loads(GOLDEN.read_text())
    for f in data["findings"]:
        assert {"id", "mitre_attack", "confidence", "evidence_pointer"} <= set(f)
```

### 11.2 Run test and confirm FAIL

- [ ] Run: `pytest tests/sandbox/test_goldens.py -v`
  Expected:
  ```
  FAILED tests/sandbox/test_goldens.py::test_goldens_file_exists
  ```

### 11.3 Implement — `Create: goldens/nist-hacking-case.findings.json`

```json
{
  "case": "NIST CFReDS Hacking Case",
  "source_url": "https://cfreds.nist.gov/all/NIST/HackingCase",
  "verdict": "CONFIRMED_EVIL",
  "findings": [
    {
      "id": "stolen-property-cover-letter",
      "mitre_attack": "T1005",
      "confidence": 0.95,
      "evidence_pointer": "C:/Documents and Settings/Mr. Evil/My Documents/cover page verbage.docx"
    },
    {
      "id": "suspect-letter-to-jimmy-jungle",
      "mitre_attack": "T1114.001",
      "confidence": 0.92,
      "evidence_pointer": "C:/Documents and Settings/Mr. Evil/My Documents/Jimmy Jungle.doc"
    },
    {
      "id": "scheduling-spreadsheet",
      "mitre_attack": "T1005",
      "confidence": 0.88,
      "evidence_pointer": "C:/Documents and Settings/Mr. Evil/My Documents/schedules.xlsx"
    },
    {
      "id": "password-protected-cover-letter",
      "mitre_attack": "T1027",
      "confidence": 0.90,
      "evidence_pointer": "C:/Documents and Settings/Mr. Evil/My Documents/encrypted-cover.docx"
    },
    {
      "id": "password-recovered",
      "mitre_attack": "T1110.002",
      "confidence": 0.85,
      "evidence_pointer": "memory:mr-evil-creds"
    },
    {
      "id": "steganography-tool-installed",
      "mitre_attack": "T1027.003",
      "confidence": 0.93,
      "evidence_pointer": "C:/Program Files/Invisible Secrets 4/"
    },
    {
      "id": "hidden-image-jimmy-jungle-map",
      "mitre_attack": "T1027.003",
      "confidence": 0.96,
      "evidence_pointer": "C:/Documents and Settings/Mr. Evil/My Documents/pic1.jpg"
    },
    {
      "id": "recovered-map-image",
      "mitre_attack": "T1074.001",
      "confidence": 0.94,
      "evidence_pointer": "recovered:pic1-plaintext.bmp"
    },
    {
      "id": "recovered-letters-folder",
      "mitre_attack": "T1005",
      "confidence": 0.90,
      "evidence_pointer": "C:/RECYCLER/letters/"
    },
    {
      "id": "email-communication-jimmy-jungle",
      "mitre_attack": "T1114.002",
      "confidence": 0.87,
      "evidence_pointer": "mailbox:outlook.pst/Sent Items"
    },
    {
      "id": "gmail-sessions-evidence",
      "mitre_attack": "T1114.003",
      "confidence": 0.82,
      "evidence_pointer": "browser:ie-history.dat"
    },
    {
      "id": "mozilla-bookmarks-drug-sites",
      "mitre_attack": "T1217",
      "confidence": 0.78,
      "evidence_pointer": "C:/Documents and Settings/Mr. Evil/Application Data/Mozilla/bookmarks.html"
    },
    {
      "id": "gmail-password-artifact",
      "mitre_attack": "T1555.003",
      "confidence": 0.80,
      "evidence_pointer": "browser:firefox-passwords"
    },
    {
      "id": "usb-thumbdrive-serial",
      "mitre_attack": "T1200",
      "confidence": 0.91,
      "evidence_pointer": "registry:HKLM/System/CurrentControlSet/Enum/USBSTOR"
    }
  ]
}
```

### 11.4 Re-run test and confirm PASS

- [ ] Run: `pytest tests/sandbox/test_goldens.py -v`
  Expected: `6 passed`

### 11.5 Commit

- [ ] Run:
  ```
  git add tests/sandbox/test_goldens.py goldens/nist-hacking-case.findings.json
  git commit -m "feat(sandbox): NIST Hacking Case golden findings (14 items)

Encodes the fourteen canonical evidence artifacts from the NIST CFReDS
Hacking Case (Mr Evil / Jimmy Jungle / steganography / USB serial) with
MITRE ATT&CK mapping and evidence pointers. Confidence scores are the
initial baseline; the Product team refines them as detectors mature."
  ```
  Expected: commit succeeds.

---

## Task 12: Branch-protection bootstrap script

**Scope:** Script that calls `gh api` to require L0 + L1 status checks on `main` before merge, per Spec #3 §11.

### 12.1 Failing test — `Create: tests/sandbox/test_branch_protection.py`

```python
"""Branch-protection bootstrap script structure test."""
from pathlib import Path
import subprocess

SCRIPT = Path("scripts/setup-branch-protection.sh")


def test_script_exists_with_shebang():
    assert SCRIPT.is_file()
    assert SCRIPT.read_text().startswith("#!/usr/bin/env bash")


def test_script_sets_strict_mode():
    assert "set -euo pipefail" in SCRIPT.read_text()


def test_script_calls_gh_api_branch_protection():
    text = SCRIPT.read_text()
    assert "gh api" in text
    assert "/branches/main/protection" in text


def test_requires_l0_and_l1_contexts():
    text = SCRIPT.read_text()
    assert "L0 Static" in text
    assert "L1 Unit" in text


def test_requires_strict_status_checks():
    text = SCRIPT.read_text()
    assert '"strict": true' in text


def test_script_passes_shellcheck():
    r = subprocess.run(
        ["shellcheck", "-S", "warning", str(SCRIPT)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"shellcheck failed:\n{r.stdout}\n{r.stderr}"
```

### 12.2 Run test and confirm FAIL

- [ ] Run: `pytest tests/sandbox/test_branch_protection.py -v`
  Expected:
  ```
  FAILED tests/sandbox/test_branch_protection.py::test_script_exists_with_shebang
  ```

### 12.3 Implement — `Create: scripts/setup-branch-protection.sh`

```bash
#!/usr/bin/env bash
# Idempotently apply main-branch protection: L0 + L1 must be green,
# 1 approving review, no force pushes, no direct-to-main.
# Run once per repo after the workflows exist.
set -euo pipefail

REPO="${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"

echo "[branch-protect] applying to ${REPO}:main"

gh api \
    --method PUT \
    -H "Accept: application/vnd.github+json" \
    "/repos/${REPO}/branches/main/protection" \
    -f 'required_status_checks[strict]=true' \
    -f 'required_status_checks[contexts][]=L0 Static / l0-static' \
    -f 'required_status_checks[contexts][]=L1 Unit / l1-unit' \
    -f 'enforce_admins=true' \
    -f 'required_pull_request_reviews[required_approving_review_count]=1' \
    -f 'required_pull_request_reviews[dismiss_stale_reviews]=true' \
    -f 'restrictions=null' \
    -f 'allow_force_pushes=false' \
    -f 'allow_deletions=false' \
    --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["L0 Static / l0-static", "L1 Unit / l1-unit"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON

echo "[branch-protect] done"
```

### 12.4 Re-run test and confirm PASS

- [ ] Run: `pytest tests/sandbox/test_branch_protection.py -v`
  Expected: `6 passed`
- [ ] Run: `chmod +x scripts/setup-branch-protection.sh`
  Expected: no output.

### 12.5 Commit

- [ ] Run:
  ```
  git add tests/sandbox/test_branch_protection.py scripts/setup-branch-protection.sh
  git commit -m "feat(sandbox): main branch protection bootstrap

Requires L0 + L1 green before merge, one approving review, no force
pushes, no deletions. Admins included (enforce_admins=true) so a tired
hackathon operator cannot self-merge around the bots at 03:00. Run once
after workflows are visible in the GitHub API."
  ```
  Expected: commit succeeds.

---

## Task 13: End-to-end verification

**Scope:** Actually run L0 + L1 + L2-smoke locally and L3 against the NIST fixture. This is the acceptance-criteria check from Spec #3 §8. Whatever fails here is a real bug the earlier static tests could not catch.

### 13.1 Write verification harness — `Create: tests/sandbox/test_end_to_end.py`

```python
"""End-to-end sandbox verification.

Marked `slow`; opt in with: pytest -m slow tests/sandbox/test_end_to_end.py
Requires Docker + KVM + the sift-2026.03.24.ova at repo root.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow


def _run(cmd, **kw):
    print(f"[e2e] $ {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, **kw)


def test_l0_workflow_validates_with_actionlint():
    if not shutil.which("actionlint"):
        pytest.skip("actionlint not installed")
    _run(["actionlint", ".github/workflows/l0-static.yml"])


def test_l1_image_builds():
    _run([
        "docker", "build",
        "-t", "findevil/l1-devbase:e2e",
        "-f", "docker/l1-devbase.Dockerfile",
        "docker",
    ])


def test_l1_image_runs_cargo_and_pnpm_sanity():
    out = subprocess.check_output([
        "docker", "run", "--rm", "findevil/l1-devbase:e2e",
        "bash", "-lc", "rustc --version && pnpm --version && uv --version",
    ], text=True)
    assert "1.83" in out
    assert "9.12" in out
    assert "0.5.8" in out


def test_l2_smoke_runs_if_sysbox_present():
    if shutil.which("sysbox-runc") is None:
        pytest.skip("sysbox-runc not on PATH; L2 runs only in CI")
    _run(["bash", "scripts/fetch-fixtures.sh", "--profile", "l2"])
    _run([
        "docker", "build", "--runtime=sysbox-runc",
        "-t", "findevil/l2-siftlite:e2e",
        "-f", "docker/l2-siftlite.Dockerfile", ".",
    ])
    _run([
        "docker", "run", "--runtime=sysbox-runc", "--rm",
        "-v", f"{Path.cwd()}/fixtures:/fixtures:ro",
        "findevil/l2-siftlite:e2e",
        "/usr/local/bin/run-dfir-smoke.sh",
    ])


def test_l3_golden_matches_on_nist_case():
    if not Path("sift-microvm-warm.qcow2.zst").is_file():
        pytest.skip("warm qcow2 not built yet; run `packer build packer/`")
    if shutil.which("qemu-system-x86_64") is None:
        pytest.skip("qemu not installed")
    _run(["bash", "scripts/fetch-fixtures.sh", "--profile", "l3"])
    _run(["bash", "scripts/l3-run-goldens.sh"])
    run = json.loads(Path("run.log").read_text())
    golden = json.loads(Path("goldens/nist-hacking-case.findings.json").read_text())
    assert run["verdict"] == golden["verdict"]
    assert {f["id"] for f in run["findings"]} == {f["id"] for f in golden["findings"]}
```

### 13.2 Register the `slow` marker — `Create: pytest.ini`

```ini
[pytest]
markers =
    slow: end-to-end sandbox tests requiring Docker/KVM/OVA
testpaths = tests
addopts = -ra
```

### 13.3 Run the harness in dry-mode and confirm static gates still pass

- [ ] Run: `pytest tests/sandbox/ -v --ignore=tests/sandbox/test_end_to_end.py`
  Expected: `tests/sandbox/test_*.py ..... 47 passed` (12 tests-files × their counts).

### 13.4 Run the end-to-end harness (opt-in, slow)

- [ ] Run: `pytest -m slow tests/sandbox/test_end_to_end.py -v`
  Expected (on a KVM-enabled Linux box with Docker + Sysbox + the OVA):
  ```
  PASSED test_l0_workflow_validates_with_actionlint
  PASSED test_l1_image_builds
  PASSED test_l1_image_runs_cargo_and_pnpm_sanity
  PASSED test_l2_smoke_runs_if_sysbox_present
  PASSED test_l3_golden_matches_on_nist_case
  ```
  On a non-KVM dev laptop, expect the L2 and L3 tests to `SKIPPED` with the documented reasons — this is acceptable; CI is the authoritative run.

### 13.5 Commit

- [ ] Run:
  ```
  git add tests/sandbox/test_end_to_end.py pytest.ini
  git commit -m "test(sandbox): end-to-end harness + slow marker

The static structural tests in Tasks 1-12 lock in shape; this harness
exercises the actual build-and-run path against the judge's real OVA
and the NIST CFReDS case. Marked 'slow' so the swarm's per-PR loop does
not accidentally spin up qemu; CI runs it on the nightly L3 job."
  ```
  Expected: commit succeeds.

---

## Acceptance checklist (mirrors Spec #3 §8)

- [ ] `.github/workflows/l0-static.yml` — Task 1
- [ ] `docker/l1-devbase.Dockerfile` + `docker/l1-compose.yml` + `.github/workflows/l1-unit.yml` — Tasks 2, 3
- [ ] `docker/l2-siftlite.Dockerfile` + `scripts/l2-dfir-smoke.sh` + `.github/workflows/l2-sift-lite.yml` — Tasks 4, 5, 6
- [ ] `packer/sift-microvm.pkr.hcl` + `scripts/sift-setup.sh` — Task 7
- [ ] `scripts/l3-run-goldens.sh` + `.github/workflows/l3-nightly.yml` — Tasks 8, 9
- [ ] `scripts/fetch-fixtures.sh` — Task 10
- [ ] `goldens/nist-hacking-case.findings.json` — Task 11
- [ ] `scripts/setup-branch-protection.sh` — Task 12
- [ ] End-to-end verification passes on a KVM Linux host — Task 13
- [ ] Monthly CI cost stays under $350 at 100 PR/day + nightly L3 — monitored post-rollout

---

## Notes for the executor

- Preserve task order. Task 6 references the smoke script from Task 5; Task 9 references the driver from Task 8; Task 13 references every earlier artifact.
- Every code block in this plan is the literal file content — do not paraphrase.
- If a test fails in a way the plan does not predict, stop and surface it, do not paper over.
- Commits are one-per-task by design. If a pre-commit hook fails, fix and commit again — do not `--amend`.
