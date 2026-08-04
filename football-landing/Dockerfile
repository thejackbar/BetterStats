# bs-football-landing — the betterat.football umbrella landing page.
# Static only, built from the repo so the messaging/layout evolves through the
# normal git flow (edit football-landing/html/, push to main, rebuild).
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY html/ /usr/share/nginx/html/
