# Votes API — what exists, what's new

Everything below is additive. No existing endpoint changes shape; new fields are
added to existing payloads and three new endpoints are introduced.

## Existing (unchanged, in `backend/app/services/votes.py` + routers)

| Client method | Purpose |
| --- | --- |
| `api.votesFixtures({year, grade_id, round_key, q})` | Played fixtures + voting state |
| `api.votesFixtureDetail(id)` | Ballots, eligible list, weekly results, eligibility panel |
| `api.votesLeaderboard({year, grade_id, through_round})` | Season standings, replayable "as at" |
| `api.votesGetSettings()` / `votesSetSettings(patch)` | Vote config |
| `api.votesRegenerateLink()` | New magic-link token |
| `api.votesAdminBallot(fixtureId, body)` | Paper-vote entry |
| `api.votesSetFixtureSource(fixtureId, source)` | Per-fixture eligibility override |
| `api.votesLockFixture(id)` / `votesReopenFixture(id)` | Lock / reopen |
| `api.votesDeleteBallot(id)` | Delete a ballot |
| `api.votePublicLanding / votePublicFixture / votePublicVerify / votePublicSwitch / votePublicSubmit` | Public flow |

## New fields on existing payloads

### `GET /api/votes/fixtures`
```jsonc
{
  "fixtures": [{
    // …existing fields…
    "voters_expected": 11,        // NEW: eligible-voter count for this fixture,
                                  // derived from the resolved eligibility source
                                  // (0 when there is no team list yet)
    "outstanding_count": 3        // NEW: voters_expected - distinct player ballots
  }],
  "summary": {                    // NEW: powers the four hub counters
    "open": 2,
    "awaiting_team": 1,
    "ballots_in": 11,             // for the latest round in scope
    "ballots_expected": 22,
    "rounds_counted": 8,
    "rounds_total": 9
  }
}
```

### `GET /api/votes/fixtures/{id}`
```jsonc
{
  // …existing…
  "fixture": { "voters_expected": 11 },
  "outstanding": [                // NEW: eligible, hasn't voted
    { "id": "…", "name": "Ben Traill", "photo_url": null, "channel": "sms" }
  ]
}
```
`channel` is `"sms" | "whatsapp" | "none"`, derived from the player's contact
record (mobile present → sms; club-configured WhatsApp group → whatsapp).

### `GET /api/votes/leaderboard`
```jsonc
{
  // …existing: year, grades, rounds, standings, ballot_values,
  //            counting_method, tie_policy, through_round…
  "club_name": "Applecross Cricket Club",
  "club_short": "ACC",            // NEW: awards-night stage lockup
  "season_label": "2025/26",
  "grade_name": "1st Grade",
  "race_caption": "Fletcher led from round 4.",   // optional, nullable
  "standings": [{
    // …existing: player_id, name, points, raw, counts[], rounds…
    "grade": "1st Grade",         // NEW
    "grade_short": "1st",         // NEW
    "tied": false,                // NEW: replaces the client-side "=" derivation
    "movement": 1,                // NEW: rank change vs the previous counted
                                  // round (+ = climbed). 0 = unchanged.
    "form": [3, 2, 3, 0, 3],      // NEW: points earned in the last 5 counted
                                  // rounds, oldest first
    "cumulative": [3,3,6,9,12,15,19,22],  // NEW: running total per counted
                                  // round — only needed for the top 5
    "round_gain": 3               // NEW: points from the LAST counted round in
                                  // scope (drives the awards-night "+3" pill)
  }],
  "rounds": [{ "key": "r8", "label": "Round 8", "short": "R8", "counted": true, "date": "2026-01-31" }],
  "last_round": {                 // NEW: the "what just happened" card
    "label": "Round 8", "fixture": "@ Subiaco",
    "results": [{ "player_id": "…", "name": "Tom Fletcher", "points": 3 }]
  }
}
```

**Movement + cumulative are derived, not stored.** The service already replays
the count for any `through_round`; compute round N and round N-1 standings in the
same pass and diff the ranks. Cache per (year, grade, through_round) — awards
night hits this endpoint once per reveal.

## New endpoints

### `POST /api/votes/bulk-state`
```jsonc
// body
{ "fixture_ids": ["…", "…"], "action": "open" | "lock" }
// response
{ "updated": 2, "skipped": [{ "fixture_id": "…", "reason": "awaiting_team" }] }
```
Requires `MANAGE_VOTES`. Same per-fixture rules as the single lock/reopen calls;
fixtures that can't transition are reported in `skipped` rather than failing the
whole request.

### `POST /api/votes/nudge`
```jsonc
// body — either a single fixture with an explicit player list…
{ "fixture_id": "…", "player_ids": ["…"] }
// …or every outstanding voter across several fixtures
{ "fixture_ids": ["…", "…"] }
// response
{ "sent": 3, "failed": [{ "player_id": "…", "reason": "no_mobile" }] }
```
Requires `MANAGE_VOTES`. Sends through the existing BetterComms sender and MUST
respect `docs/bettercomms-usage-policy.md` — rate-limit to one nudge per player
per fixture per 24h and record the send against the fixture so the count is
auditable.

### `POST /api/votes/leaderboard/card` (optional, phase 2)
Renders the podium as a square PNG for BetterSocials.
```jsonc
{ "year": 2025, "grade_id": null, "through_round": "r8" }
→ { "image_url": "…", "expires_at": "…" }
```
The BetterSocial post suite already owns image composition
(`docs/BetterSocial Events Post Suite/`) — reuse it rather than adding a renderer.
Until this lands, "Post to socials" should deep-link into the post designer with
the standings pre-filled.
