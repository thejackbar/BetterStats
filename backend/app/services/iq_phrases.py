"""BetterIQ — rotating scouting descriptions + plans for danger players.

The opponent dossier flags a handful of danger batters / bowlers (and keeper-
batters). Rather than stamp every one with the same boilerplate, we classify
each into an *archetype* from their scorecard profile and pull a flavourful
one-line description — and a separate actionable *plan* — from large per-archetype
pools. The pick is deterministic per player (a stable hash of the player id), so:

* a given player always reads the same way (no flip-flop between refreshes), and
* different players of the same archetype read differently (variety).

Everything here is presentation only — no stats are invented. The factual line
("523 @ 47.5 this season") is appended separately by the caller. The plan pools
are keyed first on a dominant *dismissal mode* (the most actionable signal, e.g.
"nicks off" → bowl a tight off-stump line) and otherwise on the archetype.
"""
from __future__ import annotations

import hashlib

# ════════════════════════════════════════════════════════════════════════════
#  BATTER DESCRIPTIONS  (archetype pools)
# ════════════════════════════════════════════════════════════════════════════

NEMESIS_BAT = [
    "Has our number — keeps cashing in whenever they see our bowling.",
    "A genuine bogey player for us; this is a fixture they circle on the calendar.",
    "History says they save their best for us — plan for them to bat long.",
    "We've struggled to contain them before; the record against us is ugly.",
    "Loves the sight of our attack — they've filled their boots in past meetings.",
    "Our usual plans haven't worked on them; they own this match-up.",
    "Whenever these two clubs meet, they tend to be the difference.",
    "Past form against us screams danger — don't let them settle.",
    "They've punished us repeatedly; treat them as the top priority wicket.",
    "A serial tormentor in this derby — get them early or pay for it.",
    "The numbers against us are alarming; they relish this contest.",
    "Reads our bowling like a book — we need a fresh plan for them.",
    "Has feasted on us in the past, so respect the threat from ball one.",
    "If there's one player who turns up against us, it's this one.",
    "Our record against them is a warning — they've beaten us on their own before.",
    "They're the reason past games slipped away; shut them down first.",
    "A proven match-winner against us specifically — handle with real care.",
    "Form against us is in a different league to their form elsewhere.",
    "They've made a habit of hurting us; nothing about that has changed.",
    "Familiarity breeds runs for them here — keep them guessing.",
]

INFORM_BAT = [
    "Red hot right now — every time they walk out they look set for a score.",
    "In the form of their life; the runs are flowing and they're brimming.",
    "Riding a purple patch — confident, busy and hard to tie down.",
    "Peaking at exactly the wrong time for us; they're seeing it like a beach ball.",
    "On a roll lately — momentum is firmly with them at the crease.",
    "Scoring for fun at the moment; they'll back themselves against anyone.",
    "Their recent scores are stacking up — a batter playing with real freedom.",
    "Flying right now; get them cheaply or they'll bat you out of the game.",
    "Few in this comp are batting better — they're in ominous touch.",
    "Form is temporary, but theirs is dangerous — strike before they're in.",
    "Everything's clicking for them — timing, footwork, shot selection.",
    "They've been the in-form bat lately and show no sign of slowing.",
    "Walking out full of runs and confidence — a real handful right now.",
    "Hot streak in full swing; nip it in the bud early.",
    "Carrying serious recent form — the kind that wins matches single-handed.",
    "Touch and tempo are spot on — they're the danger player of the moment.",
    "Runs in the bank lately means they'll come out positive and busy.",
    "On fire — the longer they're there, the worse it gets for us.",
    "Their bat's doing the talking right now; quieten it fast.",
    "Playing like someone who can't get out — break the spell early.",
]

AGGRESSOR_BAT = [
    "A destroyer — when they connect, the rate goes through the roof.",
    "Lives for the boundary; give them width and the game can flip in an over.",
    "Takes the attack on from ball one — high risk, high reward, high danger.",
    "An explosive striker who can change a game in a handful of overs.",
    "Plays with serious intent — they'll look to dominate from the off.",
    "A clean hitter who clears the rope; bowl smart or they'll deposit you.",
    "Counter-attacker by nature — pressure them and they swing harder.",
    "Fast scorer who puts bowlers off their length in a hurry.",
    "They don't milk it, they murder it — protect the short boundaries.",
    "Aggressive intent means they score quick but offer chances — bowl straight.",
    "A boundary machine; deny them the gaps and force the false shot.",
    "Can take the game away in ten balls — never let them get a sniff of width.",
    "Big-shot player — they'll back themselves to clear any field.",
    "Strikes at a fierce rate; the new ball and the death are their playgrounds.",
    "A momentum-grabber — get on top early or they'll wrest it back violently.",
    "All power and intent; tuck them up and make them manufacture their shots.",
    "They hit through the line hard — a single mistake can cost a dozen.",
    "An attacking threat who feeds on loose deliveries — be relentless.",
    "Goes hard from the start; one tight over can dry them up.",
    "Pure ball-striker — the kind who can win a game off their own bat fast.",
]

ANCHOR_BAT = [
    "A patient accumulator — they'll bat all day if you let them settle.",
    "The glue in their order; they soak up pressure and bat deep.",
    "Old-fashioned grafter — they won't give it away, so you must take it.",
    "Bats time beautifully; starve them and force the rare loose shot.",
    "An anchor who builds the innings around themselves — break their concentration.",
    "Hard to dislodge once in — sustained pressure is the only way through.",
    "They value their wicket highly; tempt them rather than wait for a gift.",
    "Rotates strike and waits for the bad ball — patience versus patience.",
    "The rock at the top; remove them and the rest is far more exposed.",
    "Plays the long game — denying singles frustrates them into errors.",
    "A wall to bowl at — you'll have to earn every bit of their wicket.",
    "Compact and watchful; they rarely beat themselves, so build the pressure.",
    "Bats within themselves and cashes in late — don't let them get deep.",
    "Defence first, scoreboard second — bore them out with tight lines.",
    "The kind who carries their bat; set attacking fields and make them decide.",
    "A grinder who wears bowlers down — rotate your attack to stay fresh.",
    "Unhurried and organised; a probing spell, not a wild one, gets them.",
    "Happy to bat ugly for the cause — patience and discipline beat them.",
    "They absorb the new ball superbly — your best chance is early movement.",
    "Methodical and unflappable; squeeze the scoring and create doubt.",
]

CONVERTER_BAT = [
    "Doesn't waste starts — once they're in, they go big, so get them early.",
    "A serial converter; thirties become hundreds if they're given time.",
    "Punishes any let-off — the cheap wicket has to be taken first ball in.",
    "Turns good starts into match-defining knocks — don't drop them.",
    "Big-score merchant; a settled version of them is a nightmare.",
    "They cash in when set — the danger window is right after they arrive.",
    "Once past twenty they rarely look back — strike in the first few balls.",
    "A daddy-hundred type; let them bed in and they'll bury you.",
    "Makes starts count — every chance against them is worth gold.",
    "They build and build; the time to get them is before they're organised.",
    "Conversion is their calling card — a missed half-chance becomes a century.",
    "Settles quickly then accelerates — disrupt their rhythm at the start.",
    "Give them a sniff of form and they turn it into a hundred — be ruthless.",
    "Their average is built on big ones; deny them the platform to launch.",
    "When they get in, they get greedy — get the early breakthrough.",
    "A starts-to-scores specialist; the new batter is the vulnerable one.",
    "They rarely throw away a good start, so your plan has to be front-loaded.",
    "Capable of going on for a long time — the early wicket is everything.",
    "Converts pressure into runs once set — keep them out of their comfort zone.",
    "The longer they stay, the bigger it gets — make the start count.",
]

LEADER_BAT = [
    "Their leading run-scorer — the player their innings is built around.",
    "Top of their charts; remove them and you've removed their backbone.",
    "The premier bat in this side — your single most important wicket.",
    "Carries their batting; the rest tend to follow their lead.",
    "Their go-to batter — set the tone by getting them.",
    "Head and shoulders their best — the whole order leans on them.",
    "The cornerstone of their batting; everything starts with stopping them.",
    "Their standout run-maker — earn this wicket and the gate swings open.",
    "Far and away their main scorer — plan the innings around them.",
    "The batting kingpin; their dismissal changes the entire complexion.",
    "Their most reliable source of runs — make them your first priority.",
    "The name at the top of the team sheet for a reason — shut them down.",
    "Their batting revolves around them — break that and they wobble.",
    "The leading light of their order — a prized scalp worth chasing.",
    "Top dog with the bat; the rest are a level below them.",
    "Their run engine — stall it early and the scoreboard slows.",
    "The one they can't afford to lose cheaply — so make it happen.",
    "Their premier accumulator and the player to target from the first ball.",
    "They set their standard — get them and confidence drains from the rest.",
    "Their best bat by a distance; this is the contest within the contest.",
]

# Keeper-batters — a keeper who can bat. Detected from real fielding data
# (wicketkeeper catches / stumpings), so these only fire for an actual keeper.
KEEPER_BAT = [
    "Their keeper-batter — busy, sharp between the wickets and never out of the game.",
    "Keeper who can really bat; they're used to building an innings under pressure.",
    "A wicketkeeper-batter — expect quick singles and a cool head when it tightens.",
    "Keeps and bats up the order; a genuine two-in-one threat to plan for.",
    "Their keeper with the bat in hand — scrappy, street-smart and hard to shift.",
    "A keeper-bat who reads the game well; they'll milk you if you let them settle.",
    "Wicketkeeper-batter who thrives on rotating the strike — cut off their singles.",
    "They keep wickets and anchor the innings; don't underestimate their batting.",
    "A busy keeper-bat — quick feet, soft hands, and a knack for the awkward knock.",
    "Their keeper bats with real nous; pressure them before they get going.",
    "Keeper-batter who's seen every situation from behind the stumps — very streetwise.",
    "A dual threat: takes their chances with the gloves and grafts runs with the bat.",
    "Their keeper can bat properly — treat them as a top-order wicket, not a tail-ender.",
    "Nimble keeper-bat; they'll nudge, nurdle and run you ragged for ones and twos.",
    "A wicketkeeper who bats with the game's tempo in mind — calm under pressure.",
    "Keeper-batter with a high cricket IQ; they rarely get themselves out cheaply.",
    "Their keeper is a real batting asset — bowl to a plan, don't gift them width.",
    "A scrapping keeper-bat who finds a way; dot balls are your friend against them.",
    "Keeps tidily and bats with intent — a genuine all-round headache.",
    "Their keeper bats like a specialist; the keeper tag undersells the threat.",
    "A keeper-batter who loves a chase — composed and good at pacing a run-down.",
    "Sharp keeper, sharper between the wickets — they turn ones into twos.",
    "Their keeper-bat is the heartbeat of the side; vocal, busy and combative.",
    "A keeper who bats deep into the innings — patience will be needed.",
]

STEADY_BAT = [
    "A dependable contributor who quietly does damage if ignored.",
    "Not flashy, but consistent — the kind who sneaks a useful score.",
    "A solid hand in their middle order; don't let them off the hook.",
    "Reliable rather than spectacular — still worth a clear plan.",
    "Chips in regularly; a steady threat that adds up over an innings.",
    "Workmanlike and effective — capable of an awkward, sticky knock.",
    "A useful bat who can frustrate if you switch off against them.",
    "Quietly handy — give them room and they'll happily accept it.",
    "Steady accumulator who keeps their innings ticking along.",
    "Unspectacular but durable — bowl to a plan and stay patient.",
    "A capable contributor who can punish anything loose.",
    "They won't blow you away, but they'll hang around and graft.",
    "A consistent middle-order presence — keep the pressure on.",
    "Does the unglamorous work well; respect them without overrating them.",
    "Reliable across a season — the sort who nudges a tidy thirty.",
    "A steady customer; deny them rhythm and they'll grow restless.",
    "Useful depth in their batting — make them earn everything.",
    "Honest, hard-working bat — nothing fancy, but plenty stubborn.",
    "A handy contributor who rewards any lapse in discipline.",
    "Dependable and unhurried — tighten the screws and wait.",
]

# ════════════════════════════════════════════════════════════════════════════
#  BOWLER DESCRIPTIONS  (archetype pools)
# ════════════════════════════════════════════════════════════════════════════

NEMESIS_BOWL = [
    "Has tormented us before — our batters have struggled to read them.",
    "A genuine bogey bowler for this club; the record against us is grim.",
    "Loves bowling at us — they've run through our top order in the past.",
    "They've had our number repeatedly; counter them with a clear plan.",
    "Past meetings say they're our biggest threat with the ball.",
    "We've handed them wickets before — don't gift them the same again.",
    "A proven wrecker of our innings; treat every spell as a threat.",
    "Our batters haven't solved them yet — that has to change today.",
    "They save their best for us — disrupt their rhythm early.",
    "History warns they can win this on their own with the ball.",
    "They're torn through us before; pick your moments against them carefully.",
    "A familiar tormentor — respect them, but find a way to score.",
    "The bowler who's hurt us most — line up a counter-plan now.",
    "We've been their bunnies in the past; flip that script early.",
    "They bowl with our wickets in mind — be proactive, not passive.",
    "Owns the match-up against us — see them off, then cash in elsewhere.",
    "A repeat offender against this side — the early overs are crucial.",
    "Their record against us demands caution from the first ball.",
    "They've beaten us before with the ball; don't let them build pressure.",
    "Whenever we meet, they're in the wickets — break that pattern.",
]

MISER_BOWL = [
    "Miserly — they choke the run rate and force the mistake.",
    "Bowls a tight, nagging line; you won't score freely off them.",
    "An economy specialist — rotate the strike and don't try to force it.",
    "Hard to get away; the pressure they build gets wickets at the other end.",
    "Rarely offers a loose ball — patience is the only way to handle them.",
    "They squeeze the game; refuse to take the bait and milk the others.",
    "A run-saver who suffocates innings — see them off without risk.",
    "Relentlessly accurate — the smart play is to wait them out.",
    "Gives nothing away; trying to break them is how wickets fall.",
    "Tight as they come — accept the dot balls and target the change bowlers.",
    "Their containment piles on pressure — keep the scoreboard moving elsewhere.",
    "A choke-hold bowler; respect the spell and pounce later.",
    "Dries up the runs and waits for the error — deny them that satisfaction.",
    "Pinpoint control means easy runs are off the table against them.",
    "They'll bowl maidens for fun — don't let frustration cost a wicket.",
    "An economical workhorse; play them out and attack from the other end.",
    "Stingy and disciplined — singles, not strokes, are the way through.",
    "The pressure valve in their attack — survive them, then accelerate.",
    "Bowls dot after dot; reset, stay calm and bide your time.",
    "A real miser — the contest is patience, and they usually win it.",
]

STRIKER_BOWL = [
    "A strike bowler — they hunt wickets and take them in clusters.",
    "Genuine wicket-taking threat; they can rip out a top order fast.",
    "Attacks the stumps and the edge — every ball is a wicket ball to them.",
    "They don't just contain, they strike — survive the new ball at all costs.",
    "A spell-changer; one good over from them can flip the match.",
    "Takes wickets in bunches — a quick start against them steadies the ship.",
    "Their strike rate is dangerous; they'll find a way through if you let them.",
    "A natural wicket-taker — see off their opening burst with care.",
    "They bowl to take wickets, not to save runs — respect the threat.",
    "Capable of a match-winning haul; blunt them early and rotate.",
    "Always in the game — they probe for the breakthrough every ball.",
    "A penetrative bowler who thrives on movement and pace.",
    "When they're on, wickets tumble — weather the storm and cash in later.",
    "The breakthrough merchant of their attack — don't feed them chances.",
    "They can run through a side; the plan is to deny them the first one.",
    "A genuine threat with the new ball — your start sets up the innings.",
    "Lives for the wicket ball — play straight and leave well.",
    "They'll test you every delivery; concentration is the key against them.",
    "A wicket-taker who builds their own pressure — be watchful, not reckless.",
    "Dangerous in any conditions — get through their spell and the rest eases.",
]

WORKHORSE_BOWL = [
    "Their workhorse — long, accurate spells that wear batters down.",
    "Bowls big overs and keeps coming; outlast them rather than attack them.",
    "A reliable load-bearer who holds an end up all day.",
    "They'll bowl themselves into the ground for the cause — patience beats them.",
    "The bankable option in their attack; consistent and hard to shift.",
    "Bowls long and tight — the smart play is to wait for the change.",
    "A stamina bowler who never lets the pressure off — stay disciplined.",
    "Always available, always accurate — pick the right balls to score.",
    "They soak up overs and frustrate; rotate the strike and bide time.",
    "A dependable grinder — nothing loose, so manufacture nothing rash.",
    "Carries their attack with sheer volume of accurate overs.",
    "They won't tire easily — settle in for a long, careful contest.",
    "The glue of their bowling; respect the line and target the others.",
    "Steady, durable and relentless — discipline is the only answer.",
    "A true workhorse — keep them wicketless and the pressure shifts.",
    "They'll plug an end for ten overs straight; play them on merit.",
    "Consistent length and a tireless engine — see them through.",
    "The unsung hero of their attack — quietly effective if ignored.",
    "Bowls to a plan over after over; counter with one of your own.",
    "An iron-willed bowler; the war of attrition is exactly what they want.",
]

SPEARHEAD_BOWL = [
    "Their leading wicket-taker — the spearhead of the whole attack.",
    "Top of their bowling charts; everything funnels through them.",
    "Their strike weapon — see them off and the threat drops sharply.",
    "The bowler they turn to when they need a wicket — be ready for them.",
    "Their best with the ball by a distance; plan your innings around them.",
    "The tip of their spear — survive their spells and target the rest.",
    "Their main weapon with the ball — your key battle of the day.",
    "Carries their attack; blunt them and they look ordinary.",
    "The wicket-taker-in-chief — respect them, then go after the support.",
    "Their go-to threat — the contest with them decides plenty.",
    "Head of their attack; weather their overs and the door opens.",
    "Their premier bowler — earn a start against them and you're set.",
    "The one they lean on for breakthroughs — don't hand them momentum.",
    "Their standout bowler; the smart innings sees them off first.",
    "The leader of their attack — a clear plan for them is non-negotiable.",
    "Their biggest bowling threat — get through them and exhale.",
    "The danger bowler — every batter must respect their spell.",
    "Their attack's heartbeat — quieten them and they lose their rhythm.",
    "Their wicket machine; deny them early and the pressure lifts.",
    "Front and centre of their bowling — this is the match-up that matters.",
]

# Wickets but expensive — the boom-or-bust threat (strikes, but leaks runs while
# hunting). Detectable from scorecard wickets + economy alone.
BOOMBUST_BOWL = [
    "Boom or bust — they take wickets but leak runs hunting them.",
    "A wicket-taker who pays for it; punish the bad balls, respect the good one.",
    "High-risk, high-reward bowler — plenty to score off, but they'll strike too.",
    "They buy their wickets — there are runs on offer if you survive the danger ball.",
    "Attacking but expensive; cash in on the loose stuff, watch the wicket ball.",
    "Gives you chances to score and chances to get out in the same over.",
    "A feast-or-famine bowler — milk the width, but don't take them on blindly.",
    "They'll go searching for wickets and spray a few — be patient for the four-ball.",
    "Dangerous when it's on, costly when it's not — pick your shots carefully.",
    "Wicket threat with a leaky economy; the runs are there for the disciplined.",
    "They bowl wicket-to-wicket aggression — score off the misses, respect the hits.",
    "An all-or-nothing bowler; they'll get one, but they'll concede plenty too.",
    "Goes hard for wickets and bleeds runs doing it — capitalise without the risk.",
    "Plenty of release balls, but a genuine wicket threat — stay switched on.",
    "They attack relentlessly; punish the width, but never relax against them.",
    "Expensive but penetrative — the loose ball is your reward for surviving.",
    "A bowler who buys wickets with runs; be greedy on the bad ones only.",
    "They'll get a couple but go for plenty — patience turns them into a target.",
    "Boom-or-bust spells — the danger and the runs come hand in hand.",
    "Aggressive and wayward; make the most of their off-days, beware their on-days.",
]


_BAT_POOLS = {
    "nemesis": NEMESIS_BAT,
    "in_form": INFORM_BAT,
    "keeper": KEEPER_BAT,
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
    "boom_or_bust": BOOMBUST_BOWL,
    "workhorse": WORKHORSE_BOWL,
    "spearhead": SPEARHEAD_BOWL,
}

# ════════════════════════════════════════════════════════════════════════════
#  PLANS  (tactical instructions — keyed by dismissal mode, then archetype)
# ════════════════════════════════════════════════════════════════════════════

# Dominant dismissal mode → how to get them out again. The cricket logic matters:
# a batter who "holes out" (caught) is mishitting to fielders, so push catchers
# OUT and invite the big shot — you do NOT keep catchers in the ring.
_BAT_DISMISSAL_PLANS = {
    "bowled": [
        "Attack the stumps — bring it back in and target the gate.",
        "Bowl straight and full; they play around their front pad.",
        "Full, fast and at off stump — there's a gap to bowl at.",
        "Swing or seam it in at the stumps early.",
        "Keep it stump-to-stump; they give a chance playing across the line.",
    ],
    "lbw": [
        "Bowl straight and full — hit the top of the pads.",
        "Swing it in to the front pad; they're lbw-prone.",
        "Target a full middle-and-leg line — they play across it.",
        "Full, straight and into the stumps; keep the umpire interested.",
        "Cramp them with the inswinger and trap them in front.",
    ],
    "caught": [
        "Keep fielders back on the rope and tempt the big shot — they hole out.",
        "Set a catching trap in the deep; give them the boundary ball.",
        "Push the fielders out for the mishit — they can't resist the aerial route.",
        "Hang a fielder in the deep and bowl into the hit; they go aerial under pressure.",
        "Protect the boundary and invite the lofted shot — they find the fielder.",
    ],
    "caught behind": [
        "Fuller, tighter outside off with the keeper up and a slip in — they nick off.",
        "Draw them into the drive on a fourth-stump line; they feel for it.",
        "Bowl a probing off-stump channel — the edge is on offer.",
        "Seam it away off a full length; keeper and slip in play.",
        "Tempt the loose drive away from the body and take the nick.",
    ],
    "c&b": [
        "Bowl straight and stay alert — they hit it back at you.",
        "Follow through ready for the return catch; they drive uppishly.",
        "Tempt the straight drive and hold the caught-and-bowled chance.",
        "Bowl into the hit and keep your hands ready in the follow-through.",
    ],
    "stumped": [
        "Flight it and drag them out of their crease — they've been stumped before.",
        "Bowl into the rough and tempt the charge; keeper up and ready.",
        "Toss it up wider — they come down the track and overbalance.",
        "Spin it away from the bat and let the keeper finish the job.",
        "Vary the flight; they commit early and can be beaten in the air.",
    ],
    "run out": [
        "Pile on the field pressure — they hesitate and have been run out before.",
        "Attack the single and back up at both ends; they ball-watch.",
        "Be sharp to the stumps — they're suspect between the wickets.",
        "Hit the stumps at every chance; the run-out is on offer.",
    ],
    "hit wicket": [
        "Bang it in short and crowd them — they can tread on their stumps.",
        "Cramp them on the back foot; they get tangled and lose their footing.",
    ],
}

_BAT_ARCHETYPE_PLANS = {
    "nemesis": [
        "Throw a fresh plan at them — what we've tried hasn't worked.",
        "Best bowler, best field, from ball one; they own this match-up.",
        "Don't bowl them into form — vary your length and angles early.",
        "Set defensive fields and make them earn every run the hard way.",
    ],
    "in_form": [
        "Get them before they've set — your strike bowler with the new ball.",
        "Strike early; a player in this touch only gets harder to remove.",
        "Attack from the off and break their rhythm before they settle.",
        "Front-load your best overs at them while the ball is hard.",
    ],
    "aggressor": [
        "Bowl tight and take the pace off — make them manufacture their shots.",
        "Deny them width and pace; cramp them for room.",
        "Back-of-a-length into the body and dry up the boundaries.",
        "Set the field back and make them take the risk to score.",
        "Change pace and length constantly — give them no rhythm to hit.",
    ],
    "anchor": [
        "Dry up the singles and build the pressure — patience beats them.",
        "Bowl maidens at them and force the rash shot.",
        "Squeeze both ends; frustration is your wicket-taker here.",
        "Don't search for the magic ball — let the dots do the work.",
    ],
    "converter": [
        "Take the half-chance — don't let them get set and go big.",
        "Throw everything at the first ten balls; they cash in once in.",
        "Be ruthless with any early chance; they won't give a second.",
        "Keep them under pressure before they reach twenty.",
    ],
    "leader": [
        "Plan the innings around removing them — they're the wicket that matters.",
        "Save an over of your best bowler for them specifically.",
        "Get them and the rest follow — make them your priority.",
        "No freebies — every ball at them with a clear purpose.",
    ],
    "keeper": [
        "Cut off their singles and make them force it — they love to stay busy.",
        "Set straight fields and starve the gaps; they nudge and run.",
        "Keep it tight outside off; keeper-bats nibble at width.",
        "Pressure them early before they get busy and take the game on.",
    ],
    "steady": [
        "Bowl a tidy, patient line and wait for the error.",
        "Keep it simple and disciplined; they'll give you a chance.",
        "Don't over-attack — let the pressure bring the wicket.",
        "Stick to your stock ball and keep them honest.",
    ],
}

_BOWL_PLANS = {
    "nemesis": [
        "Have a clear plan for them; watch for the ball that's done us before.",
        "See them off without risk, then target the others.",
        "Respect their spell — survive it and the runs come elsewhere.",
        "Don't get drawn into their trap ball; play them on merit.",
    ],
    "miser": [
        "Rotate the strike and refuse to take the bait.",
        "Milk them for ones; don't try to break them and lose a wicket.",
        "Accept the dot balls and cash in at the other end.",
        "Be patient — see off their spell, then attack the change bowlers.",
    ],
    "striker": [
        "See off their opening burst, then bat normally.",
        "Survive their spell at all costs — they hunt wickets.",
        "Play straight and leave well against them; minimise the risk.",
        "Respect the new-ball threat; don't give them the early one.",
    ],
    "boom_or_bust": [
        "Cash in when they drop short or wide — they leak while they hunt.",
        "Take the gifts but respect the wicket ball; they're wayward but dangerous.",
        "Be patient for the four-ball; just don't fall to the good one.",
        "Punish their loose deliveries — there are plenty between the wicket balls.",
    ],
    "workhorse": [
        "Be patient and pick off the loose ball; they bowl long, tidy spells.",
        "Wait them out and attack the bowler at the other end.",
        "Rotate the strike; don't let them settle into a rhythm against you.",
        "Outlast them — they'll keep coming, so stay disciplined.",
    ],
    "spearhead": [
        "See off their main threat, then go after the support attack.",
        "Weather their overs; the door opens once they've bowled out.",
        "Respect them early and target the weaker bowlers.",
        "Survive their spell and the pressure shifts back to them.",
    ],
}


# ── selection + picking ───────────────────────────────────────────────────────

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
    if b.get("is_keeper"):
        return "keeper"
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
    wkts = b.get("wickets") or 0
    vs = b.get("vs_us") or {}
    if vs.get("wickets") and vs["wickets"] >= 3:
        return "nemesis"
    if econ is not None and econ < 3.8:
        return "miser"
    if (sr is not None and sr <= 24) or (b.get("five_fors") or 0) >= 1:
        return "striker"
    if wkts >= 5 and econ is not None and econ >= 5.5:
        return "boom_or_bust"
    if overs >= 40:
        return "workhorse"
    if rank == 0:
        return "spearhead"
    if econ is not None and econ < 4.6:
        return "miser"
    return "striker"


def batter_note(archetype: str, seed: str) -> str:
    """A rotating one-line scouting description for a danger batter."""
    return _pick(_BAT_POOLS.get(archetype, STEADY_BAT), seed)


def bowler_note(archetype: str, seed: str) -> str:
    """A rotating one-line scouting description for a danger bowler."""
    return _pick(_BOWL_POOLS.get(archetype, SPEARHEAD_BOWL), seed)


def batter_plan(archetype: str, dominant_dismissal: str | None, seed: str) -> str:
    """A rotating, situation-appropriate plan: keyed on the dominant dismissal
    mode when there is one (most actionable), otherwise on the archetype."""
    if dominant_dismissal and dominant_dismissal in _BAT_DISMISSAL_PLANS:
        return _pick(_BAT_DISMISSAL_PLANS[dominant_dismissal], (seed or "") + ":plan")
    return _pick(_BAT_ARCHETYPE_PLANS.get(archetype, _BAT_ARCHETYPE_PLANS["steady"]), (seed or "") + ":plan")


def bowler_plan(archetype: str, seed: str) -> str:
    """A rotating plan for handling a danger bowler, keyed on archetype."""
    return _pick(_BOWL_PLANS.get(archetype, _BOWL_PLANS["spearhead"]), (seed or "") + ":plan")
