"""BetterIQ — rotating scouting descriptions for danger players.

The opponent dossier flags a handful of danger batters / bowlers. Rather than
stamp every one of them with the same boilerplate ("Their leading run-scorer
this season."), we classify each into an *archetype* from their scorecard
profile and pull a flavourful one-line description from a large per-archetype
pool. The pick is deterministic per player (a stable hash of the player id), so:

* a given player always reads the same way (no flip-flop between refreshes), and
* different danger players of the same archetype read differently (variety).

Everything here is presentation only — no stats are invented. The factual line
("523 @ 47.5 this season") is appended separately by the caller.
"""
from __future__ import annotations

import hashlib

# ── batter archetypes ─────────────────────────────────────────────────────────
# Order matters in the classifier (most distinctive trait wins); the pools are
# independent so a player only ever reads from one of them.

NEMESIS_BAT = [
    "Has our number — keeps cashing in whenever he sees our bowling.",
    "A genuine bogey man for us; this is a fixture he circles on the calendar.",
    "History says he saves his best for us — plan for him to bat long.",
    "We've struggled to contain him before; the record against us is ugly.",
    "Loves the sight of our attack — he's filled his boots in past meetings.",
    "Our usual plans haven't worked on him; he owns this match-up.",
    "Whenever these two clubs meet, he tends to be the difference.",
    "Past form against us screams danger — don't let him settle.",
    "He's punished us repeatedly; treat him as the top priority wicket.",
    "A serial tormentor in this derby — get him early or pay for it.",
    "The numbers against us are alarming; he relishes this contest.",
    "Reads our bowling like a book — we need a fresh plan for him.",
    "Has feasted on us in the past, so respect the threat from ball one.",
    "If there's one man who turns up against us, it's this bloke.",
    "Our record against him is a warning — he's beaten us on his own before.",
    "He's the reason past games slipped away; shut him down first.",
    "A proven match-winner against us specifically — handle with real care.",
    "Form against us is in a different league to his form elsewhere.",
    "He's made a habit of hurting us; nothing about that has changed.",
    "Familiarity breeds runs for him here — keep him guessing.",
]

INFORM_BAT = [
    "Red hot right now — every time he walks out he looks set for a score.",
    "In the form of his life; the runs are flowing and he's brimming.",
    "Riding a purple patch — confident, busy and hard to tie down.",
    "Peaking at exactly the wrong time for us; he's seeing it like a beach ball.",
    "On a roll lately — momentum is firmly with him at the crease.",
    "Scoring for fun at the moment; he'll back himself against anyone.",
    "His recent scores are stacking up — a man playing with real freedom.",
    "Flying right now; get him cheaply or he'll bat you out of the game.",
    "Few in this comp are batting better — he's in ominous touch.",
    "Form is temporary, but his is dangerous — strike before he's in.",
    "Everything's clicking for him — timing, footwork, shot selection.",
    "He's been the in-form bat lately and shows no sign of slowing.",
    "Walking out full of runs and confidence — a real handful right now.",
    "Hot streak in full swing; nip it in the bud early.",
    "Carrying serious recent form — the kind that wins matches single-handed.",
    "Touch and tempo are spot on — he's the danger man of the moment.",
    "Runs in the bank lately means he'll come out positive and busy.",
    "On fire — the longer he's there, the worse it gets for us.",
    "His bat's doing the talking right now; quieten it fast.",
    "Playing like a man who can't get out — break the spell early.",
]

AGGRESSOR_BAT = [
    "A destroyer — when he connects, the rate goes through the roof.",
    "Lives for the boundary; give him width and the game can flip in an over.",
    "Takes the attack on from ball one — high risk, high reward, high danger.",
    "An explosive striker who can change a game in a handful of overs.",
    "Plays with serious intent — he'll look to dominate from the off.",
    "A clean hitter who clears the rope; bowl smart or he'll deposit you.",
    "Counter-attacker by nature — pressure him and he swings harder.",
    "Fast scorer who puts bowlers off their length in a hurry.",
    "He doesn't milk it, he murders it — protect the short boundaries.",
    "Aggressive intent means he scores quick but offers chances — bowl straight.",
    "A boundary machine; deny him the gaps and force the false shot.",
    "Can take the game away in ten balls — never let him get a sniff of width.",
    "Big-shot player — he'll back himself to clear any field.",
    "Strikes at a fierce rate; the new ball and the death are his playgrounds.",
    "A momentum-grabber — get on top early or he'll wrest it back violently.",
    "All power and intent; tuck him up and make him manufacture his shots.",
    "He hits through the line hard — a single mistake can cost a dozen.",
    "An attacking threat who feeds on loose deliveries — be relentless.",
    "Goes hard from the start; one tight over can dry him up.",
    "Pure ball-striker — the kind who can win a game off his own bat fast.",
]

ANCHOR_BAT = [
    "A patient accumulator — he'll bat all day if you let him settle.",
    "The glue in their order; he soaks up pressure and bats deep.",
    "Old-fashioned grafter — he won't give it away, so you must take it.",
    "Bats time beautifully; starve him and force the rare loose shot.",
    "An anchor who builds the innings around himself — break his concentration.",
    "Hard to dislodge once in — sustained pressure is the only way through.",
    "He values his wicket highly; tempt him rather than wait for a gift.",
    "Rotates strike and waits for the bad ball — patience versus patience.",
    "The rock at the top; remove him and the rest is far more exposed.",
    "Plays the long game — denying singles frustrates him into errors.",
    "A wall to bowl at — you'll have to earn every bit of his wicket.",
    "Compact and watchful; he rarely beats himself, so build the pressure.",
    "Bats within himself and cashes in late — don't let him get deep.",
    "Defence first, scoreboard second — bore him out with tight lines.",
    "The kind who carries his bat; set attacking fields and make him decide.",
    "A grinder who wears bowlers down — rotate your attack to stay fresh.",
    "Unhurried and organised; a probing spell, not a wild one, gets him.",
    "Happy to bat ugly for the cause — patience and discipline beat him.",
    "He absorbs the new ball superbly — your best chance is early movement.",
    "Methodical and unflappable; squeeze the scoring and create doubt.",
]

CONVERTER_BAT = [
    "Doesn't waste starts — once he's in, he goes big, so get him early.",
    "A serial converter; thirties become hundreds if he's given time.",
    "Punishes any let-off — the cheap wicket has to be taken first ball in.",
    "Turns good starts into match-defining knocks — don't drop him.",
    "Big-score merchant; a settled version of him is a nightmare.",
    "He cashes in when set — the danger window is right after he arrives.",
    "Once past twenty he rarely looks back — strike in the first few balls.",
    "A daddy-hundred type; let him bed in and he'll bury you.",
    "Makes starts count — every chance against him is worth gold.",
    "He builds and builds; the time to get him is before he's organised.",
    "Conversion is his calling card — a missed half-chance becomes a century.",
    "Settles quickly then accelerates — disrupt his rhythm at the start.",
    "Give him a sniff of form and he turns it into a hundred — be ruthless.",
    "His average is built on big ones; deny him the platform to launch.",
    "When he gets in, he gets greedy — get the early breakthrough.",
    "A starts-to-scores specialist; the new batter is the vulnerable one.",
    "He rarely throws away a good start, so your plan has to be front-loaded.",
    "Capable of going on for a long time — the early wicket is everything.",
    "Converts pressure into runs once set — keep him out of his comfort zone.",
    "The longer he stays, the bigger it gets — make the start count.",
]

LEADER_BAT = [
    "Their leading run-scorer — the man their innings is built around.",
    "Top of their charts; remove him and you've removed their backbone.",
    "The premier bat in this side — your single most important wicket.",
    "Carries their batting; the rest tend to follow his lead.",
    "Their go-to man with the bat — set the tone by getting him.",
    "Head and shoulders their best — the whole order leans on him.",
    "The cornerstone of their batting; everything starts with stopping him.",
    "Their standout run-maker — earn this wicket and the gate swings open.",
    "Far and away their main scorer — plan the innings around him.",
    "The batting kingpin; his dismissal changes the entire complexion.",
    "Their most reliable source of runs — make him your first priority.",
    "The name at the top of the team sheet for a reason — shut him down.",
    "Their batting revolves around him — break that and they wobble.",
    "The leading light of their order — a prized scalp worth chasing.",
    "Top dog with the bat; the rest are a level below him.",
    "Their run engine — stall it early and the scoreboard slows.",
    "The one they can't afford to lose cheaply — so make it happen.",
    "Their premier accumulator and the man to target from the first ball.",
    "He sets their standard — get him and confidence drains from the rest.",
    "Their best bat by a distance; this is the contest within the contest.",
]

STEADY_BAT = [
    "A dependable contributor who quietly does damage if ignored.",
    "Not flashy, but consistent — the kind who sneaks a useful score.",
    "A solid hand in their middle order; don't let him off the hook.",
    "Reliable rather than spectacular — still worth a clear plan.",
    "Chips in regularly; a steady threat that adds up over an innings.",
    "Workmanlike and effective — capable of an awkward, sticky knock.",
    "A useful bat who can frustrate if you switch off against him.",
    "Quietly handy — give him room and he'll happily accept it.",
    "Steady accumulator who keeps their innings ticking along.",
    "Unspectacular but durable — bowl to a plan and stay patient.",
    "A capable contributor who can punish anything loose.",
    "He won't blow you away, but he'll hang around and graft.",
    "A consistent middle-order presence — keep the pressure on.",
    "Does the unglamorous work well; respect him without overrating him.",
    "Reliable across a season — the sort who nudges a tidy thirty.",
    "A steady customer; deny him rhythm and he'll grow restless.",
    "Useful depth in their batting — make him earn everything.",
    "Honest, hard-working bat — nothing fancy, but plenty stubborn.",
    "A handy contributor who rewards any lapse in discipline.",
    "Dependable and unhurried — tighten the screws and wait.",
]

# ── bowler archetypes ─────────────────────────────────────────────────────────

NEMESIS_BOWL = [
    "Has tormented us before — our batters have struggled to read him.",
    "A genuine bogey bowler for this club; the record against us is grim.",
    "Loves bowling at us — he's run through our top order in the past.",
    "He's had our number repeatedly; counter him with a clear plan.",
    "Past meetings say he's our biggest threat with the ball.",
    "We've handed him wickets before — don't gift him the same again.",
    "A proven wrecker of our innings; treat every spell as a threat.",
    "Our batters haven't solved him yet — that has to change today.",
    "He saves his best for us — disrupt his rhythm early.",
    "History warns he can win this on his own with the ball.",
    "He's torn through us before; pick your moments against him carefully.",
    "A familiar tormentor — respect him, but find a way to score.",
    "The bowler who's hurt us most — line up a counter-plan now.",
    "We've been his bunnies in the past; flip that script early.",
    "He bowls with our wickets in mind — be proactive, not passive.",
    "Owns the match-up against us — see him off, then cash in elsewhere.",
    "A repeat offender against this side — the early overs are crucial.",
    "His record against us demands caution from the first ball.",
    "He's beaten us before with the ball; don't let him build pressure.",
    "Whenever we meet, he's in the wickets — break that pattern.",
]

MISER_BOWL = [
    "Miserly — he chokes the run rate and forces the mistake.",
    "Bowls a tight, nagging line; you won't score freely off him.",
    "An economy specialist — rotate the strike and don't try to force it.",
    "Hard to get away; the pressure he builds gets wickets at the other end.",
    "Rarely offers a loose ball — patience is the only way to handle him.",
    "He squeezes the game; refuse to take the bait and milk the others.",
    "A run-saver who suffocates innings — see him off without risk.",
    "Relentlessly accurate — the smart play is to wait him out.",
    "Gives nothing away; trying to break him is how wickets fall.",
    "Tight as they come — accept the dot balls and target the change bowlers.",
    "His containment piles on pressure — keep the scoreboard moving elsewhere.",
    "A choke-hold bowler; respect the spell and pounce later.",
    "Dries up the runs and waits for the error — deny him that satisfaction.",
    "Pinpoint control means easy runs are off the table against him.",
    "He'll bowl maidens for fun — don't let frustration cost a wicket.",
    "An economical workhorse; play him out and attack from the other end.",
    "Stingy and disciplined — singles, not strokes, are the way through.",
    "The pressure valve in their attack — survive him, then accelerate.",
    "Bowls dot after dot; reset, stay calm and bide your time.",
    "A real miser — the contest is patience, and he usually wins it.",
]

STRIKER_BOWL = [
    "A strike bowler — he hunts wickets and takes them in clusters.",
    "Genuine wicket-taking threat; he can rip out a top order fast.",
    "Attacks the stumps and the edge — every ball is a wicket ball to him.",
    "He doesn't just contain, he strikes — survive the new ball at all costs.",
    "A spell-changer; one good over from him can flip the match.",
    "Takes wickets in bunches — a quick start against him steadies the ship.",
    "His strike rate is dangerous; he'll find a way through if you let him.",
    "A natural wicket-taker — see off his opening burst with care.",
    "He bowls to take wickets, not to save runs — respect the threat.",
    "Capable of a match-winning haul; blunt him early and rotate.",
    "Always in the game — he probes for the breakthrough every ball.",
    "A penetrative bowler who thrives on movement and pace.",
    "When he's on, wickets tumble — weather the storm and cash in later.",
    "The breakthrough merchant of their attack — don't feed him chances.",
    "He can run through a side; the plan is to deny him the first one.",
    "A genuine threat with the new ball — your start sets up the innings.",
    "Lives for the wicket ball — play straight and leave well.",
    "He'll test you every delivery; concentration is the key against him.",
    "A wicket-taker who builds his own pressure — be watchful, not reckless.",
    "Dangerous in any conditions — get through his spell and the rest eases.",
]

WORKHORSE_BOWL = [
    "Their workhorse — long, accurate spells that wear batters down.",
    "Bowls big overs and keeps coming; outlast him rather than attack him.",
    "A reliable load-bearer who holds an end up all day.",
    "He'll bowl himself into the ground for the cause — patience beats him.",
    "The bankable option in their attack; consistent and hard to shift.",
    "Bowls long and tight — the smart play is to wait for the change.",
    "A stamina bowler who never lets the pressure off — stay disciplined.",
    "Always available, always accurate — pick the right balls to score.",
    "He soaks up overs and frustrates; rotate the strike and bide time.",
    "A dependable grinder — nothing loose, so manufacture nothing rash.",
    "Carries their attack with sheer volume of accurate overs.",
    "He won't tire easily — settle in for a long, careful contest.",
    "The glue of their bowling; respect the line and target the others.",
    "Steady, durable and relentless — discipline is the only answer.",
    "A true workhorse — keep him wicketless and the pressure shifts.",
    "He'll plug an end for ten overs straight; play him on merit.",
    "Consistent length and a tireless engine — see him through.",
    "The unsung hero of their attack — quietly effective if ignored.",
    "Bowls to a plan over after over; counter with one of your own.",
    "An iron-man bowler; the war of attrition is exactly what he wants.",
]

SPEARHEAD_BOWL = [
    "Their leading wicket-taker — the spearhead of the whole attack.",
    "Top of their bowling charts; everything funnels through him.",
    "Their strike weapon — see him off and the threat drops sharply.",
    "The bowler they turn to when they need a wicket — be ready for him.",
    "Their best with the ball by a distance; plan your innings around him.",
    "The tip of their spear — survive his spells and target the rest.",
    "Their main man with the ball — your key battle of the day.",
    "Carries their attack; blunt him and they look ordinary.",
    "The wicket-taker-in-chief — respect him, then go after the support.",
    "Their go-to threat — the contest with him decides plenty.",
    "Head of their attack; weather his overs and the door opens.",
    "Their premier bowler — earn a start against him and you're set.",
    "The one they lean on for breakthroughs — don't hand him momentum.",
    "Their standout bowler; the smart innings sees him off first.",
    "The leader of their attack — a clear plan for him is non-negotiable.",
    "Their biggest bowling threat — get through him and exhale.",
    "The danger man with the ball — every batter must respect his spell.",
    "Their attack's heartbeat — quieten him and they lose their rhythm.",
    "Their wicket machine; deny him early and the pressure lifts.",
    "Front and centre of their bowling — this is the match-up that matters.",
]


_BAT_POOLS = {
    "nemesis": NEMESIS_BAT,
    "in_form": INFORM_BAT,
    "aggressor": AGGRESSOR_BAT,
    "anchor": ANCHOR_BAT,
    "converter": CONVERTER_BAT,
    "leader": LEADER_BAT,
    "steady": STEADY_BAT,
}
_BOWL_POOLS = {
    "nemesis": NEMESIS_BOWL,
    "miser": MISER_BOWL,
    "striker": STRIKER_BOWL,
    "workhorse": WORKHORSE_BOWL,
    "spearhead": SPEARHEAD_BOWL,
}


def _pick(pool: list[str], seed: str) -> str:
    """Deterministically pick one phrase from ``pool`` for ``seed`` (a player id),
    so a player always reads the same and peers read differently."""
    if not pool:
        return ""
    h = int(hashlib.md5((seed or "").encode("utf-8")).hexdigest(), 16)
    return pool[h % len(pool)]


def batter_archetype(b: dict, rank: int) -> str:
    """Classify a danger batter from their scorecard profile (most distinctive
    trait wins). All inputs are optional — a thin profile falls back to steady."""
    avg = b.get("average")
    sr = b.get("strike_rate")
    vs = b.get("vs_us") or {}
    boundary = b.get("boundary_pct")
    bigs = (b.get("fifties") or 0) + (b.get("hundreds") or 0)
    if vs.get("average") and vs["average"] >= 35 and (avg is None or vs["average"] >= avg):
        return "nemesis"
    if b.get("form") == "hot":
        return "in_form"
    if (sr is not None and sr >= 110) or (boundary is not None and boundary >= 60):
        return "aggressor"
    if sr is not None and sr <= 70 and avg is not None and avg >= 30:
        return "anchor"
    if bigs >= 2:
        return "converter"
    if rank == 0:
        return "leader"
    return "steady"


def bowler_archetype(b: dict, rank: int) -> str:
    """Classify a danger bowler from their scorecard profile."""
    econ = b.get("economy")
    sr = b.get("strike_rate")
    overs = b.get("overs") or 0
    vs = b.get("vs_us") or {}
    if vs.get("wickets") and vs["wickets"] >= 3:
        return "nemesis"
    if econ is not None and econ < 3.8:
        return "miser"
    if (sr is not None and sr <= 24) or (b.get("five_fors") or 0) >= 1:
        return "striker"
    if overs >= 40:
        return "workhorse"
    if rank == 0:
        return "spearhead"
    # Default: lean on the most useful remaining signal.
    if econ is not None and econ < 4.6:
        return "miser"
    return "striker"


def batter_note(b: dict, rank: int) -> str:
    """A rotating one-line scouting description for a danger batter."""
    arch = batter_archetype(b, rank)
    return _pick(_BAT_POOLS.get(arch, STEADY_BAT), b.get("player_id") or b.get("name") or "")


def bowler_note(b: dict, rank: int) -> str:
    """A rotating one-line scouting description for a danger bowler."""
    arch = bowler_archetype(b, rank)
    return _pick(_BOWL_POOLS.get(arch, SPEARHEAD_BOWL), b.get("player_id") or b.get("name") or "")
