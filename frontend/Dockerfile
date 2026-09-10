# Frontend image: Next.js standalone output (see next.config.mjs).
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund


FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# BACKEND_INTERNAL_URL is read at request time, not build time; a placeholder keeps the build
# from failing while guaranteeing the real value is never baked into the image.
ENV BACKEND_INTERNAL_URL=http://backend:8000
RUN npm run build


FROM node:22-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production PORT=3000

RUN useradd --create-home --uid 10001 eka
COPY --from=builder --chown=eka:eka /app/.next/standalone ./
COPY --from=builder --chown=eka:eka /app/.next/static ./.next/static
COPY --from=builder --chown=eka:eka /app/public ./public

USER eka
EXPOSE 3000
CMD ["node", "server.js"]
