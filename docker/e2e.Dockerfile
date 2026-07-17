FROM mcr.microsoft.com/playwright:v1.61.1-noble

ENV PNPM_HOME=/pnpm \
    NODE_USE_ENV_PROXY=1
ENV PATH=$PNPM_HOME:$PATH

WORKDIR /workspace

RUN corepack enable && corepack prepare pnpm@11.14.0 --activate

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web-vue/package.json apps/web-vue/package.json

RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm config set store-dir /pnpm/store \
    && pnpm install --frozen-lockfile

COPY apps/web-vue apps/web-vue

CMD ["pnpm", "--dir", "apps/web-vue", "test"]
