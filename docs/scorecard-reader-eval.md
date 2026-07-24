# Scorecard reader: formats it knows, and how to train it

The Upload Historical Scorecard reader (`backend/app/services/scorecard_ocr.py`)
is a single vision-model call. It has no memory and never learns from uploads, so
"training" it means three things:

1. Teaching the prompt about card layouts and scorer conventions.
2. Extending the schema so everything on a card has somewhere to land.
3. Measuring every change against a set of verified cards (the eval below), so we
   know a tweak helped rather than hoping it did.

## Formats the prompt knows (Jul 2026)

- **Australian scorebook (two-page WACA-style book).** One innings per page:
  batsman block with scoring strokes, fall of wickets, progress-score grid,
  bowling analysis grid. The reader trusts the written TOTAL column over its own
  stroke count, and counts 4s/6s from the strokes.
- **Association official match summary form** (e.g. Toowoomba Cricket
  Association). One page, one club's side of the whole match: their batting,
  their bowlers (often wickets and runs only), an OWN CATCHES column with the
  keeper marked W/K, a stumpings box, and the opposition as a bare totals line
  like "10/111". The opposition innings imports with totals and no batting rows.
- **Anything else** (typed sheets, hand-ruled layouts): it reads what is present
  and says what it assumed in the reader notes.

Conventions it is warned about: tally strokes in extras boxes (two strokes is 2,
not 11), wickets-first scores ("7/164"), two-digit years resolving to the 1900s,
two-day matches (first day is the match date), 8-ball overs on pre-1980 cards
(`match.balls_per_over`), and inferring a result only when the scores decide it
(flagged `result_inferred` so the review screen says to check it).

## Names: cross-reference the whole card

The single biggest handwriting win. The same person is written many times on a
card — in the batting order, in the bowling analysis, as a catcher in a "c Smith"
dismissal, as the wicket-taker in a "b Jones", and in the fall-of-wickets — and
the legibility varies wildly between them. A bowler that reads "S Willingslow" in
a cramped how-out column is plainly "G Wittingslow" in the bowling analysis right
below it; "T Houser" on one page is "I Heuser" on the next. The prompt tells the
model to read *every* occurrence and use the clearest one as the true spelling,
then use that one spelling everywhere. The two authorities:

- The **bowling analysis** is the authority for bowler names. A dismissing bowler
  is always one of the analysed bowlers (you can't be out to someone who didn't
  bowl), so a "b X" reads as whichever analysis bowler it matches.
- The **batting order** is the authority for batter names, so a fall-of-wickets
  or fielder name that is a known player takes that player's spelling.

It must NOT collapse two different people who merely share a surname ("N Ziebell"
and "R Ziebell" are different players). `reconcile()` backs this up with an
advisory: a dismissal bowler whose surname doesn't fuzzy-match any bowler in that
innings' analysis is flagged for the reviewer, which is the exact
"S Willingslow" → "G Wittingslow" case.

## Adding a verified card to the eval set

Keep a local folder (not in the repo; the scans are big and carry names), one
sub-folder per match, containing the photos or the PDF plus an `expected.json`
with the values as they *should* read. The full shape is documented at the top of
`backend/app/scripts/scorecard_eval.py`; a minimal truth file is fine, since only
the keys you include are scored:

```json
{
  "our_club": "Metropolitans",
  "match": { "date": "1976-10-02", "balls_per_over": 8 },
  "innings": [
    {
      "innings_number": 1, "batting_team": "Metropolitans", "is_our_team": true,
      "total_runs": 172, "total_wickets": 10,
      "batting": [
        { "name": "G Evans", "runs": 73, "how_out": "caught", "bowler": "I Houser" }
      ],
      "bowling": [
        { "name": "R Brownhalls", "overs": 13, "maidens": 3, "runs": 46, "wickets": 2 }
      ]
    }
  ]
}
```

The most useful truth files are complete ones: every batter's name, runs and
dismissal, every bowler's figures, extras, fall of wickets. Verify against the
physical card, not against what the reader said.

## Running the eval

```bash
cd backend
python -m app.scripts.scorecard_eval /path/to/scorecard-eval-cases
# or one case:
python -m app.scripts.scorecard_eval /path/to/scorecard-eval-cases 1976-10-02-railways
```

Needs `ANTHROPIC_API_KEY` set (same settings as the server). Each run costs real
model calls, roughly the same as uploading each card once.

It prints a per-case field accuracy, every field-level mismatch, and an overall
score. Workflow for any reader change: run the eval, make the prompt/schema/model
change, run it again, keep the change only if the score went up (or a targeted
mismatch went away without new ones appearing).
