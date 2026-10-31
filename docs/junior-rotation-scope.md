# Junior Rotation: scope

Status: built in v9.137.0 (migration 381). This is the brief, the decisions made while scoping it, what shipped and what did not.

## The ask

A first-time tee ball coach wanted a random batting and fielding lineup generator that remembers who has fielded and batted where, so it comes out even for everyone. The coach loads about 12 kids, they go into a random batting order each week, that order is remembered so next week is randomised again, and the same goes for the key fielding positions (the bases and so on). With 11 players and 9 fielding positions, two kids rest each change, and the resting has to be shared out too.

## Decisions

| Question | Decision |
|---|---|
| Where do the kids come from? | Typed names, saved against a group. The tool is meant to become a product of its own, so nothing is keyed on the club's `players` table. A tee ball side is often not on Cricket Australia at all. |
| What gets rotated? | An editable list of field positions per group, with a Tee ball and a Junior cricket starting set. Positions marked key are shared out first. |
| What does "random but fair" mean? | Random every week, weighted by history. One setting (0 to 100) says how hard a draw leans on history. At 0 it is a plain shuffle. It is never an exact answer, because an exact answer is one a parent could work out from last week. |
| Who sees it, and where? | A coach screen in BetterSelect, a one-page print sheet, a parent link, and an optional tie to a fixture. |
| Where does it sit in the product? | Under Club Life in BetterSelect, entitled by the BetterSelect module, with its own access item (`select_rotation`). Built so it can be lifted out. |

## What shipped

**Coach screens** (`/admin/betterselect/rotation`):
- The list of groups, with a create form (name, starting positions, paste the kids' names).
- Game day: set up a game (date, label, optional fixture, who is here), generate, then edit by hand. Pick a kid for a position and whoever held it swaps in. Move kids up and down the batting order. Untick a kid who went home, add a late arrival. Re-roll everything, only the batting order or only the field. Lock the game, unlock it, print it, delete a draft.
- Kids: add by pasting names, rename, keep a kid out of chosen positions, mark a kid as left (and bring them back).
- Season: games, led off, batted last, average batting spot, rests, key turns and turns at each position, from locked games only, with a sentence saying how even it is.
- Settings: name, field changes per game (1 to 6), the fairness setting, whether the group bats, the positions, the parent link and archive.

**Print sheet** (`/admin/betterselect/rotation/:group/print/:round`): its own page, light theme, no site navigation, Print button kept off the paper.

**Parent link** (`/rotation/:token`): off by default. Locked games only, last eight. First name and last initial unless surnames are switched on. No ids, notes or other groups in the response. A bad token, a switched-off link, an archived group and a club without BetterSelect all give the same 404.

## How the draw works

For each game, in order:

1. **Batting order.** Drawn one slot at a time. Each kid's chance for a slot leans on where they usually bat (a kid who usually bats late is likelier to lead off) and against handing the first or last slot to a kid who has had it before.
2. **Who rests.** With more kids than positions, the spare kids sit out. Several random candidates are drawn and the one that rests the kids who have rested least wins, then is polished with swaps.
3. **Who goes where.** Several random candidates, scored on how often each kid has already had that position (squared, key positions counted double, plus the kid's total key turns), polished with swaps. A position a kid is to be kept out of costs more than anything a season can build up, so it is only broken when there is no other way.

With several field changes in a game, each change builds on the one before it, so the kid who rested first is not the one to rest second. A kid with no history is neutral, never "owed".

Measured over 40 seeded 12-game seasons for each of 11 kids on 1 change, 11 on 3, 9 on 1 and 13 on 2: rests never differ by more than one, key-position turns never by more than two, and the spread of average batting positions is well tighter than a plain shuffle's. From one fixed history, 80 draws give dozens of different batting orders and more than three different openers.

## Data

Three tables, raw SQL, no ORM model, `services/rotation_ddl.py` shared by the migration and the lifespan:

- `rotation_groups`: name, positions (JSON, each with a stable id), field changes, fairness, bats, parent link token and switches, archived.
- `rotation_players`: typed names, positions to avoid, note, `former_at`. Never deleted.
- `rotation_rounds`: date, label, optional fixture (set null if the fixture goes), who is here, batting order, field per change, warnings, status, version.

Nothing refers to `players`, `grades` or `seasons`, so a player merge cannot touch it. Tallies are derived from locked rounds on read and never stored.

## Permissions

`SELECT_ROTATION` or the BetterSelect umbrella, behind `require_module("select")`. `select.rotation` is an access item in `services/access.py`, so a coach can be given Junior Rotation alone. The route-access audit passes with no new open routes.

## How it was verified

- `backend/verification/verify_junior_rotation.py`: 103 checks on real Postgres through the shipped route bodies. Includes the evenness and randomness claims above, a fairness-0 control that must fail the evenness checks, draft versus locked, version conflicts, hand-edit validation, one club not seeing another's data, and every way the parent link can be a 404.
- `frontend/verification/verify_junior_rotation_browser.mjs`: 70 checks in Chromium with the API stubbed. Asserts the exact request each control sends, that a locked game is read only, that a conflict shows the other version, the print sheet and the parent page, and no horizontal overflow at 390px on every screen. It caught two faults before they shipped.
- `audit_route_access` and `verify_user_access.py` (124) for the new capability.

## Not built, and next

- A drag handle on the batting order (arrows only for now).
- A field diagram for the print sheet and parent page (a list for now).
- Per-kid batting rules (always last, never first) and bowling overs.
- Importing names from the club roster. Typing them is the deliberate default, but a club that has them in BetterSelect could offer a one-tap import.
- Telling parents: the link has to be shared by the coach. A BetterComms send of the lineup would be the natural next step.
- Standing alone as a product: its own sign-in and billing, a home outside BetterSelect, and a public marketing page. Everything above is built so none of that needs the data model to change.

## Questions for you

1. The Tee ball and Junior cricket starting positions are a first guess (nine each, key marked). Do you want different defaults, or a Softball and Kanga set as well?
2. Should the parent link also offer a "find my kid" highlight, or is the full list fine?
3. For a standalone product, do you want the first version's group to be shareable between two coaches (an assistant coach with edit access), or one owner per group?
