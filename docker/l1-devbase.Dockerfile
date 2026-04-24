# Spec #3 §4.2 — L1 dev-base image.
# Matches SIFT's Ubuntu 22.04 base so CI + L3 golden-run Product
# environments are byte-compatible where it matters.
#
# Budget: 2-5min build; <5min L1 test cycle.
# Blocks PR merge via .github/workflows/l1-unit.yml.

# hadolint ignore=DL3007
FROM ubuntu:22.04

# Ensure deterministic apt behavior.
ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH=/root/.cargo/bin:/root/.fnm:/root/.local/bin:${PATH}

# System deps matching BUILD_PLAN_v2.md §10 week-1 skeleton + Spec #2 §4.1
# (rmcp + evtx + duckdb) + Spec #2 §4.2 (Python agent with sigstore/OTS).
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    git \
    pkg-config \
    libssl-dev \
    libclang-dev \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    libyara-dev \
    libewf-dev \
    libafflib-dev \
    libfuse-dev \
    sleuthkit \
    postgresql-client \
    xz-utils \
    zstd \
    unzip \
    jq \
 && rm -rf /var/lib/apt/lists/* \
 && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
 && ln -sf /usr/bin/python3.11 /usr/bin/python

# Rust 1.83 (pinned — specs use stable feature surface available in 1.83).
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y \
        --default-toolchain 1.83.0 \
        --profile minimal \
        --component clippy,rustfmt \
 && /root/.cargo/bin/rustup --version \
 && /root/.cargo/bin/cargo --version

# Node 20 via fnm + pnpm 9.12.0 via corepack.
RUN curl -fsSL https://fnm.vercel.app/install | bash -s -- --install-dir /root/.fnm --skip-shell \
 && /root/.fnm/fnm install 20 \
 && /root/.fnm/fnm default 20 \
 && ln -sf /root/.fnm/aliases/default/bin/node /usr/local/bin/node \
 && ln -sf /root/.fnm/aliases/default/bin/npm  /usr/local/bin/npm \
 && ln -sf /root/.fnm/aliases/default/bin/npx  /usr/local/bin/npx \
 && corepack enable \
 && corepack prepare pnpm@9.12.0 --activate \
 && ln -sf "$(corepack --prefix /usr/local prepare pnpm@9.12.0 --activate 2>/dev/null; readlink -f $(command -v pnpm) 2>/dev/null || command -v pnpm)" /usr/local/bin/pnpm || true \
 && node --version \
 && pnpm --version

# Python packaging: uv for env+lockfile (matches CLAUDE.md conventions).
# Pinned per https://astral.sh/uv release notes around the plan date.
RUN pip install --no-cache-dir 'uv==0.5.8' \
 && uv --version

# Non-root build user. Anything that runs evidence-adjacent must be non-root.
ARG DEV_UID=1000
ARG DEV_GID=1000
RUN groupadd --gid "${DEV_GID}" dev \
 && useradd --uid "${DEV_UID}" --gid "${DEV_GID}" --create-home --shell /bin/bash dev \
 && mkdir -p /workspace \
 && chown -R dev:dev /workspace /root/.cargo /root/.fnm || true

WORKDIR /workspace

# Healthcheck proves every toolchain is invocable.
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD rustc --version >/dev/null \
   && cargo --version >/dev/null \
   && python3.11 --version >/dev/null \
   && uv --version >/dev/null \
   && node --version >/dev/null \
   && pnpm --version >/dev/null \
   || exit 1

# Default: print toolchain versions, then drop to a shell if overridden.
CMD ["bash", "-lc", "echo 'L1 devbase — toolchains:' && rustc --version && python3.11 --version && uv --version && node --version && pnpm --version"]
