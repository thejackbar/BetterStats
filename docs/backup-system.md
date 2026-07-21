# BetterStats backup system

Automated daily backups (with a "Run backup now" button), a manual full
restore, and a manual per-club restore, plus a Super Admin "Backups" page
showing run history and current database size stats. No downtime for backup;
a full restore needs a brief app stop only at the final cutover step; a
per-club restore needs no downtime at all. Restore is deliberately
SSH-only — see "Why restore has no UI button" below.

## What's backed up

- **Postgres** — `pg_dump -Fc` against the live `betterstats-db`, an
  MVCC-consistent snapshot (no locks, no downtime).
- **The `uploads` Docker volume** — player/logo/yearbook files not stored as
  DB `bytea` columns. Most images ARE stored in Postgres already (see
  CLAUDE.md), but not all, so this is required for a complete restore.
- Both are age-encrypted before they touch disk (backups hold player PII —
  emails, phones).

Not included (out of scope for this phase, see `.env.example`): a copy of
`/srv/docker/.env` (secrets). Keep that backed up separately, by hand — it
changes rarely and shouldn't live in a daily-rotated, app-readable bundle.

## One-time server setup

1. **Generate an age keypair** (do this once, keep the private key OFFLINE —
   e.g. a password manager, not on the box):
   ```bash
   age-keygen -o backup-key.txt
   ```
   Copy the public key (`age1...` line) — that's `AGE_RECIPIENT` below. Put
   the private key file at `/root/.age/backup-key.txt` on the box (needed
   only for `restore.sh`, never for `backup.sh`).

2. **Copy this directory to the server**:
   ```bash
   # from a checkout of this repo on the box, or scp'd across
   cp -r ops/backup /srv/docker/betterstats/ops/backup
   chmod +x /srv/docker/betterstats/ops/backup/*.sh
   ```

3. **Set `AGE_RECIPIENT`** (and anything else you want to override) in
   `/srv/docker/betterstats/backup.env`:
   ```bash
   AGE_RECIPIENT=age1qyourpublickeyhere...
   BACKUP_ROOT=/srv/backups/betterstats
   ```

4. **Install the systemd units**:
   ```bash
   sudo cp /srv/docker/betterstats/ops/backup/betterstats-backup.{service,timer} /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now betterstats-backup.timer
   ```

5. **Confirm `age`, `zstd`, `numfmt` are installed** on the host (`apt
   install age zstd coreutils` on Debian/Ubuntu).

6. Set the schedule and retention from **Super Admin → All Clubs → General
   Settings → Backups** (defaults to 03:00 UTC, 30 days if you don't touch
   it) — no config file edit or redeploy needed to change either.

7. **(Optional) Set up the backup-agent** so Super Admin gets a "Run backup
   now" button instead of needing SSH for a manual run — see the next
   section. Skip this step and the button just shows "not configured yet";
   scheduled backups and SSH manual runs work either way.

## Backup-agent — enables the "Run backup now" button

The backend container has no Docker socket or host filesystem access (by
design — CLAUDE.md's container-safety rules exist for good reason), so it
can't run `backup.sh` itself. `ops/backup/agent/` is a small sidecar
container that DOES have that access, with a single fixed, secret-gated
endpoint (`POST /run-backup`) — no arbitrary command execution, and it's
never routed through nginx-proxy-manager, so it's only reachable from other
containers on the same internal Docker network.

1. **Generate a shared secret**: `openssl rand -hex 32` → this is
   `BACKUP_AGENT_SECRET`.
2. **Add it to `/srv/docker/.env`** (or wherever `AGE_RECIPIENT`/`DB_PASSWORD`
   already live): `BACKUP_AGENT_SECRET=...`
3. **Paste `ops/backup/agent/docker-compose.snippet.yaml`'s service into the
   central `/srv/docker/docker-compose.yaml`**, matching its `networks:` to
   whichever internal network `betterstats-backend` is already on.
4. **Build and start it**:
   ```bash
   cd /srv/docker
   export COMPOSE_PROJECT_NAME=bltbox_docker_app
   docker compose build betterstats-backup-agent
   docker compose up -d --no-deps betterstats-backup-agent
   ```
5. **Point the backend at it** — set in `/srv/docker/.env`:
   ```bash
   BACKUP_AGENT_URL=http://betterstats-backup-agent:8080
   BACKUP_AGENT_SECRET=...   # same value as step 2
   ```
   then redeploy the backend so it picks up the new env vars (`deploy.sh`).

The agent only ever runs `backup.sh` (with `BACKUP_FORCE=1`) — it has no
restore endpoint. See "Why restore has no UI button" below.

## Why restore has no UI button

Restoring (full or per-club) needs the age **private** key, and step 1 above
says to keep that key OFFLINE — not on the box at all, let alone in a
container the backend can reach over the network. Wiring restore into the
agent would mean putting that key somewhere network-reachable, which defeats
the point of keeping it offline. So restore — both `restore.sh apply` and
`restore.sh restore-club` — stays an operator-runs-it-over-SSH action. The
Super Admin Backups page shows restore tasks (logged the same way backups
are) but never a button to start one.

## Manual runs

```bash
# force a backup right now, ignoring the schedule window (still won't
# double-run if one already completed today — use BACKUP_FORCE=2 to force that too)
BACKUP_FORCE=1 BACKUP_TRIGGERED_BY=manual /srv/docker/betterstats/ops/backup/backup.sh

# list bundles
/srv/docker/betterstats/ops/backup/restore.sh list

# restore to a scratch container only, to verify a bundle without touching prod
/srv/docker/betterstats/ops/backup/restore.sh check 2026-07-21T03-00-00Z

# full restore into the live DB (asks for confirmation, briefly stops the app)
/srv/docker/betterstats/ops/backup/restore.sh apply 2026-07-21T03-00-00Z

# per-club restore — DRY RUN (default): reports what would change, writes nothing
/srv/docker/betterstats/ops/backup/restore.sh restore-club 2026-07-21T03-00-00Z <org-id>

# per-club restore — for real (asks for confirmation, no downtime, snapshots
# the club's current data first so it can be undone)
/srv/docker/betterstats/ops/backup/restore.sh restore-club 2026-07-21T03-00-00Z <org-id> --apply

# undo a previous --apply club restore
/srv/docker/betterstats/ops/backup/restore.sh rollback-club /srv/backups/betterstats/club-restores/<task_id>.json
```

Every run — scheduled or manual — is logged to the `backup_tasks` table and
shows up on **Super Admin → Backups**, along with the DB size / row count /
per-club breakdown captured at completion.

## Per-club restore — how it stays safe on a shared schema

Every club's data lives in the same tables, so "restore club X" can't be a
plain `pg_restore`. `app/services/club_restore.py` (invoked via
`app/scripts/restore_club.py`) does it table-by-table instead:

- **Direct tables** (an `organisation_id` column — players, settings,
  sponsors, fixtures, comms, merch, fees structure, memberships, ...):
  scoped straightforwardly by that column.
- **Game-scoped tables** (`batting_innings`, `bowling_spells`,
  `fielding_stats`, `bowler_wickets`, `game_appearances`, `fall_of_wickets`,
  `partnerships`, `milestones`, ...): these have NO `organisation_id` of
  their own, and — critically — a single game between two synced clubs
  shares ONE `games.id` row carrying BOTH sides' per-innings data. Scoping by
  `game_id` alone would restore or delete the *opponent's* rows for a shared
  game too. Instead, rows are scoped through whichever column(s)
  foreign-key-reference `players.id` (discovered live from
  `information_schema`, not a hardcoded list), keeping only rows whose
  linked player belongs to the target club. A fill-in row (no `player_id`,
  free-text name — see the fill-in-players feature) has no club owner in the
  row itself and is deliberately left untouched.
- Tables the tool can't safely attribute to one club (e.g. `fee_match_days`,
  which is member-scoped rather than player-scoped) are skipped and logged,
  not guessed at.
- **Dry-run by default.** Without `--apply`, nothing is written — it only
  reports live-row-count vs bundle-row-count per table.
- **Snapshot before write.** The FIRST thing `--apply` does is dump the
  club's current live rows to
  `/srv/backups/betterstats/club-restores/<task_id>.json` — same
  backup-before-write precedent as `klubpro_migration.py`'s import tool —
  before touching anything, so `rollback-club` can put it back.
- Each table is deleted-then-reinserted inside its own transaction (not one
  transaction across ~70 tables), so a failure partway through leaves a
  clearly diagnosable partial state rather than a long-held lock.

## Per-club size and record-count stats

Row counts per club are exact. Per-club *byte size* is an **estimate**:
Postgres doesn't track per-tenant size in a shared schema, so each table's
on-disk size is split across clubs in proportion to each club's share of
that table's rows (`app/services/backup_stats.py`). Good enough to spot "this
club's data got 10x bigger overnight", not a billing-grade number.

## Not built yet

- **This has not been run against a real database yet** — there's no
  Postgres instance in the environment this was built in to test against.
  Run `restore-club ... ` WITHOUT `--apply` (the default) against a real
  bundle and sanity-check the reported row counts before ever passing
  `--apply` on production data. The dry-run path touches nothing, so it's
  safe to rehearse repeatedly.
- **Restore buttons in the UI.** Deliberate, not a gap — see "Why restore has
  no UI button" above.
- **Offsite storage.** Local disk only for now
  (`/srv/backups/betterstats`) — add an `rclone`/`rsync` step to `backup.sh`
  after a local run if/when that's wanted.
