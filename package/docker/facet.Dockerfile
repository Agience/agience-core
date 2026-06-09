# /docker/facet.Dockerfile
# Build context is the repo root (see compose/docker-compose.yml context: ..)
# Stage 1: Build
FROM node:20-alpine AS builder

ARG GIT_SHA=
ENV GIT_SHA=$GIT_SHA

RUN apk add --no-cache python3 && ln -sf /usr/bin/python3 /usr/bin/python

WORKDIR /workspace

# Copy package files first for better layer caching
COPY src/facet/package*.json src/facet/

WORKDIR /workspace/src/facet
RUN npm ci

# Copy source files needed for the build. Destinations mirror the repo layout
# (src/facet, src/chorus, package/types, build_info.json at root) so the
# repo-relative paths in vite.config.ts — ../../build_info.json, package/types,
# ../chorus — resolve identically in Docker and in local dev.
WORKDIR /workspace
COPY build_info.json build_info.json
COPY src/facet/ src/facet/
COPY src/chorus/ src/chorus/
COPY package/types/ package/types/

WORKDIR /workspace/src/facet
RUN npm run build

# Stage 2: Serve with nginx
FROM nginx:alpine

COPY --from=builder /workspace/src/facet/dist /usr/share/nginx/html
COPY src/facet/nginx.conf /etc/nginx/conf.d/default.conf
COPY package/docker/facet-runtime-config.sh /docker-entrypoint.d/40-runtime-config.sh

RUN chmod +x /docker-entrypoint.d/40-runtime-config.sh

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
