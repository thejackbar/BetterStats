FROM node:20-alpine AS builder

# Multi-sport build args (docs/afl-betterstats-plan.md). Defaults reproduce the
# cricket build byte-for-byte; the AFL silo (bs-afl-frontend) builds with
#   --build-arg VITE_SPORT=afl --build-arg VITE_BASE=/afl/ \
#   --build-arg NGINX_CONF=nginx.afl.conf --build-arg WEB_ROOT=/usr/share/nginx/html/afl
# (VITE_BASE = the path prefix the app lives under on the umbrella domain;
#  WEB_ROOT places the built files at that same prefix inside the image.)
ARG VITE_SPORT=cricket
ARG VITE_BASE=

# BetterScout is a separate PRODUCT, not another sport (see App.jsx's
# VITE_PRODUCT check) — the bs-scout-frontend silo builds with
#   --build-arg VITE_PRODUCT=scout --build-arg VITE_BASE=/betterscout/ \
#   --build-arg NGINX_CONF=nginx.scout.conf --build-arg WEB_ROOT=/usr/share/nginx/html/betterscout
ARG VITE_PRODUCT=cricket

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
ENV VITE_SPORT=$VITE_SPORT
ENV VITE_BASE=$VITE_BASE
ENV VITE_PRODUCT=$VITE_PRODUCT
RUN npm run build

FROM nginx:alpine
ARG NGINX_CONF=nginx.conf
ARG WEB_ROOT=/usr/share/nginx/html
COPY --from=builder /app/dist $WEB_ROOT
COPY $NGINX_CONF /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
