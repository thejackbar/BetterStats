# Multi-sport architecture

How to grow BetterStats from a cricket-only platform into one that also runs
Australian Rules football, then soccer, netball, rugby league, hockey and
whatever comes after, while keeping the two hard requirements the business
has set:

- **Runtime separation.** A code change and redeploy for one sporting code
  must never impact or compromise another. A bad cricket deploy cannot touch
  football's data or take football offline.
- **One codebase for shared work.** A bug fix or enhancement to common
  software must never mean editing and redeploying several separate codebases.
  Fix it once.

Those two pull in opposite directions only if you conflate two different
things. The resolution runs through this whole document, so it is worth
stating up front.

## The one idea that reconciles the two requirements

Separate **codebase** from **runtime instance**.

- A **codebase** is source. There is exactly ONE (this monorepo). It builds
  ONE set of images. A shared fix is a single commit, so requirement two holds.
- A **runtime instance** is a running stack: its own containers, its own
  database, its own domain, its own backup lineage. There is ONE PER SPORTING
  CODE. Redeploying cricket recreates only cricket's containers and can only
  reach cricket's database, so requirement one holds.

The unit of isolation is the **sporting code**, not the domain, not the repo,
not the container image. Everything below is an application of that single
rule to each layer you named: domain, nginx-proxy-manager, docker services,
source code, GitHub repo, database, bltbox folder layout, and backups.

"Sport as configuration, not as a fork." The active sport is chosen by
configuration, principally one environment variable (`SPORT=cricket|afl|soccer|...`),
and where terminology or data or legal naming diverges by region, a second
`REGION` value alongside it (see "The instance key is (code, region)" below).
The same image, pointed at a different database with a different `SPORT` value
and a different hostname, IS the football instance.

### Why not the two obvious alternatives

- **One database with a `sport` column (pooled multi-tenancy).** Rejected. It
  breaks runtime separation: one database and one deploy means the blast radius
  of any change spans every sport, and per-sport backup/restore stops being
  clean. You already lean away from this ("backups dependent on sporting
  code", "runtime separation").
- **A separate repo per sport.** Rejected. It breaks the fix-once rule: a
  common bug now has to be fixed in every repo, or maintained as a shared
  library with a version-bump dance across repos, which is exactly the
  "multiple codebases updated and redeployed" pain to avoid.

The monorepo-plus-per-sport-stack model is the only one that satisfies both.

## Source code: one repo, a core-plus-plugins layout

Stay a monorepo. Reorganise the inside into a sport-agnostic **core** and thin
per-sport **plugins**, with a registry that activates one plugin from the
`SPORT` env var at boot.

```
backend/app/
  core/                 # sport-agnostic. The bulk of today's code.
    auth/ orgs/ teams/ players/ seasons/ competitions/ fixtures/
    comms/ fees/ merch/ votes/ availability/ billing/ usage/
    notifications/ marketing/ setup/ ...
  sports/
    cricket/            # today's cricket-specific code, moved here as-is
      data_source/      # grassroots_scores_client, sync_grassroots_*, playhq_*
      stats/            # batting_innings, bowling_spells, fielding_stats models
      iq/               # partnerships, dismissals, economy, dossier metrics
      profile.py        # labels, stat columns, scorecard shape, brand
      migrations/       # cricket-only Alembic revisions
    afl/                # future: the same shape, AFL implementations
    soccer/
  sport_registry.py     # SPORT env -> the active SportPlugin
```

A `SportPlugin` is a small interface the core calls through. The pieces that
genuinely differ between sports are only these:

1. **Data source adapter.** Discover competitions, then matches, then match
   detail, then normalise into the common tables. Cricket's existing
   `grassroots_scores_client` and `sync_grassroots_game_level_data` become the
   cricket implementation with no logic change. AFL gets its own (PlayHQ runs
   AFL too, found the same way the cricket and UK feeds were found: capture the
   real request from a browser network tab, see `docs/uk-play-cricket-data-source.md`).
2. **Statline schema and models.** Cricket's per-innings tables stay cricket's.
   AFL adds disposals, marks, tackles, goals, behinds, and so on. Because each
   sport runs a separate database (below), an AFL database simply never creates
   cricket's tables and the reverse holds too.
3. **Analytics (BetterIQ).** The metrics are sport-specific (a bowling economy
   has no AFL meaning). The plumbing around them (opponent identity resolution,
   the dossier cache, the fixture-aware scouting flow) is shared. Keep the shell
   in core and the metrics in the plugin.
4. **The `SportProfile`.** Labels ("grade" vs "division", "innings" vs
   "quarter"), the stat columns a table renders, the scorecard renderer, and
   the brand string ("BetterCricket" vs "BetterAFL"). Shared components read
   this instead of hardcoding cricket words.

Everything else (roughly the other 90 percent: clubs, teams, players, seasons,
availability, comms, fees, merch, socials, billing, votes, usage, CRM,
notifications, the setup wizard) is sport-agnostic and reused unchanged. The
core must never contain `if sport == "cricket"`. Sport names live only inside
the plugins and the registry.

The frontend mirrors this: `frontend/src/core/` for shared components and
pages, `frontend/src/sports/<code>/` for the sport-specific renderers, labels,
stat tables and IQ views, and a `sportConfig` that the app reads at runtime.

### How this satisfies fix-once and isolation at the same time

Both plugins ship inside the same image. The container activates one via
`SPORT`. So:

- A shared-core fix rebuilds one image. Every sport stack can pull that one
  image tag. The bug is fixed once. (Requirement two.)
- A cricket-plugin change rebuilds the same one image, but the football stack
  keeps running its currently pinned tag until you choose to roll it forward,
  and even once it does, football never executes cricket's code path. Deploying
  cricket recreates only cricket's containers. (Requirement one.)

The word "redeployed" is worth being precise about. Rolling one image out to
several stacks is several deploy actions, but it is not several codebases being
maintained. It is one mechanical, identical, scriptable step per stack, and it
is staged and independent per stack, which is exactly what gives you the
per-sport rollout and rollback that runtime separation is really asking for.

## GitHub repo

One repo. Renaming it from `betterstats` to something sport-neutral like
`bettersports` (the trading company name) signals the wider scope, but that is
cosmetic and low priority; "BetterStats" as the Core module name already reads
as sport-agnostic.

CI builds a single versioned image pair on merge to `main`
(`backend:vX`, `frontend:vX`). Deploy pins each sport stack to a tag. That tag
pinning is what lets cricket run `vN+1` while football stays on `vN` during a
canary, and lets you roll one sport back without touching the others.

Path-filtered CI is a nice-to-have: a change confined to `sports/cricket/` can
run cricket's eval and test suites without gating the others, but the built
artifact stays the one shared image.

## Container images and how the frontend picks its sport

Keep it to **one backend image and one frontend image**, both sport-selected at
container start, so the "one artifact" property holds.

- Backend reads `SPORT` at startup, asks `sport_registry` for the plugin, and
  loads only that plugin's data source, models, migrations and IQ metrics.
- Frontend is a static SPA, so bake nothing sport-specific into the bundle.
  Inject the sport at container start: an entrypoint runs `envsubst` over a
  small `/sport-config.json` (or a `window.__SPORT__` snippet) from the `SPORT`
  env var, and the SPA reads it on load, the same way a runtime-config SPA
  normally handles per-environment settings. Same image serves cricket or AFL
  depending on the variable.

If you ever want belt-and-suspenders isolation where football's image does not
even contain new cricket bytes, you can instead build per-sport image tags from
the same repo with a build arg. That costs N image builds per release and loses
the single-artifact simplicity, so treat it as an option to reach for only if
an auditor demands it, not the default.

## Docker services and the bltbox layout

Keep the current model (one box, one systemd-managed compose project
`bltbox_docker_app`, services defined in the central
`/srv/docker/docker-compose.yaml`). Make each sport a **parameterised group of
services** inside it.

The global prefix is **`bs-` (BetterSports)**, the platform umbrella, not
`bc-`/`bettercricket-`/`betterstats-`, all of which imply cricket and would
read wrong on a hockey or netball stack. Per sporting code, four services:

```
bs-cricket-frontend   bs-cricket-backend   bs-cricket-db   bs-cricket-backup-agent
bs-afl-frontend       bs-afl-backend       bs-afl-db       bs-afl-backup-agent
bs-hockey-frontend    ...
```

The current cricket services are named `betterstats-*`. Rename them to
`bs-cricket-*` at a convenient maintenance window (a compose service rename plus
the volume, and repoint the nginx-proxy-manager host) so the whole box speaks
one convention. It is not urgent, but do not enshrine `betterstats-*` as the
pattern new sports copy.

The umbrella brand is **BetterSports**, at `bettersports.com.au` (owned;
`bettersport.com` is taken, and `bettersports.app` is worth acquiring for a
future cross-sport console or account portal). That umbrella domain is the
corporate and platform home; the per-sport public sites live under the
`betterat.<sport>` family. Keep the two roles distinct: `bettersports.*` is the
company and the internal platform, `betterat.<sport>` is what a club sees.

### The instance key is (code, region)

For most sports the instance is keyed on the sporting code alone. FIFA football
forces a second axis, because the same code is called different things in
different places and that difference is not cosmetic, it is a hard naming rule
(see Domains below). So the real instance key is **(sporting code, region)**,
with region defaulting to a single global value for any sport that does not need
splitting, and becoming explicit only when terminology, data or legal naming
diverges:

```
bs-cricket-<...>          # code=cricket, region=global (one instance for now)
bs-afl-<...>              # code=afl,     region=au
bs-soccer-au-<...>        # code=soccer,  region=au   (branded "Soccer")
bs-football-uk-<...>      # code=soccer,  region=uk   (branded "Football")
```

`bs-soccer-au-*` and `bs-football-uk-*` run the SAME FIFA-football plugin code.
They differ only in their instance profile: region, terminology, branding,
which hostnames they may bind, and which data source they pull. The data does
not overlap anyway (an English grassroots club and an Australian one share
nothing), so separate regional databases are natural rather than a cost. This
is the same shape cricket already hints at with its AU and UK data sources, just
made a first-class axis because soccer's naming makes it unavoidable.

Key rules, each of which is a direct lesson from the June 2026 outage
post-mortems already in `CLAUDE.md`:

- **Each sport gets its own Postgres container and its own named volume**
  (`bs_cricket_pgdata`, `bs_afl_pgdata`). This is what makes data isolation and
  per-sport backup real, and it keeps each sport's data in a clearly named,
  dedicated volume so the "compose project split onto an empty volume" class of
  failure cannot silently cross sports.
- **The frontend `nginx.conf` proxies `/api` to that sport's own backend
  service name** (`bs-cricket-backend`, never a bare `backend`), the same
  discipline the current single-stack config already requires.
- `COMPOSE_PROJECT_NAME=bltbox_docker_app` stays load-bearing and unchanged.
- The images are shared, so the only per-sport differences are: the `SPORT`
  value, the domain and CORS origin, the database name and volume, the host
  port, the backup lineage, and the secrets. That short difference list is what
  makes templating practical.

`deploy.sh` becomes `deploy.sh <sport>`: it targets only that sport's
`-frontend` and `-backend` (never its `-db`), pins the image tag for that
sport, and runs the existing nginx-proxy-manager self-heal step against that
sport's frontend hostname. Because docker-compose has no real templating, keep
one template plus a per-sport `.env` file (`cricket.env`, `afl.env`) and either
a tiny generator or a per-sport compose override; the generator route is
cleaner as the sport count grows.

Capacity: the box already runs about 26 containers. Cricket plus AFL plus
soccer adds roughly 12 more, which is fine. When a sport outgrows the shared
box, move that sport's stack to its own host with no code change: same image,
same template, different machine. Nothing in the application couples a sport to
a box, so this is a pure ops move and also the strongest available runtime
isolation if you ever want it.

## Domains and nginx-proxy-manager, including the shared `.football` question

The important reframing: **a domain is a routing detail. The unit of everything
else is the sporting code.** How many domains you bought is decoupled from how
many sports you run.

Straightforward cases first:

- `betterat.cricket` -> cricket's `-frontend`. Brand BetterCricket.
- `betterat.football` -> AFL's `-frontend`. Brand BetterAFL (or BetterFooty).
- `betterat.soccer` -> soccer's `-frontend`. Brand BetterSoccer.

Each is one nginx-proxy-manager proxy host pointing at that sport's frontend
container on the shared docker network. A clean one-to-one mapping, exactly like
`betterstats.cricket` maps today.

Now the interesting part. Two separate collisions sit on the word "football":

- **Code collision (within Australia).** "Football" means AFL in some states
  and rugby league in others. Both want a football name; they are different
  sporting codes.
- **Region collision (across countries).** FIFA football is "soccer" in
  Australia and the USA but "football" in the UK and Europe. Same code, opposite
  words, and the wrong word is not merely awkward, it is unacceptable.

Handle both by treating the hostname-to-instance mapping as data, subject to one
firm rule.

**Each instance advertises only the hostnames that are correct for its region,
and a region-wrong hostname is never bound to it.** This is the structural way
to guarantee the soccer/football naming rule rather than trusting everyone to
remember it:

- A `.soccer` TLD or a `soccer.` subdomain may only ever point at an AU or US
  soccer instance (`bs-soccer-au-*`). It must NEVER resolve to the UK
  FIFA-football instance. In the UK "soccer" is wrong, so the UK instance simply
  has no soccer hostname to leak. Because the regions are separate instances,
  this is enforced by there being nothing to misconfigure, not by a policy note.
- The UK FIFA-football instance (`bs-football-uk-*`) is reached under a football
  name only: `betterat.football`, or a UK-appropriate football domain if you
  acquire one. Its canonical URLs, share cards and emails all use that host, so
  a UK user is never shown a soccer address.
- In Australia, soccer under `betterat.soccer` or a `soccer.` subdomain is fine,
  and that is where AU soccer lives.

For the Australian code collision, use **a subdomain per code**, each still its
own fully independent stack:

```
afl.betterat.football   -> AFL stack   (bs-afl-frontend)
nrl.betterat.football   -> NRL stack   (bs-nrl-frontend)
```

Note the consequence: the apex `betterat.football` genuinely means different
sports in different countries (AFL or NRL to an Australian, FIFA football to a
Briton). So the apex is the one place a region decision is legitimate: route
`betterat.football` by region at the edge (the Cloudflare worker you already run
is the right layer), sending UK and European visitors to the UK FIFA-football
instance and Australian visitors to a small AFL/NRL chooser. This is the
deliberate exception to "no geo routing": it applies only to the ambiguous apex,
never to a code-or-region-explicit subdomain, which always resolves to exactly
one stack regardless of who asks.

Three things to hold the line on:

- **Keep the sport explicit in the hostname wherever the name is unambiguous.**
  Do not disambiguate a specific code by URL path (`betterat.football/afl`).
  Path prefixes couple codes at the proxy and complicate the SPA. Geo routing is
  confined to the genuinely ambiguous apex and nowhere else.
- **Never bind a region-wrong hostname to an instance.** No `.soccer` anywhere
  near the UK stack; no bare football-only host as the canonical address of the
  AU soccer stack. The instance profile lists its allowed hosts, and nginx-proxy-manager
  only ever holds those.
- **Do not let one "football" stack serve both AFL and NRL.** They are
  different sporting codes with different feeds, stats and competitions, so each
  is its own stack. `.football` is a shared street address, not a shared
  building, and the same is true of any domain fronting more than one code or
  region.

## Database

One database per sporting code (the silo). Inside each database:

- **Common core schema, identical across sports.** organisations, users,
  teams, players, seasons, competitions (generalise today's "grades" into a
  sport-neutral competition concept), games and fixtures, subscriptions and
  billing, comms, fees, merch, votes, availability, usage, notifications,
  marketing and CRM. This is most of the existing 200-plus migrations and it is
  reused as-is.
- **Sport-specific schema.** The statline tables and the sport's analytics
  caches. Cricket keeps `batting_innings`, `bowling_spells`, `fielding_stats`
  and the rest. AFL adds its own. A cricket database never creates AFL tables
  because the cricket container never loads the AFL plugin's migrations.
- **Sport-specific attributes on shared tables**, which is the "additional
  sporting-code-specific attributes" you described. Two mechanisms, used
  together:
  - A nullable typed column when a field is hot and queried a lot.
  - A JSONB `attributes` (or `sport_config`) column on players, teams and games
    for the open-ended long tail, so a new sport rarely needs a migration to
    carry a new attribute. This is the same pattern already in use for
    `scouting_intel`, `theme_config` and similar blobs, so it is a known
    quantity here. Promote a JSON key to a typed column when it earns it.

Migrations: keep Alembic plus the idempotent `main.py` lifespan mirror. Split
the revision tree into core revisions (applied in every sport's database) and
per-sport revisions (applied only when that plugin is active). On startup the
container applies core plus its own sport's revisions and nothing else, which it
knows because it knows its `SPORT`.

One guardrail worth adding: record the sport in a single `instance_meta` (or
`platform_settings`) row, and have the backend assert on boot that `SPORT`
matches what the database says it is. That refuses to start a football
container accidentally pointed at the cricket volume, which is the same class of
mistake the June 2026 project-split was, caught before it can do damage.

## Backups and restore

Backups are already per-stack (a `pg_dump -Fc` of the one database plus the
`uploads` volume, age-encrypted, driven from `ops/backup`). Making them
per-sport is a small generalisation of what exists, and it satisfies the
"backups dependent on sporting code" requirement directly:

- One backup agent, timer and service per instance (`bs-<code>[-<region>]-backup-agent`).
- A per-instance backup root (`/mnt/media/bettersports/backup/<code>[-<region>]/`) so each
  sport's lineage is its own directory.
- Its own `AGE_RECIPIENT`, or a shared key with separate lineage, your call.
- Restore stays SSH-only and targets only that sport's database and volume. The
  per-club restore feature stays naturally within a sport, since a club belongs
  to exactly one sporting code.

Because each sport has its own database and volume, a restore of cricket
touches only cricket, which is the whole point.

## A phased path that de-risks the change

You are not being asked to build all of this at once, and the order matters.
Get the seams right while there is still only one sport, because retrofitting
seams after two sports are live is much harder.

1. **Introduce the sport abstraction with no behaviour change.** Add
   `SPORT=cricket` (defaulting to cricket), the `sport_registry`, and move the
   cricket data source, stat models and IQ behind a `sports/cricket` plugin;
   add a `SportProfile` for labels and branding. Everything still runs exactly
   as today. This is a refactor, validated by the existing test and eval
   suites, shipped to the current cricket stack with nothing user-visible
   changing.
2. **Templatise deploy, compose and backups by sport.** Prove you can stand up
   a second, empty stack (`afl`, on `betterat.football`) running the same image
   with `SPORT=afl` and a stub AFL plugin: the shell, the branding, an empty
   database, the domain, the backup timer. No AFL data yet.
3. **Build the AFL plugin.** The AFL data source adapter, stat schema,
   scorecard renderer and IQ metrics. All net-new code under `sports/afl`, zero
   risk to cricket because cricket never loads it.
4. **Repeat per sport.** Soccer, netball, rugby league, hockey. Each new sport
   is a new plugin plus a new stack, with no core change required.

## Anti-patterns to avoid

- Pooling every sport into one database with a `sport_id` discriminator. Breaks
  isolation, independent deploy, and per-sport backup.
- Forking the repo per sport. Breaks fix-once.
- One "football" stack serving both AFL and NRL. Different sports; share the
  domain, not the stack.
- Encoding a specific code in a URL path. Keep it explicit in the hostname; the
  only legitimate geo routing is the genuinely ambiguous apex (`betterat.football`).
- Binding a `.soccer` or `soccer.` hostname anywhere near the UK FIFA-football
  instance, or any region-wrong name to any instance.
- Carrying `bc-`/`bettercricket-`/`betterstats-` forward as the service prefix
  for new sports. The platform prefix is `bs-`.
- Scattering `if sport == "cricket"` through the services. Sport lives behind
  the plugin interfaces; the core does not know sport names.

## Summary

- One monorepo, reorganised into a sport-agnostic core plus thin per-sport
  plugins, selected by a `SPORT` env var. Fix shared code once.
- One backend image and one frontend image, sport-selected at container start.
- One independent runtime stack per instance, keyed on (sporting code, region),
  region explicit only where naming, data or terminology diverge (FIFA football).
  Each has its own containers, Postgres and volume, hostnames and backups, so a
  deploy or a bug in one instance cannot reach another.
- Service and volume naming uses the platform prefix `bs-` (BetterSports), never
  a cricket-implying prefix. Umbrella brand at `bettersports.com.au`; per-sport
  public sites at `betterat.<sport>`.
- Domains map to instances one-to-one on a dedicated TLD, via subdomain-per-code
  where one TLD fronts several codes (`afl.`/`nrl.betterat.football`), and with a
  firm region rule: an instance binds only region-correct hostnames, so a
  `.soccer` address never reaches the UK and the UK football instance never shows
  soccer. Geo routing is allowed only at the ambiguous apex.
- Databases share the core schema and diverge only in the statline and
  analytics, with sport-specific attributes carried as nullable columns or a
  JSONB blob.
- The (sporting code, region) instance, not the domain or the repo or the image,
  is the unit of isolation.
