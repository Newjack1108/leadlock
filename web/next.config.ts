import type { NextConfig } from "next";

const apiProxyTarget = process.env.API_PROXY_TARGET || process.env.NEXT_PUBLIC_API_URL || "";

const nextConfig: NextConfig = {
  async redirects() {
    return [
      {
        source: "/favicon.ico",
        destination: "/icon.png",
        permanent: false,
      },
    ];
  },
  async rewrites() {
    // Proxy frontend /api calls to FastAPI in production.
    // Keep disabled when target is missing or already a relative path.
    if (!apiProxyTarget || apiProxyTarget.startsWith("/")) {
      return [];
    }
    return [
      {
        source: "/api/:path*",
        destination: `${apiProxyTarget.replace(/\/+$/, "")}/api/:path*`,
      },
    ];
  },
  images: {
    unoptimized: false,
    // Increase image size limit for large logos
    imageSizes: [16, 32, 48, 64, 96, 128, 256, 384],
    deviceSizes: [640, 750, 828, 1080, 1200, 1920, 2048, 3840],
  },
};

export default nextConfig;
