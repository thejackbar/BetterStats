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
    "Has our number. Keeps cashing in whenever he sees our bowling.",
    "A genuine bogey man for us; this is a fixture he circles on the calendar.",
    "History says he saves his best for us, plan for him to bat long.",
    "We've struggled to contain him before; the record against us is ugly.",
    "Loves the sight of our attack. He's filled his boots in past meetings.",
    "Our usual plans haven't worked on him; he owns this match-up.",
    "Whenever these two clubs meet, he tends to be the difference.",
    "Past form against us screams danger. Don't let him settle.",
    "He's punished us repeatedly; treat him as the top priority wicket.",
    "A serial tormentor in this derby. Get him early or pay for it.",
    "The numbers against us are alarming; he relishes this contest.",
    "Reads our bowling like a book. We need a fresh plan for him.",
    "Has feasted on us in the past, so respect the threat from ball one.",
    "If there's one man who turns up against us, it's this bloke.",
    "Our record against him is a warning. He's beaten us on his own before.",
    "He's the reason past games slipped away; shut him down first.",
    "A proven match-winner against us specifically, handle with real care.",
    "Form against us is in a different league to his form elsewhere.",
    "He's made a habit of hurting us; nothing about that has changed.",
    "Familiarity breeds runs for him here. Keep him guessing.",
]

INFORM_BAT = [
    "Red hot right now. Every time he walks out he looks set for a score.",
    "In the form of his life; the runs are flowing and he's brimming.",
    "Riding a purple patch, confident, busy and hard to tie down.",
    "Peaking at exactly the wrong time for us; he's seeing it like a beach ball.",
    "On a roll lately: momentum is firmly with him at the crease.",
    "Scoring for fun at the moment; he'll back himself against anyone.",
    "His recent scores are stacking up. A man playing with real freedom.",
    "Flying right now; get him cheaply or he'll bat you out of the game.",
    "Few in this comp are batting better, he's in ominous touch.",
    "Form is temporary, but his is dangerous, strike before he's in.",
    "Everything's clicking for him: timing, footwork, shot selection.",
    "He's been the in-form bat lately and shows no sign of slowing.",
    "Walking out full of runs and confidence, a real handful right now.",
    "Hot streak in full swing; nip it in the bud early.",
    "Carrying serious recent form. The kind that wins matches single-handed.",
    "Touch and tempo are spot on, he's the danger man of the moment.",
    "Runs in the bank lately means he'll come out positive and busy.",
    "On fire. The longer he's there, the worse it gets for us.",
    "His bat's doing the talking right now; quieten it fast.",
    "Playing like a man who can't get out, break the spell early.",
]

AGGRESSOR_BAT = [
    "A destroyer, when he connects, the rate goes through the roof.",
    "Lives for the boundary; give him width and the game can flip in an over.",
    "Takes the attack on from ball one: high risk, high reward, high danger.",
    "An explosive striker who can change a game in a handful of overs.",
    "Plays with serious intent, he'll look to dominate from the off.",
    "A clean hitter who clears the rope; bowl smart or he'll deposit you.",
    "Counter-attacker by nature: pressure him and he swings harder.",
    "Fast scorer who puts bowlers off their length in a hurry.",
    "He doesn't milk it, he murders it, protect the short boundaries.",
    "Aggressive intent means he scores quick but offers chances, bowl straight.",
    "A boundary machine; deny him the gaps and force the false shot.",
    "Can take the game away in ten balls. Never let him get a sniff of width.",
    "Big-shot player: he'll back himself to clear any field.",
    "Strikes at a fierce rate; the new ball and the death are his playgrounds.",
    "A momentum-grabber. Get on top early or he'll wrest it back violently.",
    "All power and intent; tuck him up and make him manufacture his shots.",
    "He hits through the line hard. A single mistake can cost a dozen.",
    "An attacking threat who feeds on loose deliveries. Be relentless.",
    "Goes hard from the start; one tight over can dry him up.",
    "Pure ball-striker. The kind who can win a game off his own bat fast.",
]

ANCHOR_BAT = [
    "A patient accumulator, he'll bat all day if you let him settle.",
    "The glue in their order; he soaks up pressure and bats deep.",
    "Old-fashioned grafter. He won't give it away, so you must take it.",
    "Bats time beautifully; starve him and force the rare loose shot.",
    "An anchor who builds the innings around himself, break his concentration.",
    "Hard to dislodge once in. Sustained pressure is the only way through.",
    "He values his wicket highly; tempt him rather than wait for a gift.",
    "Rotates strike and waits for the bad ball, patience versus patience.",
    "The rock at the top; remove him and the rest is far more exposed.",
    "Plays the long game. Denying singles frustrates him into errors.",
    "A wall to bowl at. You'll have to earn every bit of his wicket.",
    "Compact and watchful; he rarely beats himself, so build the pressure.",
    "Bats within himself and cashes in late. Don't let him get deep.",
    "Defence first, scoreboard second: bore him out with tight lines.",
    "The kind who carries his bat; set attacking fields and make him decide.",
    "A grinder who wears bowlers down, rotate your attack to stay fresh.",
    "Unhurried and organised; a probing spell, not a wild one, gets him.",
    "Happy to bat ugly for the cause, patience and discipline beat him.",
    "He absorbs the new ball superbly. Your best chance is early movement.",
    "Methodical and unflappable; squeeze the scoring and create doubt.",
]

CONVERTER_BAT = [
    "Doesn't waste starts: once he's in, he goes big, so get him early.",
    "A serial converter; thirties become hundreds if he's given time.",
    "Punishes any let-off. The cheap wicket has to be taken first ball in.",
    "Turns good starts into match-defining knocks. Don't drop him.",
    "Big-score merchant; a settled version of him is a nightmare.",
    "He cashes in when set. The danger window is right after he arrives.",
    "Once past twenty he rarely looks back. Strike in the first few balls.",
    "A daddy-hundred type; let him bed in and he'll bury you.",
    "Makes starts count. Every chance against him is worth gold.",
    "He builds and builds; the time to get him is before he's organised.",
    "Conversion is his calling card. A missed half-chance becomes a century.",
    "Settles quickly then accelerates. Disrupt his rhythm at the start.",
    "Give him a sniff of form and he turns it into a hundred. Be ruthless.",
    "His average is built on big ones; deny him the platform to launch.",
    "When he gets in, he gets greedy. Get the early breakthrough.",
    "A starts-to-scores specialist; the new batter is the vulnerable one.",
    "He rarely throws away a good start, so your plan has to be front-loaded.",
    "Capable of going on for a long time. The early wicket is everything.",
    "Converts pressure into runs once set. Keep him out of his comfort zone.",
    "The longer he stays, the bigger it gets. Make the start count.",
]

LEADER_BAT = [
    "Their leading run-scorer. The man their innings is built around.",
    "Top of their charts; remove him and you've removed their backbone.",
    "The premier bat in this side, your single most important wicket.",
    "Carries their batting; the rest tend to follow his lead.",
    "Their go-to man with the bat. Set the tone by getting him.",
    "Head and shoulders their best. The whole order leans on him.",
    "The cornerstone of their batting; everything starts with stopping him.",
    "Their standout run-maker. Earn this wicket and the gate swings open.",
    "Far and away their main scorer. Plan the innings around him.",
    "The batting kingpin; his dismissal changes the entire complexion.",
    "Their most reliable source of runs. Make him your first priority.",
    "The name at the top of the team sheet for a reason, shut him down.",
    "Their batting revolves around him, break that and they wobble.",
    "The leading light of their order. A prized scalp worth chasing.",
    "Top dog with the bat; the rest are a level below him.",
    "Their run engine. Stall it early and the scoreboard slows.",
    "The one they can't afford to lose cheaply, so make it happen.",
    "Their premier accumulator and the man to target from the first ball.",
    "He sets their standard. Get him and confidence drains from the rest.",
    "Their best bat by a distance; this is the contest within the contest.",
]

# Keeper-batters — a gloveman who can bat. Detected from real fielding data
# (wicketkeeper catches / stumpings), so these only fire for an actual keeper.
KEEPER_BAT = [
    "Their keeper-batter. Busy, sharp between the wickets and never out of the game.",
    "Gloveman who can really bat; he's used to building an innings under pressure.",
    "A wicketkeeper-batsman. Expect quick singles and a cool head when it tightens.",
    "Keeps and bats up the order; a genuine two-in-one threat to plan for.",
    "Their keeper with the bat in hand, scrappy, street-smart and hard to shift.",
    "A gloveman-bat who reads the game well; he'll milk you if you let him settle.",
    "Wicketkeeper-batter who thrives on rotating the strike, cut off his singles.",
    "He keeps wickets and anchors the innings; don't underestimate his batting.",
    "A busy keeper-bat: quick feet, soft hands, and a knack for the awkward knock.",
    "Their gloveman bats with real nous; pressure him before he gets going.",
    "Keeper-batter who's seen every situation from behind the stumps, very streetwise.",
    "A dual threat: takes his chances with the gloves and grafts runs with the bat.",
    "Their keeper can bat properly. Treat him as a top-order wicket, not a tail-ender.",
    "Nimble keeper-bat; he'll nudge, nurdle and run you ragged for ones and twos.",
    "A wicketkeeper who bats with the game's tempo in mind, calm under pressure.",
    "Gloveman-batter with a high cricket IQ; he rarely gets himself out cheaply.",
    "Their keeper is a real batting asset, bowl to a plan, don't gift him width.",
    "A scrapping keeper-bat who finds a way; dot balls are your friend against him.",
    "Keeps tidily and bats with intent, a genuine all-round headache.",
    "Their gloveman bats like a specialist; the keeper tag undersells the threat.",
    "A keeper-batsman who loves a chase. Composed and good at pacing a run-down.",
    "Sharp keeper, sharper between the wickets. He turns ones into twos.",
    "Their keeper-bat is the heartbeat of the side; vocal, busy and combative.",
    "A glovesman who bats deep into the innings, patience will be needed.",
]

STEADY_BAT = [
    "A dependable contributor who quietly does damage if ignored.",
    "Not flashy, but consistent: the kind who sneaks a useful score.",
    "A solid hand in their middle order; don't let him off the hook.",
    "Reliable rather than spectacular: still worth a clear plan.",
    "Chips in regularly; a steady threat that adds up over an innings.",
    "Workmanlike and effective: capable of an awkward, sticky knock.",
    "A useful bat who can frustrate if you switch off against him.",
    "Quietly handy: give him room and he'll happily accept it.",
    "Steady accumulator who keeps their innings ticking along.",
    "Unspectacular but durable: bowl to a plan and stay patient.",
    "A capable contributor who can punish anything loose.",
    "He won't blow you away, but he'll hang around and graft.",
    "A consistent middle-order presence. Keep the pressure on.",
    "Does the unglamorous work well; respect him without overrating him.",
    "Reliable across a season. The sort who nudges a tidy thirty.",
    "A steady customer; deny him rhythm and he'll grow restless.",
    "Useful depth in their batting. Make him earn everything.",
    "Honest, hard-working bat. Nothing fancy, but plenty stubborn.",
    "A handy contributor who rewards any lapse in discipline.",
    "Dependable and unhurried. Tighten the screws and wait.",
]

# ════════════════════════════════════════════════════════════════════════════
#  BOWLER DESCRIPTIONS  (archetype pools)
# ════════════════════════════════════════════════════════════════════════════

NEMESIS_BOWL = [
    "Has tormented us before. Our batters have struggled to read him.",
    "A genuine bogey bowler for this club; the record against us is grim.",
    "Loves bowling at us, he's run through our top order in the past.",
    "He's had our number repeatedly; counter him with a clear plan.",
    "Past meetings say he's our biggest threat with the ball.",
    "We've handed him wickets before. Don't gift him the same again.",
    "A proven wrecker of our innings; treat every spell as a threat.",
    "Our batters haven't solved him yet. That has to change today.",
    "He saves his best for us, disrupt his rhythm early.",
    "History warns he can win this on his own with the ball.",
    "He's torn through us before; pick your moments against him carefully.",
    "A familiar tormentor, respect him, but find a way to score.",
    "The bowler who's hurt us most, line up a counter-plan now.",
    "We've been his bunnies in the past; flip that script early.",
    "He bowls with our wickets in mind. Be proactive, not passive.",
    "Owns the match-up against us. See him off, then cash in elsewhere.",
    "A repeat offender against this side. The early overs are crucial.",
    "His record against us demands caution from the first ball.",
    "He's beaten us before with the ball; don't let him build pressure.",
    "Whenever we meet, he's in the wickets, break that pattern.",
]

MISER_BOWL = [
    "Miserly. He chokes the run rate and forces the mistake.",
    "Bowls a tight, nagging line; you won't score freely off him.",
    "An economy specialist, rotate the strike and don't try to force it.",
    "Hard to get away; the pressure he builds gets wickets at the other end.",
    "Rarely offers a loose ball. Patience is the only way to handle him.",
    "He squeezes the game; refuse to take the bait and milk the others.",
    "A run-saver who suffocates innings. See him off without risk.",
    "Relentlessly accurate: the smart play is to wait him out.",
    "Gives nothing away; trying to break him is how wickets fall.",
    "Tight as they come. Accept the dot balls and target the change bowlers.",
    "His containment piles on pressure. Keep the scoreboard moving elsewhere.",
    "A choke-hold bowler; respect the spell and pounce later.",
    "Dries up the runs and waits for the error, deny him that satisfaction.",
    "Pinpoint control means easy runs are off the table against him.",
    "He'll bowl maidens for fun. Don't let frustration cost a wicket.",
    "An economical workhorse; play him out and attack from the other end.",
    "Stingy and disciplined: singles, not strokes, are the way through.",
    "The pressure valve in their attack, survive him, then accelerate.",
    "Bowls dot after dot; reset, stay calm and bide your time.",
    "A real miser. The contest is patience, and he usually wins it.",
]

STRIKER_BOWL = [
    "A strike bowler. He hunts wickets and takes them in clusters.",
    "Genuine wicket-taking threat; he can rip out a top order fast.",
    "Attacks the stumps and the edge. Every ball is a wicket ball to him.",
    "He doesn't just contain, he strikes. Survive the new ball at all costs.",
    "A spell-changer; one good over from him can flip the match.",
    "Takes wickets in bunches. A quick start against him steadies the ship.",
    "His strike rate is dangerous; he'll find a way through if you let him.",
    "A natural wicket-taker. See off his opening burst with care.",
    "He bowls to take wickets, not to save runs, respect the threat.",
    "Capable of a match-winning haul; blunt him early and rotate.",
    "Always in the game. He probes for the breakthrough every ball.",
    "A penetrative bowler who thrives on movement and pace.",
    "When he's on, wickets tumble, weather the storm and cash in later.",
    "The breakthrough merchant of their attack. Don't feed him chances.",
    "He can run through a side; the plan is to deny him the first one.",
    "A genuine threat with the new ball. Your start sets up the innings.",
    "Lives for the wicket ball, play straight and leave well.",
    "He'll test you every delivery; concentration is the key against him.",
    "A wicket-taker who builds his own pressure. Be watchful, not reckless.",
    "Dangerous in any conditions. Get through his spell and the rest eases.",
]

WORKHORSE_BOWL = [
    "Their workhorse. Long, accurate spells that wear batters down.",
    "Bowls big overs and keeps coming; outlast him rather than attack him.",
    "A reliable load-bearer who holds an end up all day.",
    "He'll bowl himself into the ground for the cause, patience beats him.",
    "The bankable option in their attack; consistent and hard to shift.",
    "Bowls long and tight. The smart play is to wait for the change.",
    "A stamina bowler who never lets the pressure off, stay disciplined.",
    "Always available, always accurate. Pick the right balls to score.",
    "He soaks up overs and frustrates; rotate the strike and bide time.",
    "A dependable grinder. Nothing loose, so manufacture nothing rash.",
    "Carries their attack with sheer volume of accurate overs.",
    "He won't tire easily, settle in for a long, careful contest.",
    "The glue of their bowling; respect the line and target the others.",
    "Steady, durable and relentless. Discipline is the only answer.",
    "A true workhorse. Keep him wicketless and the pressure shifts.",
    "He'll plug an end for ten overs straight; play him on merit.",
    "Consistent length and a tireless engine. See him through.",
    "The unsung hero of their attack, quietly effective if ignored.",
    "Bowls to a plan over after over; counter with one of your own.",
    "An iron-man bowler; the war of attrition is exactly what he wants.",
]

SPEARHEAD_BOWL = [
    "Their leading wicket-taker, the spearhead of the whole attack.",
    "Top of their bowling charts; everything funnels through him.",
    "Their strike weapon. See him off and the threat drops sharply.",
    "The bowler they turn to when they need a wicket. Be ready for him.",
    "Their best with the ball by a distance; plan your innings around him.",
    "The tip of their spear. Survive his spells and target the rest.",
    "Their main man with the ball, your key battle of the day.",
    "Carries their attack; blunt him and they look ordinary.",
    "The wicket-taker-in-chief, respect him, then go after the support.",
    "Their go-to threat. The contest with him decides plenty.",
    "Head of their attack; weather his overs and the door opens.",
    "Their premier bowler, earn a start against him and you're set.",
    "The one they lean on for breakthroughs. Don't hand him momentum.",
    "Their standout bowler; the smart innings sees him off first.",
    "The leader of their attack. A clear plan for him is non-negotiable.",
    "Their biggest bowling threat. Get through him and exhale.",
    "The danger man with the ball. Every batter must respect his spell.",
    "Their attack's heartbeat, quieten him and they lose their rhythm.",
    "Their wicket machine; deny him early and the pressure lifts.",
    "Front and centre of their bowling. This is the match-up that matters.",
]

# Wickets but expensive — the boom-or-bust threat (strikes, but leaks runs while
# hunting). Detectable from scorecard wickets + economy alone.
BOOMBUST_BOWL = [
    "Boom or bust: he takes wickets but leaks runs hunting them.",
    "A wicket-taker who pays for it; punish the bad balls, respect the good one.",
    "High-risk, high-reward bowler, plenty to score off, but he'll strike too.",
    "He buys his wickets. There are runs on offer if you survive the danger ball.",
    "Attacking but expensive; cash in on the loose stuff, watch the wicket ball.",
    "Gives you chances to score and chances to get out in the same over.",
    "A feast-or-famine bowler, milk the width, but don't take him on blindly.",
    "He'll go searching for wickets and spray a few. Be patient for the four-ball.",
    "Dangerous when it's on, costly when it's not. Pick your shots carefully.",
    "Wicket threat with a leaky economy; the runs are there for the disciplined.",
    "He bowls wicket-to-wicket aggression. Score off the misses, respect the hits.",
    "An all-or-nothing bowler; he'll get one, but he'll concede plenty too.",
    "Goes hard for wickets and bleeds runs doing it, capitalise without the risk.",
    "Plenty of release balls, but a genuine wicket threat, stay switched on.",
    "He attacks relentlessly; punish the width, but never relax against him.",
    "Expensive but penetrative: the loose ball is your reward for surviving.",
    "A bowler who buys wickets with runs; be greedy on the bad ones only.",
    "He'll get a couple but go for plenty. Patience turns him into a target.",
    "Boom-or-bust spells. The danger and the runs come hand in hand.",
    "Aggressive and wayward; make the most of his off-days, beware his on-days.",
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

# Dominant dismissal mode → how to get him out again. The cricket logic matters:
# a batter who "holes out" (caught) is mishitting to fielders, so push catchers
# OUT and invite the big shot — you do NOT keep catchers in the ring.
_BAT_DISMISSAL_PLANS = {
    "bowled": [
        "Attack the stumps. Bring it back in and target the gate.",
        "Bowl straight and full; he plays around his front pad.",
        "Full, fast and at off stump, there's a gap to bowl at.",
        "Swing or seam it in at the stumps early.",
        "Keep it stump-to-stump; he gives a chance playing across the line.",
    ],
    "lbw": [
        "Bowl straight and full: hit the top of the pads.",
        "Swing it in to the front pad; he's lbw-prone.",
        "Target a full middle-and-leg line. He plays across it.",
        "Full, straight and into the stumps; keep the umpire interested.",
        "Cramp him with the inswinger and trap him in front.",
    ],
    "caught": [
        "Keep men back on the rope and tempt the big shot. He holes out.",
        "Set a catching trap in the deep; give him the boundary ball.",
        "Push the fielders out for the mishit. He can't resist the aerial route.",
        "Hang a man in the deep and bowl into the hit; he goes aerial under pressure.",
        "Protect the boundary and invite the lofted shot. He finds the fielder.",
    ],
    "caught behind": [
        "Fuller, tighter outside off with the keeper up and a slip in. He nicks off.",
        "Draw him into the drive on a fourth-stump line; he feels for it.",
        "Bowl a probing off-stump channel. The edge is on offer.",
        "Seam it away off a full length; keeper and slip in play.",
        "Tempt the loose drive away from the body and take the nick.",
    ],
    "c&b": [
        "Bowl straight and stay alert. He hits it back at you.",
        "Follow through ready for the return catch; he drives uppishly.",
        "Tempt the straight drive and hold the caught-and-bowled chance.",
        "Bowl into the hit and keep your hands ready in the follow-through.",
    ],
    "stumped": [
        "Flight it and drag him out of his crease, he's been stumped before.",
        "Bowl into the rough and tempt the charge; keeper up and ready.",
        "Toss it up wider. He comes down the track and overbalances.",
        "Spin it away from the bat and let the keeper finish the job.",
        "Vary the flight; he commits early and can be beaten in the air.",
    ],
    "run out": [
        "Pile on the field pressure. He hesitates and has been run out before.",
        "Attack the single and back up at both ends; he ball-watches.",
        "Be sharp to the stumps. He's suspect between the wickets.",
        "Hit the stumps at every chance; the run-out is on offer.",
    ],
    "hit wicket": [
        "Bang it in short and crowd him. He can tread on his stumps.",
        "Cramp him on the back foot; he gets tangled and loses his footing.",
    ],
}

_BAT_ARCHETYPE_PLANS = {
    "nemesis": [
        "Throw a fresh plan at him. What we've tried hasn't worked.",
        "Best bowler, best field, from ball one; he owns this match-up.",
        "Don't bowl him into form. Vary your length and angles early.",
        "Set defensive fields and make him earn every run the hard way.",
    ],
    "in_form": [
        "Get him before he's set, your strike bowler with the new ball.",
        "Strike early; a man in this touch only gets harder to remove.",
        "Attack from the off and break his rhythm before he settles.",
        "Front-load your best overs at him while the ball is hard.",
    ],
    "aggressor": [
        "Bowl tight and take the pace off. Make him manufacture his shots.",
        "Deny him width and pace; cramp him for room.",
        "Back-of-a-length into the body and dry up the boundaries.",
        "Set the field back and make him take the risk to score.",
        "Change pace and length constantly. Give him no rhythm to hit.",
    ],
    "anchor": [
        "Dry up the singles and build the pressure, patience beats him.",
        "Bowl maidens at him and force the rash shot.",
        "Squeeze both ends; frustration is your wicket-taker here.",
        "Don't search for the magic ball. Let the dots do the work.",
    ],
    "converter": [
        "Take the half-chance. Don't let him get set and go big.",
        "Throw everything at the first ten balls; he cashes in once in.",
        "Be ruthless with any early chance; he won't give a second.",
        "Keep him under pressure before he reaches twenty.",
    ],
    "leader": [
        "Plan the innings around removing him. He's the wicket that matters.",
        "Save an over of your best bowler for him specifically.",
        "Get him and the rest follow. Make him your priority.",
        "No freebies, every ball at him with a clear purpose.",
    ],
    "keeper": [
        "Cut off his singles and make him force it. He loves to stay busy.",
        "Set straight fields and starve the gaps; he nudges and runs.",
        "Keep it tight outside off; gloveman-bats nibble at width.",
        "Pressure him early before he gets busy and takes the game on.",
    ],
    "steady": [
        "Bowl a tidy, patient line and wait for the error.",
        "Keep it simple and disciplined; he'll give you a chance.",
        "Don't over-attack. Let the pressure bring the wicket.",
        "Stick to your stock ball and keep him honest.",
    ],
}

_BOWL_PLANS = {
    "nemesis": [
        "Have a clear plan for him; watch for the ball that's done us before.",
        "See him off without risk, then target the others.",
        "Respect his spell. Survive it and the runs come elsewhere.",
        "Don't get drawn into his trap ball; play him on merit.",
    ],
    "miser": [
        "Rotate the strike and refuse to take the bait.",
        "Milk him for ones; don't try to break him and lose a wicket.",
        "Accept the dot balls and cash in at the other end.",
        "Be patient. See off his spell, then attack the change bowlers.",
    ],
    "striker": [
        "See off his opening burst, then bat normally.",
        "Survive his spell at all costs. He hunts wickets.",
        "Play straight and leave well against him; minimise the risk.",
        "Respect the new-ball threat; don't give him the early one.",
    ],
    "boom_or_bust": [
        "Cash in when he drops short or wide. He leaks while he hunts.",
        "Take the gifts but respect the wicket ball; he's wayward but dangerous.",
        "Be patient for the four-ball; just don't fall to the good one.",
        "Punish his loose deliveries. There are plenty between the wicket balls.",
    ],
    "workhorse": [
        "Be patient and pick off the loose ball; he bowls long, tidy spells.",
        "Wait him out and attack the bowler at the other end.",
        "Rotate the strike; don't let him settle into a rhythm against you.",
        "Outlast him: he'll keep coming, so stay disciplined.",
    ],
    "spearhead": [
        "See off their main man, then go after the support attack.",
        "Weather his overs; the door opens once he's bowled out.",
        "Respect him early and target the weaker bowlers.",
        "Survive his spell and the pressure shifts back to them.",
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
