# syntax=docker/dockerfile:1.7
FROM node:22-alpine
RUN corepack enable
WORKDIR /repo
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY packages/config/package.json packages/config/
COPY apps/gateway/package.json apps/gateway/
RUN pnpm install --frozen-lockfile --filter @sm/gateway...
COPY packages/config packages/config
COPY apps/gateway apps/gateway
WORKDIR /repo/apps/gateway
USER node
EXPOSE 8080
CMD ["node", "--import", "tsx", "src/index.ts"]
