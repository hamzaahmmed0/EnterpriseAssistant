/**
 * Next.js configuration.
 *
 * The browser never talks to the backend, Qdrant, or the LLM directly: every call is made
 * server-side with the caller's session. BACKEND_INTERNAL_URL is deliberately NOT exposed here --
 * putting it in `env` would inline it into client bundles.
 */

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Standalone output keeps the Docker runtime stage small (see frontend/Dockerfile).
  output: "standalone",
  experimental: {
    serverActions: {
      // Contract uploads travel through a server action, so the action body limit has to clear
      // CONTRACT_MAX_UPLOAD_MB. Keep these two in step.
      bodySizeLimit: "12mb",
    },
  },
};

export default nextConfig;
