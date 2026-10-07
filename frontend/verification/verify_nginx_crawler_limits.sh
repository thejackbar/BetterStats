#!/bin/bash
# Wire-level checks for frontend/nginx.conf: robots, noindex, scraper refusal and
# per-visitor rate limiting on player profiles (v9.106.38). Runs the REAL config
# in a throwaway nginx against a stub backend; nothing touches the live site.
#
#   bash frontend/verification/verify_nginx_crawler_limits.sh
#   NGINX_CONF=/path/to/older/nginx.conf bash ...   # CONTROL RUN: the new-behaviour
#                                                   # checks must fail, the controls pass
#
# Needs: nginx, python3, curl, and the hostname betterstats-backend pointing at
# 127.0.0.1 (the script adds it to /etc/hosts when it can). Run as root, or make
# the temp dir readable to nginx's worker user.
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
CONF="${NGINX_CONF:-$HERE/nginx.conf}"
PORT="${PORT:-8081}"
T="$(mktemp -d)"; LOGDIR="$T/logs"; mkdir -p "$T/root/assets" "$LOGDIR"
: > "$LOGDIR/ratelimit.log"   # the older config never writes it; absent must read as "no entries", not crash
cp "$HERE/public/robots.txt" "$T/root/robots.txt"
printf '<!doctype html><div id="root"></div>' > "$T/root/index.html"
echo "console.log(1)" > "$T/root/assets/a.js"
grep -q betterstats-backend /etc/hosts || echo "127.0.0.1 betterstats-backend" >> /etc/hosts
# the config logs to the image's /var/log/nginx; point it at the temp dir
sed "s#listen 80;#listen $PORT;#; s#root /usr/share/nginx/html;#root $T/root;#; s#/var/log/nginx/#$LOGDIR/#g" "$CONF" > "$T/site.conf"
cat > "$T/stub.py" <<'PYEOF'
import http.server, json
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"path": self.path, "ua": self.headers.get("user-agent")}).encode()
        self.send_response(200); self.send_header("content-type","application/json"); self.send_header("content-length",str(len(body))); self.end_headers(); self.wfile.write(body)
    do_POST = do_GET
    def log_message(self,*a): pass
http.server.ThreadingHTTPServer(("127.0.0.1",8000),H).serve_forever()
PYEOF
cat > "$T/nginx.conf" <<EOF
user root;
worker_processes 1; pid $T/nginx.pid; error_log $LOGDIR/error.log warn;
events { worker_connections 256; }
http { include /etc/nginx/mime.types; log_format main '\$remote_addr \$request \$status';
  client_body_temp_path $T/t1; proxy_temp_path $T/t2; fastcgi_temp_path $T/t3; uwsgi_temp_path $T/t4; scgi_temp_path $T/t5;
  include $T/site.conf; }
EOF
python3 "$T/stub.py" & STUB=$!
cleanup(){ nginx -c "$T/nginx.conf" -s stop 2>/dev/null; kill $STUB 2>/dev/null; }
trap cleanup EXIT
nginx -t -c "$T/nginx.conf" || exit 2
nginx -c "$T/nginx.conf"; sleep 1
# let the limiter's buckets start empty
sleep 14
B=localhost:$PORT; T_H=$(mktemp); T_B=$(mktemp); T_C=$(mktemp); pass=0; fail=0
ok(){ if [ "${2-}" = "${3-}" ]; then echo "PASS $1"; pass=$((pass+1)); else echo "FAIL $1 (got '${3-}', want '$2')"; fail=$((fail+1)); fi; }
code(){ curl -s -o /dev/null -w "%{http_code}" "$@"; }
hdr(){ curl -s -D - -o /dev/null "$@" | tr -d '\r' | tr 'A-Z' 'a-z'; }
NOIDX="noindex, nofollow, noarchive, nosnippet, noimageindex"

echo "--- robots.txt"
R=$(curl -s $B/robots.txt)
ok "robots disallows /players/" 1 $(echo "$R" | grep -c '^Disallow: /players/$')
ok "robots still allows /"        1 $(echo "$R" | grep -c '^Allow: /$')
ok "robots lists sitemap"          1 $(echo "$R" | grep -c '^Sitemap:')

echo "--- profile page"
ok "profile page serves the SPA (200)" 200 $(code $B/players/abc-123)
ok "profile page has X-Robots-Tag"     "x-robots-tag: $NOIDX" "$(hdr $B/players/abc-123 | grep -i '^x-robots-tag')"
ok "profile body is the app shell"     1 $(curl -s $B/players/abc-123 | grep -c 'id="root"')
ok "profile sub-route (share) also noindex" "x-robots-tag: $NOIDX" "$(hdr $B/players/abc-123/share | grep -i '^x-robots-tag')"
ok "control: marketing page has NO X-Robots-Tag" 0 $(hdr $B/pricing | grep -ci '^x-robots-tag')
ok "control: marketing page serves (200)" 200 $(code $B/pricing)
ok "control: a hashed asset still serves" 200 $(code $B/assets/a.js)

echo "--- AI scrapers on profiles"
for ua in GPTBot ClaudeBot PerplexityBot CCBot Bytespider Amazonbot Meta-ExternalAgent Scrapy/2.11; do
  ok "$ua refused on /players/" 403 $(code -A "Mozilla/5.0 (compatible; $ua/1.0)" $B/players/abc-123)
  ok "$ua refused on /api/players/" 403 $(code -A "Mozilla/5.0 (compatible; $ua/1.0)" $B/api/players/abc-123/stats)
done
ok "control: GPTBot still gets a marketing page (prerender to backend)" 200 $(code -A "GPTBot/1.0" $B/pricing)
ok "control: Googlebot UA is NOT blocked by the scraper map" 200 $(code -A "Mozilla/5.0 (compatible; Googlebot/2.1)" $B/players/abc-123)
ok "link preview bot still gets a card (rewritten to og-preview)" 1 $(curl -s -A "facebookexternalhit/1.1" $B/players/abc-123 | grep -c 'og-preview')

echo "--- player API proxying"
ok "api path rewritten (strips /api, keeps query)" "/players/abc-123/stats?x=1" "$(curl -s "$B/api/players/abc-123/stats?x=1" | python3 -c 'import sys,json;print(json.load(sys.stdin)["path"])')"
ok "bare /api/players is not 301'd" 200 $(code $B/api/players)
ok "POST /api/players keeps its body path (no 301)" 200 $(code -X POST -d x=1 $B/api/players)
ok "player API has X-Robots-Tag" "x-robots-tag: $NOIDX" "$(hdr $B/api/players/abc-123 | grep -i '^x-robots-tag')"
ok "control: other API still proxies" 200 $(code $B/api/organisations/x)

echo "--- rate limiting (per client key = last X-Forwarded-For)"
n429(){ local ip=$1 path=$2 n=$3 c=0; for i in $(seq 1 $n); do [ "$(code -H "X-Forwarded-For: $ip" $B$path)" = 429 ] && c=$((c+1)); done; echo $c; }
A=$(n429 203.0.113.10 /api/players/abc-123/stats 120)
ok "a script hammering profile data is throttled (>0 of 120 are 429)" 1 $([ "$A" -gt 0 ] && echo 1 || echo 0); echo "     429s: $A of 120"
ok "...and is cut off for a while (immediate next request is 429)" 429 $(code -H "X-Forwarded-For: 203.0.113.10" $B/api/players/abc-123/stats)
ok "a DIFFERENT visitor is unaffected at the same moment" 200 $(code -H "X-Forwarded-For: 198.51.100.7" $B/api/players/abc-123/stats)
ok "a person loading one profile (12 calls) is never throttled" 0 $(n429 198.51.100.8 /api/players/abc-123/stats 12)
NH=0; for i in $(seq 1 120); do [ "$(code $B/api/players/abc-123/stats)" = 429 ] && NH=$((NH+1)); done
ok "FAIL-OPEN: no X-Forwarded-For => nothing counted (0 of 120 throttled)" 0 $NH
P=$(n429 203.0.113.11 /players/abc-123 120)
ok "page route throttled too (>0 of 120)" 1 $([ "$P" -gt 0 ] && echo 1 || echo 0); echo "     429s: $P of 120"
G=$(n429 203.0.113.12 /api/organisations/x 150)
ok "general API throttled at its higher ceiling (>0 of 150)" 1 $([ "$G" -gt 0 ] && echo 1 || echo 0); echo "     429s: $G of 150"
ok "general API: a normal burst of 30 is fine" 0 $(n429 198.51.100.9 /api/organisations/x 30)

echo "--- writes are not limited; 429 is readable"
W=0; for i in $(seq 1 100); do [ "$(code -X PATCH -H "X-Forwarded-For: 203.0.113.50" -d x=1 $B/api/players/abc-$i/profile)" = 429 ] && W=$((W+1)); done
ok "bulk PATCH of 100 players from one visitor: none throttled" 0 $W
ok "control: the same visitor's READS are throttled" 1 $([ "$(n429 203.0.113.51 /api/players/abc-123/stats 150)" -gt 0 ] && echo 1 || echo 0)
ok "a squad's worth of parallel stats reads (50 at once) is not throttled" 0 $(seq 1 50 | xargs -P 50 -I{} curl -s -o /dev/null -w "%{http_code}\n" -H "X-Forwarded-For: 198.51.100.60" $B/api/players/abc-{}/stats | grep -c 429)
# hammer until the first 429, capture status, headers and body from that same response
for i in $(seq 1 300); do curl -s -D $T_H -o $T_B -w "%{http_code}" -H "X-Forwarded-For: 203.0.113.52" $B/api/players/abc-1/stats > $T_C; [ "$(cat $T_C)" = 429 ] && break; done
ok "throttled API reply is status 429" 429 "$(cat $T_C)"
ok "throttled API reply is JSON with a detail message" 1 $(python3 -c 'import json,sys;print(1 if "detail" in json.load(open(sys.argv[1])) else 0)' $T_B 2>/dev/null || echo 0)
ok "throttled API reply carries Retry-After" 1 $(tr -d '\r' < $T_H | tr 'A-Z' 'a-z' | grep -c '^retry-after')

echo "--- the visitor key cannot be spoofed by the visitor"
SP=0; for i in $(seq 1 150); do [ "$(code -H "X-Forwarded-For: 9.9.9.$i, 203.0.113.70" $B/api/players/abc-1/stats)" = 429 ] && SP=$((SP+1)); done
ok "rotating a fake FIRST X-Forwarded-For does not evade (same real peer last): throttled" 1 $([ $SP -gt 0 ] && echo 1 || echo 0)
CFV=0; for i in $(seq 1 150); do [ "$(code -H "X-Forwarded-For: 203.0.113.71" -H "CF-Connecting-IP: 8.8.8.$i" $B/api/players/abc-1/stats)" = 429 ] && CFV=$((CFV+1)); done
ok "a faked CF-Connecting-IP is ignored (not Cloudflare): throttled" 1 $([ $CFV -gt 0 ] && echo 1 || echo 0)
ok "control: a different real peer is unaffected meanwhile" 200 $(code -H "X-Forwarded-For: 1.1.1.1, 198.51.100.77" $B/api/players/abc-1/stats)
ok "IPv6 peer counts as its own visitor" 200 $(code -H "X-Forwarded-For: 2001:db8::1" $B/api/players/abc-1/stats)
LOG=$LOGDIR/ratelimit.log
ok "throttle log names the counted key (the real peer, not the spoofed ones)" 1 $([ $(grep -c 'player_key="203.0.113.70"' $LOG) -gt 0 ] && echo 1 || echo 0)
ok "throttle log never contains a spoofed first-hop address" 0 $(grep -c 'key="9.9.9.' $LOG)
ok "throttle log holds only 429s" 0 $(grep -vc 'status=429' $LOG)
echo; echo "$pass passed, $fail failed"; [ $fail = 0 ]
