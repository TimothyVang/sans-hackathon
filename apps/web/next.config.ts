import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The dashboard reads audit JSONL from absolute filesystem paths
  // passed via `?case=` query string. No outbound network required at
  // runtime; everything is local to the host running Claude Code +
  // the case directory.
};

export default nextConfig;
