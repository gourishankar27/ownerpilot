import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@ownerpilot/contracts", "@ownerpilot/ui"],
  serverExternalPackages: ["pg"],
};

export default nextConfig;
