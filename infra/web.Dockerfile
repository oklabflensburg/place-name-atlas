FROM node:22.22.1-bookworm-slim@sha256:4f77a690f2f8946ab16fe1e791a3ac0667ae1c3575c3e4d0d4589e9ed5bfaf3d AS build
RUN npm install -g pnpm@12.14.0
WORKDIR /app
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/api-client packages/api-client
COPY apps/web apps/web
COPY scripts/build.mjs scripts/local-runtime.mjs scripts/
COPY infra/local.json infra/local.json
RUN pnpm install --frozen-lockfile && pnpm build
FROM node:22.22.1-bookworm-slim@sha256:4f77a690f2f8946ab16fe1e791a3ac0667ae1c3575c3e4d0d4589e9ed5bfaf3d
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3000
WORKDIR /app
COPY --from=build --chown=node:node /app/apps/web/.output .output
USER node
CMD ["node", "--max-http-header-size=65536", ".output/server/index.mjs"]
