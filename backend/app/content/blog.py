"""
Marketing blog post metadata — the backend's single source of truth for the
blog. Two readers depend on it:

  - routers/seo.py    — emits a sitemap entry per post.
  - routers/og_preview.py — builds the social-share card a crawler sees when
                            someone posts a /blog/{slug} link to Facebook,
                            LinkedIn, etc. (the SPA's client-side meta tags
                            never reach those crawlers, which don't run JS).

The article *content* lives in frontend/src/data/blog.js; this file mirrors
just the slug/title/description/image/date so each post shares with its own
card. ADDING A POST: drop the image in frontend/public/marketing/blog/, add
the full post to frontend/src/data/blog.js, and add a matching row here (same
order). That is the whole "do the same for future posts" checklist.
"""

# Each post's hero image, served as a static file by the frontend nginx at
# /marketing/blog/*.jpg. All are 1920x1080 (16:9), which renders cleanly as a
# summary_large_image card.
IMAGE_WIDTH = 1920
IMAGE_HEIGHT = 1080

# Newest first, matching the order shown on /blog. Posts may also carry a
# "body" (content blocks mirrored from frontend/src/data/blog.js) and an "faq"
# list; og_preview renders both into the crawler HTML so AI engines get the full
# article and FAQ schema, not just the card. Card-only posts omit them.
BLOG_POSTS: list[dict] = [
    {
        "slug": "how-to-analyse-cricket-opposition",
        "title": "How to Analyse Cricket Opposition at Club Level",
        "date": "2026-06-21",
        "image": "/marketing/blog/bowling-economy.jpg",
        "description": (
            "How to scout the opposition in community cricket from the scorecards "
            "you already have, and turn it into a simple game plan."
        ),
        "body": [
            {"type": "p", "text": "Most club cricketers walk out to face a side they know almost nothing about. A bit of homework changes that, and you do not need a video analyst or ball-by-ball data to do it. The scorecards your competition already publishes hold most of what a captain needs."},
            {"type": "h2", "text": "What you can learn from a scorecard"},
            {"type": "p", "text": "Club cricket data is scorecard level, not ball by ball, so you will not find a batter's strike rate against legspin in the last five overs. What you can read off the scorecards is still plenty."},
            {"type": "ul", "items": [
                "Who scores the runs, the top order or further down",
                "Which bowlers take the wickets",
                "Who is in form right now",
                "How the key batters tend to get out",
                "The partnerships that have hurt sides before",
                "Results home and away",
            ]},
            {"type": "h2", "text": "Why the manual version rarely happens"},
            {"type": "p", "text": "In theory you can pull a side's recent scorecards off PlayHQ, read them and build a picture. In practice nobody has a spare hour on a Thursday night, so it does not get done, and selection runs on memory and a bloke who reckons their opener cannot play the short ball."},
            {"type": "h2", "text": "Start with the danger players"},
            {"type": "p", "text": "Look for the names that keep showing up. A batter averaging well clear of the rest of their side, or a bowler taking wickets most weeks, is where your plan starts. Note how the batters get out, because a pattern there tells you how to set a field and who to bowl."},
            {"type": "h2", "text": "Use your own head-to-head"},
            {"type": "p", "text": "If you have played a side before, your own scorecards already hold the history: who has scored against you, which of your bowlers has dismissed their best player, what the score was last time. That record is the most useful scouting you have, and it is sitting in your own results."},
            {"type": "h2", "text": "Turn it into a plan"},
            {"type": "p", "text": "Good scouting ends in a few clear calls: who to get out early, who to bowl dry and wait out, which of your bowlers to save for their danger man, and what a par score looks like at the ground. Keep it to a single page the captain can glance at by the toss."},
            {"type": "h2", "text": "How BetterCricket does the work"},
            {"type": "p", "text": "BetterIQ reads the same scorecards and builds the dossier for you: danger batters and bowlers with their recent form, your head-to-head record, the match-ups from your own bowlers' past dismissals, and a printable captain's cheat sheet. It works off the scorecards you already generate, so you score the game exactly as you do now."},
            {"type": "links", "heading": "Related", "items": [
                {"label": "BetterIQ opposition scouting", "href": "/modules/betteriq"},
                {"label": "The full feature list", "href": "/features"},
                {"label": "Pricing", "href": "/pricing"},
                {"label": "PlayHQ", "href": "https://www.playhq.com", "external": True},
                {"label": "Cricket Australia", "href": "https://www.cricket.com.au", "external": True},
            ]},
            {"type": "callout", "text": "BetterIQ turns your own scorecards into an opposition report and a printable captain's cheat sheet. Bring your club online and we handle the first full historical sync."},
        ],
        "faq": [
            {"q": "Can you analyse cricket opposition without ball-by-ball data?", "a": "Yes. Club scorecards give you form, averages, how players get out, partnerships and head-to-head history. You miss ball-level match-ups, but that is more than enough to plan selection and tactics."},
            {"q": "What should a club captain look for in the opposition?", "a": "Their danger batters and bowlers, who is in form, how the key batters get out, the partnerships that have done damage, and your own record against them."},
            {"q": "Where does the opposition data come from?", "a": "The scorecards published through PlayHQ and Cricket Australia's community cricket, the same matches your club already plays in."},
            {"q": "Does BetterIQ need extra scoring?", "a": "No. It reads the scorecards you already generate and builds the opposition report from them, so your match day does not change."},
        ],
    },
    {
        "slug": "how-to-build-a-cricket-club-website",
        "title": "How to Build a Cricket Club Website",
        "date": "2026-06-21",
        "image": "/marketing/blog/why-stats-page.jpg",
        "description": (
            "What a cricket club website needs, the ways to build one, and how to "
            "keep it current after every game."
        ),
        "body": [
            {"type": "p", "text": "A cricket club website has one job for most of the year. It tells people what is on and makes the club look like somewhere worth being. Building it once is the easy part. Keeping it current is where most clubs come unstuck."},
            {"type": "h2", "text": "What a cricket club website actually needs"},
            {"type": "ul", "items": [
                "Fixtures and results",
                "Teams and grades",
                "Player and club stats",
                "News and announcements",
                "Somewhere for sponsors to sit",
                "Contact and registration links",
                "A way to stay current that does not rely on one person remembering",
            ]},
            {"type": "h2", "text": "The three common routes"},
            {"type": "p", "text": "A general website builder like Wix or Squarespace looks tidy but knows nothing about cricket, so every result and stat goes in by hand. A generic club system handles members and payments but rarely the cricket itself. A cricket platform builds the site from your match data, so the fixtures and stats keep themselves up to date."},
            {"type": "h2", "text": "The maintenance trap"},
            {"type": "p", "text": "Most club websites die the same way. Someone keen builds a good one and keeps it fed for a season. Then they get busy. A year on, the fixtures are wrong, the results stop in November, and the site does more harm than the old Facebook page did. A site that draws from your match data avoids that, because the updates arrive on their own."},
            {"type": "h2", "text": "A website built from your own data"},
            {"type": "p", "text": "The better approach is to wire the site to the data your club already records. Fixtures, results, ladders, player profiles and leaderboards then fill themselves in and stay right after every game."},
            {"type": "h2", "text": "How BetterCricket does it"},
            {"type": "p", "text": "BetterSocials gives your club a public website built from your own match data, in your crest, colours and fonts, with a post designer for match-day graphics. It reads the same data as your stats, so the website is current after every game and the only thing you add is the news you want to share."},
            {"type": "links", "heading": "Related", "items": [
                {"label": "BetterSocials website and posts", "href": "/modules/bettersocials"},
                {"label": "The full feature list", "href": "/features"},
                {"label": "Pricing", "href": "/pricing"},
                {"label": "All the modules", "href": "/modules"},
                {"label": "PlayHQ", "href": "https://www.playhq.com", "external": True},
                {"label": "Cricket Australia", "href": "https://www.cricket.com.au", "external": True},
            ]},
            {"type": "callout", "text": "BetterSocials runs your club's public website and match-day posts from your own data. Bring your club online and we handle the first full historical sync."},
        ],
        "faq": [
            {"q": "What does a cricket club website need?", "a": "Fixtures and results, teams and grades, player and club stats, news, somewhere for sponsors, and contact or registration links, all kept current after every game."},
            {"q": "What is the best way to build a cricket club website?", "a": "Connect it to your match data so fixtures, results and stats update themselves. A general website builder works, but it means typing in every result by hand."},
            {"q": "How do I keep a club website up to date?", "a": "Use a platform that pulls from your match data. BetterSocials refreshes fixtures, results, ladders and stats automatically after every game."},
            {"q": "Can I use my club's branding?", "a": "Yes. BetterSocials uses your crest, colours and fonts across the website and the match-day graphics."},
        ],
    },
    {
        "slug": "best-cricket-club-management-software",
        "title": "The Best Cricket Club Management Software for Australian Clubs",
        "date": "2026-06-21",
        "image": "/marketing/blog/club-culture.jpg",
        "description": (
            "What to look for in cricket club management software in Australia, "
            "how the main tools compare, and where an all-in-one club platform fits."
        ),
        "body": [
            {"type": "p", "text": "If you have searched for the best cricket club management software, you have probably found the results a muddle. Some tools run competitions. Some build websites. Some track stats. Very few do the whole job of running a club, and the words used for all of them overlap. This guide sorts out the categories and shows where each tool fits."},
            {"type": "h2", "text": "What cricket club management software actually needs to do"},
            {"type": "p", "text": "A community cricket club is a small organisation that happens to play cricket. Over a season it has to handle a long list of jobs, most of them done by volunteers after work:"},
            {"type": "ul", "items": [
                "Registration, teams and grades",
                "Fixtures, scoring and results",
                "Weekly player availability and team selection",
                "Match fees and membership payments",
                "Email and messages to the whole club",
                "A public website members and sponsors want to visit",
                "The club's stats and history, kept accurate and current",
                "Match-day social posts and opposition analysis",
            ]},
            {"type": "p", "text": "No single tool has historically done all of that, which is why most clubs end up with a spreadsheet, a group chat, a design app and three separate logins."},
            {"type": "h2", "text": "The two layers: official platforms and club platforms"},
            {"type": "p", "text": "It helps to split the market in two. The first layer is official competition management. In Australia that is PlayHQ, the platform Cricket Australia runs for registration, fixtures, scoring and results. You do not really choose it; your association runs on it and your club plugs in."},
            {"type": "p", "text": "The second layer is everything that makes a club good to belong to: the website, the history, the player profiles, the selection, the fees, the social posts. This layer is where a club actually has a choice, and where most of the frustration lives."},
            {"type": "h2", "text": "Where BetterCricket fits"},
            {"type": "p", "text": "BetterCricket is the club layer, built specifically for Australian cricket. It reads the match data your club already records, so there is no double entry, and turns it into a public club website with player profiles, leaderboards, all-time records and season yearbooks. From there you add only the modules you want."},
            {"type": "ul", "items": [
                "BetterStats: your full history and a public club site",
                "BetterSelect: player availability and smart team selection",
                "BetterSocials: your website and match-day graphics",
                "BetterAdmin: fees, member email and stock",
                "BetterIQ: opposition scouting and deep analytics",
            ]},
            {"type": "h2", "text": "What to look for when you choose"},
            {"type": "ul", "items": [
                "It imports your full history, not just the current season",
                "It updates automatically, with no data entered twice",
                "It gives you a public site, not just an admin dashboard",
                "Pricing is a flat rate per club, not per player or per team",
                "It is built for Australian club cricket and supported locally",
            ]},
            {"type": "p", "text": "BetterCricket pricing is a flat annual rate per club: BetterStats is the Core, and you add modules as you need them. The same fee covers one team or fifty."},
            {"type": "links", "heading": "Related", "items": [
                {"label": "BetterCricket pricing", "href": "/pricing"},
                {"label": "The full feature list", "href": "/features"},
                {"label": "The modules", "href": "/modules"},
                {"label": "How it compares to the tools you already use", "href": "/compare"},
                {"label": "PlayHQ (official competition platform)", "href": "https://www.playhq.com", "external": True},
                {"label": "Cricket Australia community cricket", "href": "https://www.cricket.com.au", "external": True},
            ]},
            {"type": "callout", "text": "BetterCricket is the club operating system for Australian cricket: your stats and history, your website, selection, fees, social posts and analytics in one place. Bring your club online and we handle the first full historical sync."},
        ],
        "faq": [
            {"q": "What is the best software to run an Australian cricket club?", "a": "There is no single answer, because two layers are involved. PlayHQ handles official competition management (registration, fixtures, scoring). For the club layer (website, stats, history, selection, fees, social posts and analysis) BetterCricket is built specifically for Australian clubs and brings all of it into one place."},
            {"q": "Is PlayHQ a club management platform?", "a": "PlayHQ is the official competition management platform used across Australian cricket. It runs registration, fixtures, scoring and results. It is not a club website, stats archive or analytics platform, so most clubs pair it with a club platform for those jobs."},
            {"q": "How much does cricket club management software cost?", "a": "It varies. BetterCricket is a flat annual rate per club: BetterStats (the Core) is $399 a year, and modules are $149 each ($249 for BetterIQ), with a discount when you bundle. The price is the same whether the club runs one team or fifty."},
            {"q": "Do I have to stop using PlayHQ to use BetterCricket?", "a": "No. You keep scoring and registering exactly as you do now. BetterCricket reads the data your club already records and adds the website, history and analytics on top, so nothing about your match day changes."},
        ],
    },
    {
        "slug": "best-playhq-alternative",
        "title": "The Best PlayHQ Alternative for Australian Cricket Clubs",
        "date": "2026-06-20",
        "image": "/marketing/blog/playhq-migration.jpg",
        "description": (
            "PlayHQ runs the competition, but it isn't a club website or stats "
            "platform. Here's the honest take on alternatives for the parts PlayHQ "
            "leaves out."
        ),
        "body": [
            {"type": "p", "text": "People search for a PlayHQ alternative for two very different reasons, and the honest answer depends on which one you are. This article covers both, without pretending BetterCricket is something it is not."},
            {"type": "h2", "text": "First, the honest part: you cannot really replace PlayHQ for competitions"},
            {"type": "p", "text": "PlayHQ is the official competition management platform Cricket Australia runs. Registration, fixtures, scoring and results flow through it, and your association runs on it. If you are looking for a drop-in replacement for that, there is not really one, and swapping it out is not in your club's hands."},
            {"type": "h2", "text": "What people actually want when they look for an alternative"},
            {"type": "p", "text": "Most clubs searching for an alternative are not unhappy with fixtures and scoring. They are frustrated that PlayHQ does not do the rest of the job:"},
            {"type": "ul", "items": [
                "A public club website that looks like the club, not a generic template",
                "The club's full history and career stats, going back decades",
                "Rich player profiles with milestones and a shareable stat card",
                "Weekly availability and team selection without the group-chat scramble",
                "Match fees and member email in one place",
                "Match-day social graphics and opposition analysis",
            ]},
            {"type": "p", "text": "These are real gaps, and they are exactly the jobs a club platform is meant to fill."},
            {"type": "h2", "text": "BetterCricket: the club layer on top of PlayHQ"},
            {"type": "p", "text": "BetterCricket is not a replacement for PlayHQ. It sits on top of it. It reads the match data your club already records, so there is no double entry, and turns it into a public club website with player profiles, leaderboards, all-time records and season yearbooks, plus modules for selection, social posts, fees and analytics."},
            {"type": "ul", "items": [
                "BetterStats: your full history and a public club site",
                "BetterSelect: player availability and smart team selection",
                "BetterSocials: your website and match-day graphics",
                "BetterAdmin: fees, member email and stock",
                "BetterIQ: opposition scouting and deep analytics",
            ]},
            {"type": "h2", "text": "How it works alongside PlayHQ"},
            {"type": "p", "text": "Nothing about your match day changes. You keep scoring in PlayHQ exactly as you do now. BetterCricket pulls the data, reconciles your history and keeps your stats current after every game. The short version: use PlayHQ because you have to, and BetterCricket because you want to."},
            {"type": "links", "heading": "Related", "items": [
                {"label": "BetterCricket features", "href": "/features"},
                {"label": "The modules", "href": "/modules"},
                {"label": "Pricing", "href": "/pricing"},
                {"label": "How BetterCricket compares", "href": "/compare"},
                {"label": "PlayHQ", "href": "https://www.playhq.com", "external": True},
                {"label": "Cricket Australia", "href": "https://www.cricket.com.au", "external": True},
            ]},
            {"type": "callout", "text": "BetterCricket gives your club the website, history, selection, fees, social posts and analytics that PlayHQ leaves out, all reading from the data you already record. Bring your club online and we handle the first full historical sync."},
        ],
        "faq": [
            {"q": "Can I replace PlayHQ with BetterCricket?", "a": "No, and you do not need to. PlayHQ is the official competition management platform your association runs on for registration, fixtures and scoring. BetterCricket sits on top of it and adds the club website, history, stats and analytics that PlayHQ does not provide."},
            {"q": "What does BetterCricket do that PlayHQ does not?", "a": "A public club website, your full historical stats and career profiles, weekly availability and team selection, match fees and member email, match-day social graphics, and opposition scouting and analytics."},
            {"q": "Do I have to enter data twice?", "a": "No. BetterCricket reads the match data your club already records, so your stats appear and update automatically with no second data entry."},
            {"q": "How much does BetterCricket cost?", "a": "A flat annual rate per club: BetterStats (the Core) is $399 a year, and modules are $149 each ($249 for BetterIQ), with a discount when you bundle. The same price covers one team or fifty."},
        ],
    },
    {
        "slug": "how-to-run-a-cricket-club",
        "title": "How to Run a Cricket Club: A Practical Guide",
        "date": "2026-06-19",
        "image": "/marketing/blog/season-yearbook.jpg",
        "description": (
            "A practical guide to running a community cricket club: the season "
            "cycle, the jobs that matter, and the tools that take the admin off "
            "volunteers."
        ),
        "body": [
            {"type": "p", "text": "Running a community cricket club is mostly admin, done by volunteers, in the evenings, for the love of it. The cricket is the easy part. This is a practical guide to the jobs that keep a club running and the tools that take the load off the people doing them."},
            {"type": "h2", "text": "The jobs that actually keep a club running"},
            {"type": "ul", "items": [
                "Registration, teams and grades at the start of the season",
                "Fixtures, scoring and results each week",
                "Collecting player availability and picking sides",
                "Chasing and recording match fees and membership",
                "Keeping the whole club in the loop by email and message",
                "A website that members, parents and sponsors actually use",
                "Looking after the club's stats, records and history",
                "Match-day social posts and a bit of opposition homework",
            ]},
            {"type": "h2", "text": "The season cycle"},
            {"type": "p", "text": "Most of these jobs follow a predictable rhythm. Pre-season is registration, grading and setting up teams. The in-season weeks are a loop of availability, selection, match day, fees and results. The end of the season is awards, the honour board and a yearbook, if anyone has the energy left to make one."},
            {"type": "h2", "text": "Where the time goes, and how to get it back"},
            {"type": "p", "text": "The admin is rarely hard. It is just scattered. Availability lives in a group chat, fees in a spreadsheet, the website in a builder no one remembers the login for, and the stats in the head of one dedicated volunteer. When that volunteer steps away, a lot of it walks out the door with them. The fix is to automate the repetitive parts and keep everything reading from one member list."},
            {"type": "h2", "text": "A simple stack for a modern club"},
            {"type": "p", "text": "Think in two layers. The official competition layer is PlayHQ, which Cricket Australia runs for registration, fixtures and scoring. On top of that you want a club platform that turns the same data into everything else, without entering anything twice."},
            {"type": "ul", "items": [
                "Stats, history and a public website: BetterStats",
                "Availability and team selection: BetterSelect",
                "Website and match-day graphics: BetterSocials",
                "Fees and member email: BetterAdmin",
                "Opposition scouting and analytics: BetterIQ",
            ]},
            {"type": "h2", "text": "Start small"},
            {"type": "p", "text": "You do not have to fix everything at once. Most clubs start by getting their history and stats online, because that is the part that quietly disappears, then add selection, fees and the rest as they go. The point is to make the club easier to run and better to belong to."},
            {"type": "links", "heading": "Related", "items": [
                {"label": "BetterCricket features", "href": "/features"},
                {"label": "The modules", "href": "/modules"},
                {"label": "Pricing", "href": "/pricing"},
                {"label": "PlayHQ", "href": "https://www.playhq.com", "external": True},
                {"label": "Cricket Australia", "href": "https://www.cricket.com.au", "external": True},
            ]},
            {"type": "callout", "text": "BetterCricket puts the club layer in one place: stats and history, a public website, availability and selection, fees and member email, social posts and analytics. Bring your club online and we handle the first full historical sync."},
        ],
        "faq": [
            {"q": "What software do I need to run a cricket club?", "a": "At minimum, the official competition platform your association uses (PlayHQ in Australia) for registration, fixtures and scoring. On top of that, a club platform like BetterCricket handles the website, stats, history, selection, fees, social posts and analytics from the same data."},
            {"q": "How do volunteers reduce the admin of running a club?", "a": "By automating the repetitive jobs and keeping everything on one member list. BetterCricket pulls match data automatically, so stats, leaderboards and records update after every game without anyone re-entering them."},
            {"q": "How do I keep my club's history and stats?", "a": "Get them online and keep them updating automatically. BetterCricket imports a club's full history on first sync, for many clubs going back decades, then refreshes after every match so the record never depends on one person's spreadsheet."},
            {"q": "How do I build a cricket club website?", "a": "BetterSocials gives your club a public website built from your own match data, in your crest, colours and fonts, with match-day graphics. It updates from the same data as your stats, so there is nothing to maintain by hand."},
        ],
    },
    {
        "slug": "how-to-merge-duplicate-player-records",
        "title": "How to Merge Duplicate Player Records in BetterCricket",
        "date": "2026-05-29",
        "image": "/marketing/blog/merge-duplicate-players.jpg",
        "description": (
            "Sometimes the same player ends up with two records: a Nick and a "
            "Nicholas, a maiden name and a married name. Here's how to combine "
            "them in BetterCricket so a player's full career sits on one profile."
        ),
    },
    {
        "slug": "why-your-cricket-club-needs-a-public-stats-page",
        "title": "Why Every Cricket Club Needs a Public Stats Page",
        "date": "2026-05-26",
        "image": "/marketing/blog/why-stats-page.jpg",
        "description": (
            "Players talk about their stats. Parents follow their kids' progress. "
            "Sponsors want to know who they're backing. None of them are well "
            "served by a PDF fixtures list. Here's what a proper public stats "
            "page changes."
        ),
    },
    {
        "slug": "why-your-clubs-history-keeps-getting-lost",
        "title": "Why your club's history keeps getting lost, and how to get it back",
        "date": "2026-05-24",
        "image": "/marketing/blog/playhq-migration.jpg",
        "description": (
            "Most clubs only ever see their most recent season. Decades of "
            "innings, spells and records sit scattered across spreadsheets and "
            "old systems, out of sight. Here's why club history keeps "
            "disappearing, and how BetterCricket brings it all back."
        ),
    },
    {
        "slug": "season-yearbook-automatically-generated",
        "title": "The Season Yearbook: Your Club's Story, Automatically Generated",
        "date": "2026-05-22",
        "image": "/marketing/blog/season-yearbook.jpg",
        "description": (
            "Every season your club plays 100+ games and generates thousands of "
            "performances. BetterCricket turns that data into a proper digital "
            "yearbook, auto-populated with stats and ready for your editorial "
            "content."
        ),
    },
    {
        "slug": "how-cricket-statistics-build-club-culture",
        "title": "How Cricket Statistics Build Club Culture",
        "date": "2026-05-21",
        "image": "/marketing/blog/club-culture.jpg",
        "description": (
            "The strongest cricket clubs share something beyond talented players: "
            "a sense of history and identity. Statistics are the raw material of "
            "that culture. Here's how tracking them properly changes a club."
        ),
    },
    {
        "slug": "cricket-milestones-numbers-that-define-a-career",
        "title": "Cricket Milestones: The Numbers That Define a Career",
        "date": "2026-05-23",
        "image": "/marketing/blog/milestones.jpg",
        "description": (
            "Cricket is a sport of numbers. Runs, wickets, and games accumulate "
            "over careers spanning 20+ years. Along the way, certain thresholds "
            "become landmarks. BetterCricket tracks every one of them "
            "automatically."
        ),
    },
    {
        "slug": "what-is-a-good-batting-average-in-club-cricket",
        "title": "What Is a Good Batting Average in Club Cricket?",
        "date": "2026-05-20",
        "image": "/marketing/blog/batting-average.jpg",
        "description": (
            "A guide to understanding batting averages at club level: what "
            "numbers to aim for, how grades affect expectations, and why career "
            "averages tell a different story to season averages."
        ),
    },
    {
        "slug": "5-reasons-your-cricket-club-is-losing-its-stats-history",
        "title": "5 Reasons Your Cricket Club Is Losing Its Stats History",
        "date": "2026-05-15",
        "image": "/marketing/blog/stats-history.jpg",
        "description": (
            "Most Australian cricket clubs have been running games for decades. "
            "Yet ask for career stats on a player who left five years ago, and "
            "you'll often get a shrug. Here's why club cricket history disappears."
        ),
    },
    {
        "slug": "understanding-bowling-economy-rate-in-club-cricket",
        "title": "Understanding Bowling Economy Rate in Club Cricket",
        "date": "2026-05-10",
        "image": "/marketing/blog/bowling-economy.jpg",
        "description": (
            "Bowling economy rate is one of the most useful numbers in "
            "limited-overs selection, yet it's often misread at club level. "
            "Here's how to use it properly, including what's actually good by "
            "format."
        ),
    },
]

# Slug list for the sitemap (preserves the order above).
BLOG_SLUGS: list[str] = [p["slug"] for p in BLOG_POSTS]

_BY_SLUG: dict[str, dict] = {p["slug"]: p for p in BLOG_POSTS}


def get_post(slug: str) -> dict | None:
    """Return the post metadata for a slug, or None if there's no such post."""
    return _BY_SLUG.get(slug)
