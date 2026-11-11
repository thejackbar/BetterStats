# Support chat (Chatwoot), Cap and Open Higgsfield on the box

Three self-hosted tools, written up so they can be put on the bltbox host without guessing. None of them is built or started from this repo: the compose files here are snippets to merge into `/srv/docker/docker-compose.yaml`.

| Tool | What it is for | Files |
|---|---|---|
| Chatwoot | The support inbox behind the Help window in the admin app. A bot answers simple FAQ questions and hands the rest to Jack and Elton. | `chatwoot.compose.yml`, `chatwoot.env.example` |
| Cap | Screen recordings with share links, for how-to videos and bug reports. | `cap.compose.yml`, `cap.env.example` |
| Open Higgsfield AI | A browser studio for AI images and video, billed to a Muapi.ai key each person pastes in. | `higgsfield.compose.yml`, `higgsfield.Dockerfile` |

Only Chatwoot is connected to BetterStats. Cap and Open Higgsfield are separate tools on their own addresses.

## Before you start

1. Check the box has room. Chatwoot is four containers (web, background worker, its own Postgres, Redis) and wants roughly 2 GB of memory. Cap adds a web app, MySQL, MinIO and a media server. Run `free -h` and `df -h` first. If memory is tight, start with Chatwoot only.
2. Every compose command runs from `/srv/docker` with `export COMPOSE_PROJECT_NAME=bltbox_docker_app`. Name only the services you are adding. Never recreate `betterstats-db`, never pass `-f`, never add `--remove-orphans`. The rules are in `docs/dev-notes/guides/platform-ops-and-site.md`.
3. Merge the services, volumes and networks from each snippet into the central file. `docker-shared-net` is already defined there, so do not add it twice.
4. DNS and nginx-proxy-manager (NPM). Add these hosts, each with a Let's Encrypt certificate:

| Host | Goes to | Notes |
|---|---|---|
| `help.betterat.cricket` | `chatwoot-rails:3000` | Turn on Websockets Support. Chatwoot's live chat needs it. |
| `cap.betterat.cricket` | `cap-web:3000` | Websockets on. |
| `cap-files.betterat.cricket` | `cap-minio:9000` | Browsers upload and play video from here. |
| `studio.betterat.cricket` | `open-higgsfield:3000` | Add an Access List (username and password). |

   Those four names are suggestions. If you pick others, change them in the env files too.

## 1. Chatwoot

```bash
cd /srv/docker
export COMPOSE_PROJECT_NAME=bltbox_docker_app
```

1. Copy `chatwoot.env.example` to `/srv/docker/chatwoot.env` and fill in every `CHANGE_ME`. Generate secrets with `openssl rand -hex 64`. Put `CHATWOOT_POSTGRES_PASSWORD=<same value as POSTGRES_PASSWORD>` in `/srv/docker/.env`.
2. Start the data services, prepare the database, then start the app:

```bash
docker compose up -d chatwoot-postgres chatwoot-redis
```

```bash
docker compose run --rm chatwoot-rails bundle exec rails db:chatwoot_prepare
```

```bash
docker compose up -d chatwoot-rails chatwoot-sidekiq
```

3. Open `https://help.betterat.cricket`. The first visit asks you to create the administrator and the account. Account id is `1` on a fresh install.
4. **Agents.** Settings, Agents: add Jack and Elton as Administrators. Each then opens Profile Settings and, under Notifications, turns on email and push for new conversations, assignments and mentions. Install the Chatwoot mobile app if you want a phone alert.
5. **The inbox.** Settings, Inboxes, Add Inbox, Website. Name it "BetterCricket admin help", website domain `betterat.cricket`, widget colour to suit. Add Jack and Elton as agents on the inbox. Then open the inbox's Settings and Configuration tab:
   - Copy the **website token** from the widget code snippet (`websiteToken: '...'`). This is `CHATWOOT_WEBSITE_TOKEN`.
   - Turn on **Enable identity validation** and copy the HMAC token it shows. This is `CHATWOOT_HMAC_TOKEN`. With it on, Chatwoot only trusts a person's name and email when our server signed them.
6. **The bot.** Settings, Integrations (or Bots), Agent Bot, add one. Name "BetterCricket helper". Outgoing URL:

   `https://betterat.cricket/api/public/support-chat/webhook/<CHATWOOT_WEBHOOK_SECRET>`

   Make the secret with `openssl rand -hex 24`. Copy the bot's **access token**: that is `CHATWOOT_BOT_TOKEN`. Then in the inbox's Settings, Bot Configuration, pick this bot. From then on a new conversation starts as **Pending** and the bot owns it until it hands over.
7. **Mentions (optional).** A hand-off note can @mention Jack and Elton so Chatwoot pings them. Find each agent's numeric id with `GET https://help.betterat.cricket/api/v1/accounts/1/agents` (send your own access token from Profile Settings in the `api_access_token` header). Set `CHATWOOT_MENTIONS=Jack:<id>,Elton:<id>`.
8. After the account is set up, `ENABLE_ACCOUNT_SIGNUP` stays `false`.

### Connect BetterStats

Add these to the backend's environment in the central compose file, with the values in `/srv/docker/.env` (see `docker-compose.yml` in this repo for the names):

| Variable | Value |
|---|---|
| `CHATWOOT_BASE_URL` | `https://help.betterat.cricket` |
| `CHATWOOT_INTERNAL_URL` | `http://chatwoot-rails:3000` if `betterstats-backend` shares `docker-shared-net` with it, otherwise leave empty and it uses the public address |
| `CHATWOOT_WEBSITE_TOKEN` | from step 5 |
| `CHATWOOT_HMAC_TOKEN` | from step 5 |
| `CHATWOOT_ACCOUNT_ID` | `1` |
| `CHATWOOT_BOT_TOKEN` | from step 6 |
| `CHATWOOT_WEBHOOK_SECRET` | the secret in the webhook URL |
| `CHATWOOT_MENTIONS` | optional, step 7 |

`ANTHROPIC_API_KEY` is already set for the other AI features and the bot uses it. `SUPPORT_CHAT_MODEL` can override the model (default `claude-sonnet-4-6`).

Then deploy the usual way (`/srv/docker/betterstats/deploy.sh`).

Nothing shows until the first three values are set: with them empty the Help button does not appear and the webhook answers 404.

### Check it works

1. Sign in to `/admin`. A Help button sits bottom right. If it does not, open the browser console and `GET /api/club-admin/support-chat/identity`: `{"enabled": false}` means a variable is missing on the backend.
2. Ask "How much does it cost?" The bot should answer from the FAQ within a few seconds.
3. Ask "Why is my fee report wrong?" or "Can I talk to a real person?" The window should say it has passed the chat to Jack and Elton. In Chatwoot the conversation moves from Pending to Open with a private note.
4. Backend logs: `docker compose logs betterstats-backend | grep "support chat"`. A line like `conversation 12 is 'open', the bot stays out` is normal.
5. If every message gets a hand-off and none an answer, read that log for `the model could not decide`. It names the cause (no API key, a model error).

## 2. Cap

1. Clone the source once, for the media-server build: `git clone https://github.com/CapSoftware/Cap.git /srv/docker/cap-src`, then `git -C /srv/docker/cap-src checkout <tag or commit you have read>`.
2. Add the lines from `cap.env.example` to `/srv/docker/.env`. Compose stops with a clear message if one is empty. There are no default passwords on purpose: upstream's compose ships guessable ones.
3. Merge `cap.compose.yml`, then:

```bash
docker compose build cap-media-server
```

```bash
docker compose up -d cap-mysql cap-minio cap-minio-setup cap-media-server cap-web
```

4. With no email provider set, the first sign-in link is printed in the log: `docker compose logs cap-web`.
5. In the Cap desktop app, Settings, Cap Server URL, enter `https://cap.betterat.cricket`.
6. Keep the `cap-web` image tag in step with the source you cloned. The default `latest` in the snippet is a placeholder to replace with the tag that matches your checkout.

## 3. Open Higgsfield AI

1. Copy `higgsfield.Dockerfile` to `/srv/docker/support-tools/higgsfield.Dockerfile` and set `HIGGSFIELD_REF` in `higgsfield.compose.yml` to a commit you have read.
2. Merge the compose snippet, then:

```bash
docker compose build open-higgsfield
```

```bash
docker compose up -d open-higgsfield
```

3. Add the NPM Access List on `studio.betterat.cricket` before sharing the address. Each person enters their own Muapi.ai API key on first use, and that key pays for what they generate.

## What was and was not tested

Tested in the repo (see `backend/verification/verify_support_chat.py`, and the Chromium run described in the archive entry): the bot's answer and hand-off logic against a stubbed Chatwoot and a stubbed model, the webhook secret check, the signed identity, and the admin widget loader against a stubbed Chatwoot script. The three compose files pass `docker compose config`.

Not tested, because the box and a Chatwoot server were out of reach: the real Chatwoot web client in the admin page, a live webhook from Chatwoot, the live model call, and starting any of the three stacks. The Chatwoot field names and menu paths above come from its documentation and may have moved in v4. The Open Higgsfield Dockerfile has not been built. Run the checks above after the first start and fix anything that differs.
