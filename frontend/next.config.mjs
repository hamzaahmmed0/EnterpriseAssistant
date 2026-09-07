/**
 * Next.js configuration.
 *
 * The browser never talks to the backend, Qdrant, or the LLM directly: every call is made
 * server-side with the caller session. Keep BACKEND_INTERNAL_URL out of NEXT_PUBLIC_*.
 */

// TODO: set reactStrictMode and the server-side env passthrough for BACKEND_INTERNAL_URL.
// TODO: decide output mode ("standalone" if the Docker image copies a minimal server bundle).
// TODO: add the file-size limit for contract uploads if a route handler proxies them.

/** @type {import('next').NextConfig} */
const nextConfig = {};

export default nextConfig;
