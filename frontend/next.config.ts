import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Produces a minimal server bundle — used by the frontend Dockerfile.
  output: "standalone",
};

export default nextConfig;
