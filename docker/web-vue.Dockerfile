FROM mirror.gcr.io/library/node:20-alpine AS builder

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web-vue/package.json apps/web-vue/package.json
COPY packages/ai-adapters/package.json packages/ai-adapters/package.json
COPY packages/shared/package.json packages/shared/package.json

RUN pnpm install --frozen-lockfile

COPY apps/web-vue apps/web-vue
COPY packages packages

RUN pnpm --dir apps/web-vue build


FROM mirror.gcr.io/library/nginx:alpine

COPY --from=builder /app/apps/web-vue/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
