#!/usr/bin/env bash
# The teaser pictures are API responses that end in .png. nginx tries regex
# locations before the `location /api/` prefix, so the static-image rule used to
# answer /api/public/teaser/<token>/image/<fmt>.png from disk with nginx's own
# 404. This runs the real frontend/nginx.conf in front of a stub backend and
# checks the request reaches the backend, a normal static image is still served
# from disk, and an unknown token gets the BACKEND's 404 (JSON), not nginx's.
#
#   sudo apt-get install -y nginx-light   # once
#   bash frontend/verification/verify_nginx_api_image_routes.sh [conf]   # default frontend/nginx.conf
#
# Control: run it with `git show <old commit>:frontend/nginx.conf > /tmp/old.conf`
# as the argument; the first check must fail.
set -u
CONF=${1:-$(dirname "$0")/../nginx.conf}
D=$(mktemp -d); trap 'nginx -s stop -c $D/main.conf 2>/dev/null; kill $STUB 2>/dev/null; rm -rf $D' EXIT
grep -q betterstats-backend /etc/hosts || echo "127.0.0.1 betterstats-backend" >> /etc/hosts
cat > $D/stub.py <<'PY'
import http.server
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        ok = self.path.startswith('/public/teaser/TOKENTOKEN1/image/card.png') or self.path.startswith('/public/teaser/TOKENTOKEN1/crest.png')
        self.send_response(200 if ok else 404)
        self.send_header('Content-Type', 'image/png' if ok else 'application/json'); self.end_headers()
        self.wfile.write(b'PNG' if ok else b'{"detail":"backend 404"}')
    def log_message(self, *a): pass
http.server.HTTPServer(('127.0.0.1', 8000), H).serve_forever()
PY
python3 $D/stub.py & STUB=$!
mkdir -p /usr/share/nginx/html; echo -n x > /usr/share/nginx/html/verify-probe.png
sed 's/listen 80;/listen 8093;/' "$CONF" > $D/srv.conf
cat > $D/main.conf <<EOC
pid $D/n.pid; error_log $D/err; events {}
http { access_log off; include /etc/nginx/mime.types; client_body_temp_path $D/t1; proxy_temp_path $D/t2; fastcgi_temp_path $D/t3; uwsgi_temp_path $D/t4; scgi_temp_path $D/t5; include $D/srv.conf; }
EOC
nginx -c $D/main.conf && sleep 1
pass=0; fail=0
ck(){ if [ "$2" = "$3" ]; then pass=$((pass+1)); echo "PASS $1"; else fail=$((fail+1)); echo "FAIL $1 (got '$2', want '$3')"; fi; }
ck "a teaser picture URL reaches the backend and is served" "$(curl -s -o /dev/null -w '%{http_code} %{content_type}' localhost:8093/api/public/teaser/TOKENTOKEN1/image/card.png)" "200 image/png"
ck "a kept club crest URL reaches the backend and is served" "$(curl -s -o /dev/null -w '%{http_code} %{content_type}' 'localhost:8093/api/public/teaser/TOKENTOKEN1/crest.png?v=abc')" "200 image/png"
ck "an unknown token gets the backend's JSON 404" "$(curl -s localhost:8093/api/public/teaser/NOPENOPE1/image/card.png)" '{"detail":"backend 404"}'
ck "an ordinary static .png is still served from disk" "$(curl -s -o /dev/null -w '%{http_code}' localhost:8093/verify-probe.png)" "200"
ck "a static .png that does not exist is nginx's 404" "$(curl -s -o /dev/null -w '%{http_code}' localhost:8093/no-such-file.png)" "404"
rm -f /usr/share/nginx/html/verify-probe.png
echo; echo "$pass passed, $fail failed"; exit $((fail>0))
