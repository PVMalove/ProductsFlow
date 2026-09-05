#!/usr/bin/env bash
# Gateway smoke test (issue #292) — a lightweight curl-based, automated
# re-verification that routing, rate limiting and header hardening
# (issues #284/#285/#286) actually work end-to-end against a real running
# dev-profile stack, through http://localhost:8080 only. Separate seam from
# backend/tests/e2e/ (that suite stays scoped to the E2E-only gateway per
# ADR 0004/0013) — this one exercises backend/infra/gateway/nginx.conf, the
# gateway that dev/prod actually use.
#
# Usage: bash backend/infra/gateway/smoke_test.sh
#
# WARNING: this tears down and recreates the local dev-profile gateway
# stack (docker-compose.yml + docker-compose.dev.yml) to run against a
# fresh instance, and stops it again on exit. It does not remove volumes.
#
# Requires: docker compose, curl, a backend/.env (see .env.example).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$BACKEND_DIR"

COMPOSE_DEV=(docker compose -f docker-compose.yml -f docker-compose.dev.yml)
COMPOSE_PROD=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
GATEWAY_URL="http://localhost:8080"
# Exact literal from nginx.conf's catch-all location — fragile to incidental
# whitespace/ordering changes there, but there's no jq dependency here, and
# an exact match is the strongest signal that a response came from nginx's
# own 404 rather than a service-level one.
GATEWAY_404_BODY='{"error": {"code": "NOT_FOUND", "message": "Endpoint not found"}}'
RATE_LIMIT_MARKER='"code": "TOO_MANY_REQUESTS"'

FAILURES=0
TMP_DIR="$(mktemp -d)"

section() { printf '\n== %s ==\n' "$1"; }
ok()      { printf '  [OK]   %s\n' "$1"; }
bad()     { printf '  [FAIL] %s\n' "$1"; FAILURES=$((FAILURES + 1)); }

cleanup() {
  rm -rf "$TMP_DIR"
  section "Teardown"
  # Unconditional: even a stack that failed to become healthy (e.g. gateway
  # rejected a broken nginx.conf) can leave sibling containers — dbs,
  # identity/catalog/support-api — running, and `down` on an already-down
  # project is a harmless no-op.
  "${COMPOSE_DEV[@]}" down >/dev/null 2>&1
  ok "dev stack stopped"
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
section "Structural checks: docker compose config + nginx -t"
# ---------------------------------------------------------------------------
if "${COMPOSE_DEV[@]}" config -q; then
  ok "docker compose config (dev overlay)"
else
  bad "docker compose config (dev overlay)"
fi

if "${COMPOSE_PROD[@]}" config -q; then
  ok "docker compose config (prod overlay)"
else
  bad "docker compose config (prod overlay)"
fi

# ---------------------------------------------------------------------------
section "Bringing up a fresh dev stack"
# ---------------------------------------------------------------------------
"${COMPOSE_DEV[@]}" down >/dev/null 2>&1
if "${COMPOSE_DEV[@]}" up -d --build --wait gateway identity-api catalog-api support-api; then
  ok "dev stack is up and healthy"
else
  bad "dev stack failed to come up healthy — aborting"
  "${COMPOSE_DEV[@]}" logs --tail 80
  exit 1
fi

# nginx.conf is shared by dev and prod (only ports/restart policy differ
# between overlays) — testing the live dev gateway's config also covers
# prod. Run against the live container, not a standalone one: nginx
# resolves upstream server names once at startup, and a standalone
# container has no identity-api/catalog-api/support-api to resolve.
if "${COMPOSE_DEV[@]}" exec -T gateway nginx -t; then
  ok "nginx -t against the live gateway config"
else
  bad "nginx -t against the live gateway config"
fi

# ---------------------------------------------------------------------------
section "Routing: each route group reaches its own upstream"
# ---------------------------------------------------------------------------
check_reaches_upstream() {
  local desc="$1" method="$2" path="$3" expected_status="$4"
  shift 4
  local status resp_body
  status="$(curl -s -o "$TMP_DIR/body" -w '%{http_code}' -X "$method" "$@" "$GATEWAY_URL$path")"
  resp_body="$(cat "$TMP_DIR/body")"
  if [ "$status" != "$expected_status" ]; then
    bad "$desc: expected HTTP $expected_status, got $status ($resp_body)"
  elif [ "$resp_body" = "$GATEWAY_404_BODY" ]; then
    bad "$desc: got the gateway's own 404 — request never reached the upstream"
  else
    ok "$desc (HTTP $status)"
  fi
}

# Each check is followed by a sleep so the zone it consumed (auth_limit is
# shared by nothing else; write_limit is shared by /users/ and /tickets/;
# products_read_limit is dedicated to GET /products/) has refilled before
# the next check or the burst tests further down.
check_reaches_upstream "auth/login -> identity-service" POST /api/v1/auth/login 422 \
  -H "Content-Type: application/json" -d '{}'
sleep 7

check_reaches_upstream "users/me -> identity-service" GET /api/v1/users/me 401
sleep 1

check_reaches_upstream "tickets -> support-service" GET /api/v1/tickets 401
sleep 1

check_reaches_upstream "products -> catalog-service" GET /api/v1/products 200
sleep 1

# #284 AC: an unmapped path returns the gateway's own JSON 404, not a raw
# nginx error page. The catch-all location has no limit_req, so this needs
# no refill wait.
unmapped_status="$(curl -s -o "$TMP_DIR/body" -w '%{http_code}' "$GATEWAY_URL/api/v1/nonsense")"
unmapped_body="$(cat "$TMP_DIR/body")"
if [ "$unmapped_status" = "404" ] && [ "$unmapped_body" = "$GATEWAY_404_BODY" ]; then
  ok "unmapped path returns the gateway's own JSON 404"
else
  bad "unmapped path: expected the gateway's JSON 404, got HTTP $unmapped_status ($unmapped_body)"
fi

# ---------------------------------------------------------------------------
section "Correlation id (X-Request-ID)"
# ---------------------------------------------------------------------------
GIVEN_ID="smoke-292-$(date +%s)-given"
resp_headers="$(curl -s -D - -o /dev/null "$GATEWAY_URL/api/v1/products" -H "X-Request-ID: $GIVEN_ID")"
if printf '%s' "$resp_headers" | tr -d '\r' | grep -qi "^x-request-id: $GIVEN_ID$"; then
  ok "client-supplied X-Request-ID is preserved end-to-end and echoed on the response"
else
  bad "client-supplied X-Request-ID was not echoed back unchanged"
fi
sleep 1

resp_headers="$(curl -s -D - -o /dev/null "$GATEWAY_URL/api/v1/products")"
generated_id="$(printf '%s' "$resp_headers" | tr -d '\r' | grep -i '^x-request-id:' | cut -d' ' -f2)"
if [ -n "$generated_id" ]; then
  ok "a request without X-Request-ID gets one generated ($generated_id)"
else
  bad "no X-Request-ID was generated for a request that didn't send one"
fi
sleep 1

# ---------------------------------------------------------------------------
section "Anti-spoofing (X-User-Id / X-User-Role stripped before the upstream)"
# ---------------------------------------------------------------------------
# catalog-service/support-service don't wire up request logging yet (only
# identity-service calls configure_logging() — a pre-existing gap outside
# this ticket's scope), so identity-service is the representative upstream
# here. The gateway's proxy_set_header directives are declared once at
# server{} level, not per-location, so this proves the behavior for every
# route group.
SPOOF_ID="smoke-292-spoof-$(date +%s)"
curl -s -o /dev/null "$GATEWAY_URL/api/v1/users/me" \
  -H "X-Request-ID: $SPOOF_ID" -H "X-User-Id: attacker" -H "X-User-Role: admin"
sleep 1

log_line="$("${COMPOSE_DEV[@]}" logs identity-api 2>&1 | grep -a "request_id=$SPOOF_ID")"
if [ -z "$log_line" ]; then
  bad "no request-scoped log line found for request_id=$SPOOF_ID"
elif printf '%s' "$log_line" | grep -q "x_user_id=''" && printf '%s' "$log_line" | grep -q "x_user_role=''"; then
  ok "spoofed X-User-Id/X-User-Role arrived empty at the upstream"
else
  bad "spoofed X-User-Id/X-User-Role reached the upstream non-empty: $log_line"
fi
sleep 1

# ---------------------------------------------------------------------------
section "Rate limiting: enforcement, not just config validity"
# ---------------------------------------------------------------------------
# limit_req has no burst= allowance configured, so a handful of concurrent
# requests is enough to trip every zone regardless of its nominal rate.
burst() {
  local method="$1" path="$2" n="$3"
  shift 3
  local i
  for i in $(seq 1 "$n"); do
    (
      code="$(curl -s -D "$TMP_DIR/h_$i" -o "$TMP_DIR/b_$i" -w '%{http_code}' -X "$method" "$@" "$GATEWAY_URL$path")"
      printf '%s' "$code" >"$TMP_DIR/c_$i"
    ) &
  done
  wait
}

assert_rate_limited() {
  local desc="$1" method="$2" path="$3" n="$4"
  shift 4
  burst "$method" "$path" "$n" "$@"
  local i code retry resp_body found=0
  for i in $(seq 1 "$n"); do
    code="$(cat "$TMP_DIR/c_$i")"
    if [ "$code" = "429" ]; then
      found=1
      retry="$(tr -d '\r' <"$TMP_DIR/h_$i" | grep -i '^retry-after:')"
      resp_body="$(cat "$TMP_DIR/b_$i")"
      if printf '%s' "$resp_body" | grep -q "$RATE_LIMIT_MARKER" && printf '%s' "$retry" | grep -qi 'retry-after: *6'; then
        ok "$desc: 429 with correct JSON shape and Retry-After"
      else
        bad "$desc: got 429 but shape/header is wrong (retry='$retry' body='$resp_body')"
      fi
      break
    fi
  done
  if [ "$found" -eq 0 ]; then
    bad "$desc: a burst of $n concurrent requests never triggered 429 — enforcement not working"
  fi
}

assert_rate_limited "auth_limit (10 r/m)" POST /api/v1/auth/login 8 \
  -H "Content-Type: application/json" -d '{}'
sleep 1

# #285 AC: GET on /tickets/ and /users/ is still subject to write_limit at a
# sane rate, and the zone is genuinely shared between them (not accidentally
# given a conditional key the way products_read/write_limit needed — that
# would let each path's GET through independently). Fire one concurrent
# burst split across BOTH paths: a wall-clock gap between two separate curl
# calls is too racy against write_limit's fast 0.5s refill to prove sharing
# reliably, but a single atomic burst isn't.
mixed_paths=(/api/v1/tickets /api/v1/users/me /api/v1/tickets /api/v1/users/me
  /api/v1/tickets /api/v1/users/me /api/v1/tickets /api/v1/users/me)
i=0
for p in "${mixed_paths[@]}"; do
  i=$((i + 1))
  (
    code="$(curl -s -o /dev/null -w '%{http_code}' "$GATEWAY_URL$p")"
    printf '%s' "$code" >"$TMP_DIR/wl_$i"
  ) &
done
wait
wl_through=0
wl_limited=0
for i in $(seq 1 "${#mixed_paths[@]}"); do
  code="$(cat "$TMP_DIR/wl_$i")"
  if [ "$code" = "429" ]; then
    wl_limited=$((wl_limited + 1))
  else
    wl_through=$((wl_through + 1))
  fi
done
if [ "$wl_limited" -ge 1 ] && [ "$wl_through" -le 2 ]; then
  ok "write_limit is shared across /tickets and /users/: $wl_through/${#mixed_paths[@]} got through, rest 429"
else
  bad "write_limit: expected a shared bucket (~1 through, rest 429) across /tickets+/users/, got $wl_through through / $wl_limited limited"
fi
sleep 1

assert_rate_limited "products_read_limit (20 r/s)" GET /api/v1/products 15
sleep 1

assert_rate_limited "products_write_limit (2 r/s)" POST /api/v1/products 8 \
  -H "Content-Type: application/json" -d '{}'
sleep 1

# #285 AC: a burst of mutating requests must not bleed into the read zone on
# the same location. products_read_limit is itself zero-burst, so firing
# *several* concurrent reads alongside the write burst would mostly 429 on
# reader-vs-reader contention alone — that's a confound, not evidence of a
# shared bucket. Fire exactly one read alongside the write burst instead, in
# the same atomic dispatch (no sequential wall-clock gap to race against
# either zone's refill): with a lone reader, a 200 is only possible if the
# read zone's own bucket — sitting untouched and full since the last check —
# wasn't also drained by the concurrent write burst.
for i in $(seq 1 8); do
  (
    code="$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "Content-Type: application/json" -d '{}' "$GATEWAY_URL/api/v1/products")"
    printf '%s' "$code" >"$TMP_DIR/rw_w_$i"
  ) &
done
(
  code="$(curl -s -o /dev/null -w '%{http_code}' "$GATEWAY_URL/api/v1/products")"
  printf '%s' "$code" >"$TMP_DIR/rw_r"
) &
wait
read_status="$(cat "$TMP_DIR/rw_r")"
if [ "$read_status" = "200" ]; then
  ok "products read/write zones are independent: a GET succeeded during a simultaneous write burst"
else
  bad "products read/write zones: a GET got $read_status during a simultaneous write burst — may be double-counting"
fi
sleep 1

# ---------------------------------------------------------------------------
section "/healthz does not need any upstream service to be up"
# ---------------------------------------------------------------------------
"${COMPOSE_DEV[@]}" stop identity-api catalog-api support-api >/dev/null 2>&1
status="$(curl -s -o /dev/null -w '%{http_code}' "$GATEWAY_URL/healthz")"
if [ "$status" = "200" ]; then
  ok "/healthz returns 200 with all three upstream services stopped"
else
  bad "/healthz returned $status with upstreams stopped"
fi

# ---------------------------------------------------------------------------
if [ "$FAILURES" -eq 0 ]; then
  printf '\nAll gateway smoke checks passed.\n'
  exit 0
else
  printf '\n%d gateway smoke check(s) FAILED.\n' "$FAILURES"
  exit 1
fi
