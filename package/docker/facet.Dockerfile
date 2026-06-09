# /docker/facet.Dockerfile
# Build context is the repo root (see compose/docker-compose.yml context: ..)
# Stage 1: Build
FROM node:20-alpine AS builder

ARG GIT_SHA=
ENV GIT_SHA=$GIT_SHA

RUN apk add --no-cache python3 && ln -sf /usr/bin/python3 /usr/bin/python

WORKDIR /workspace

# Copy package files first for better layer caching
COPY src/facet/package*.json facet/

WORKDIR /workspace/facet
RUN npm ci

# Copy source files needed for the build
WORKDIR /workspace
COPY build_info.json build_info.json
COPY src/facet/ facet/
COPY src/chorus/ chorus/
COPY package/types/ types/

WORKDIR /workspace/facet
RUN npm run build

# Stage 2: Serve with nginx
FROM nginx:alpine

COPY --from=builder /workspace/facet/dist /usr/share/nginx/html
COPY src/facet/nginx.conf /etc/nginx/conf.d/default.conf
COPY package/docker/facet-runtime-config.sh /docker-entrypoint.d/40-runtime-config.sh

RUN chmod +x /docker-entrypoint.d/40-runtime-config.sh

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
