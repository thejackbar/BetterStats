# Sponsor prominence, and a sponsor with naming rights on a ground

Written up for sign-off, not built. Two things Rockingham Mandurah asked for:

1. Their sponsors should be more prominent on the social post templates.
2. Two of their sponsors hold **naming rights on specific grounds** — Retravision
   on the main ground, Training U on another — and the posts should say so.

The question put with them was whether this needs **additional templates**. Mostly
it does not, and the reason is worth reading before anything is designed.

## What the code actually does today

Checked rather than assumed, because "add more templates" is the answer only if
the existing ones are already doing everything they can.

- **`org_sponsors` holds a name, a website, a logo and a display order, and
  nothing else.** There is no tier, no contract dates, no association with a
  ground. Every sponsor is the same size as every other sponsor.
- **There are 62 exported template components** across `cricket-templates.jsx`,
  `round-templates.jsx`, `event-templates.jsx` and `launch-templates.jsx`. A
  sponsor reaches **two** of those families:
  - `ScSponsorFooter` (`cricket-templates.jsx`) — a 56px bar pinned to the
    bottom of the scorecard posts. `const slots = [0, 1]`: **exactly two, always,
    whatever the club holds.**
  - `SponsorFooter` (`round-templates.jsx`) — the fixtures/results roundups.
    It renders whatever array it is handed, but `AdminSocialPost.jsx` only ever
    fills two (`sponsors: [{}, {}]`, then `[0, 1].map(...)`).
  - The **event templates** take `event.sponsor` as a plain **string** and draw
    it as a small uppercase watermark line. A sponsor with a logo cannot show one
    on any event post at all.
- **Every other template — the whole team-sheet family, the captain and
  match-day cards, the launch set — has no sponsor slot of any kind.**

So the shortfall is not template COUNT. It is that a sponsor is a logo in one of
two identical footer boxes at the bottom of a post, on the minority of templates
that have a footer, and that a club's principal partner is drawn at the same size
as its smallest one. **A club that adds three new templates gets three more
footers.**

## The venue naming right is a different fact again

`games.venue`, `fixtures.venue` and `manual_games.venue` are all **free text**,
carried through from Cricket Australia. There is no venue entity anywhere in the
schema; `facilities` exists (Facilities & Assets) but it holds the club's OWN
property — a clubroom, nets, a shed — and never joins to the venue string a
fixture arrives with. So there is nothing today that could know "Lark Hill is
Retravision's ground".

## What to build instead

### 1. A sponsor has a tier

`org_sponsors.tier` — `principal` | `major` | `supporting` | `community`, with
`display_order` ordering within a tier. This is the change that reaches all 62
templates rather than three, because a template can then ask for **the principal
partner** and give it a size a footer never could:

- **the principal gets a masthead position** — a "PRESENTED BY <logo>" band at
  the top of a match-day post, or the pre-match card's own strapline;
- **majors keep the footer**, which is what a footer is for;
- **supporting and community sponsors** go on a wall post (below) rather than
  being shrunk until nobody can read them.

One helper — `sponsorSlots(sponsors, { count, tier })` — so a template asks for
what it can fit and every template answers the question the same way. Two
templates deciding for themselves which sponsor is the big one is how two posts
in the same round end up disagreeing about who the principal partner is.

### 2. A sponsor can hold naming rights on a ground

`sponsor_venues` — `sponsor_id`, the venue name, and the naming-rights name to
print. Deliberately a **table, not a column on the sponsor**: Rockingham Mandurah
already have two sponsors on two grounds, and a club with a second ground and one
sponsor across both is just as ordinary.

**The club PICKS the venue, it never types it.** The obvious design is a text
field and a fuzzy match against the fixture's venue string, and it is the wrong
one — CA's spelling is the club's spelling only by luck, and a naming right that
silently fails to match is worse than no feature, because nobody can see that it
did not fire. Instead: offer the club the **distinct venue strings its own
fixtures and games already carry** (`SELECT DISTINCT venue`), so the value stored
is byte-for-byte what a post will be matched against. A ground the club has never
played at cannot be named, which is correct.

Then, wherever a template prints a venue, it prints the sponsored name. Three
things need deciding before this is built, and none of them is ours to decide:

- **Does the sponsored name REPLACE the ground's name or sit beside it?**
  "Retravision Oval" versus "Lark Hill Sportsplex, presented by Retravision".
  Associations and councils sometimes have a view about this.
- **Does it apply to an AWAY team's post at that ground?** We only ever generate
  the club's own posts, so in practice this is "does it apply when we are the away
  side at our own ground".
- **Do naming rights expire?** A sponsorship term ends. If they do,
  `sponsor_venues` needs `from_date` / `to_date` and a post about a match from two
  seasons ago has to use the name that applied THEN, not the name that applies
  now — which is a different and larger piece of work than the current-season case.

### 3. Two or three genuinely sponsor-led templates

Worth adding, but only for the posts a footer can never be, where the SUBJECT of
the post is the sponsor:

- **A sponsor wall** — "Our 25/26 partners", every sponsor at its tier's size.
  This is what the supporting and community tiers are actually for.
- **A single-sponsor thank-you / spotlight** — one logo, one line about them, the
  club's colours. A club posts this when a sponsor signs or renews.
- **"Today at [named ground]"** — a match-day card built around the naming-rights
  sponsor, which is the one post that makes a ground sponsorship visibly worth
  paying for.

### 4. The event templates should take a sponsor, not a sponsor's name

`event.sponsor` becomes the same sponsor object the rest of the app passes
around, so an event post can draw a logo. Today a club's quiz night can name its
pizza sponsor and cannot show it.

## Deliberately not proposed

- **No per-template sponsor configuration.** A club should set its tiers once and
  have every post obey them; a per-post picker is how a club ends up with its
  principal partner missing from half a round's posts.
- **No automatic sponsor rotation.** Fair on paper, and it means a club cannot
  tell a sponsor which posts they appeared on.
- **Nothing that changes what a sponsor's logo IS.** `org_sponsors.logo_data` is
  already served from our own domain and already renders; the problem is where it
  is drawn and how big, not what it is.

## Open question worth putting to Rockingham Mandurah

Whether "more prominent" means **bigger on the posts they already make**, or
**posts that are about the sponsors**. The two lead to different work, and the
answer is probably both — but the tiering is the half that pays for itself across
every template, so it should go first either way.
