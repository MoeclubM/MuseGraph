FROM mirror.gcr.io/library/node:20-alpine AS builder

WORKDIR /app

# Copy workspace root files needed for pnpm install
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web-vue/package.json apps/web-vue/package.json

RUN corepack enable && pnpm install --frozen-lockfile --filter @musegraph/web... || pnpm install --filter @musegraph/web...

COPY apps/web-vue/ apps/web-vue/
RUN cd apps/web-vue && pnpm build

FROM mirror.gcr.io/library/nginx:alpine
COPY --from=builder /app/apps/web-vue/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
