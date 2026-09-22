# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS build
RUN corepack enable
WORKDIR /repo
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY packages packages
COPY apps/web/package.json apps/web/
RUN pnpm install --frozen-lockfile --filter @sm/web...
COPY apps/web apps/web
ARG NEXT_PUBLIC_WS_URL=ws://localhost:8080/ws
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL NEXT_TELEMETRY_DISABLED=1
RUN pnpm --filter @sm/web build

FROM node:22-alpine
RUN corepack enable
WORKDIR /repo
COPY --from=build /repo /repo
WORKDIR /repo/apps/web
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
USER node
EXPOSE 3000
CMD ["pnpm", "start"]
