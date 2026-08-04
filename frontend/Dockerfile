FROM node:20-alpine AS builder

# Multi-sport build args (docs/afl-betterstats-plan.md). Defaults reproduce the
# cricket build byte-for-byte; the AFL silo (bs-afl-frontend) builds with
#   --build-arg VITE_SPORT=afl --build-arg NGINX_CONF=nginx.afl.conf
ARG VITE_SPORT=cricket

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
ENV VITE_SPORT=$VITE_SPORT
RUN npm run build

FROM nginx:alpine
ARG NGINX_CONF=nginx.conf
COPY --from=builder /app/dist /usr/share/nginx/html
COPY $NGINX_CONF /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
