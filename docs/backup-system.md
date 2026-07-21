# BetterStats backup system

Phase 1 of the backup/restore plan: automated daily backups + a manual full
restore, both host-level scripts, plus a Super Admin "Backups" page showing
run history and current database size stats. No downtime for backup; a full
restore needs a brief app stop only at the final cutover step. Per-club
restore is a later phase — see "Not built yet" below.

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
```

Every run — scheduled or manual — is logged to the `backup_tasks` table and
shows up on **Super Admin → Backups**, along with the DB size / row count /
per-club breakdown captured at completion.

## Per-club size and record-count stats

Row counts per club are exact. Per-club *byte size* is an **estimate**:
Postgres doesn't track per-tenant size in a shared schema, so each table's
on-disk size is split across clubs in proportion to each club's share of
that table's rows (`app/services/backup_stats.py`). Good enough to spot "this
club's data got 10x bigger overnight", not a billing-grade number.

## Not built yet

- **Per-club restore.** Structurally feasible (every table reaches back to
  `organisations.id`, directly or via `seasons`/`grades`/`games`), but a real
  tool, not a `pg_restore` flag: restore the bundle to a scratch DB, walk the
  FK graph for one org, snapshot the club's *current* live rows (so the
  restore is itself undoable, same pattern as `klubpro_migration.py`'s
  backup-before-write), then upsert. Needs care around the FK-cascade drift
  documented in CLAUDE.md's migration-142 post-mortem (the ORM's `ondelete=`
  annotations weren't always the live schema's truth).
- **"Run backup now" / "Restore" buttons in the Super Admin UI.** Today,
  triggering a backup or restore means SSHing into the box and running the
  script directly (see "Manual runs" above). A UI button needs the backend to
  reach the host's Docker socket and filesystem, which it deliberately can't
  today — the plan is a small dedicated `betterstats-backup-agent` container
  (Docker-socket + backup-volume access only, internal-network-only, fixed
  API, no arbitrary command execution) that the backend calls instead of
  getting that privilege itself. Until that's built, the Super Admin Backups
  page is read-only (history + stats).
- **Offsite storage.** Local disk only for now
  (`/srv/backups/betterstats`) — add an `rclone`/`rsync` step to `backup.sh`
  after a local run if/when that's wanted.
