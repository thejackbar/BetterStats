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
        "slug": "how-to-merge-players-in-playhq-cricket",
        "title": "How to Merge Duplicate Players in PlayHQ Cricket",
        "date": "2026-06-21",
        "image": "/marketing/blog/merge-duplicate-players.jpg",
        "description": (
            "How merging duplicate players works in PlayHQ cricket, who is allowed "
            "to do it, and how BetterCricket merges a club's duplicate stats "
            "reversibly."
        ),
        "body": [
            {"type": "p", "text": "Duplicate players are one of the most common headaches in club cricket. The same person ends up with two records, a Nick and a Nicholas, and their stats split across both. If you have gone looking for how to merge them in PlayHQ, here is what you can and cannot do, and how BetterCricket handles it."},
            {"type": "h2", "text": "Can a club merge players in PlayHQ?"},
            {"type": "p", "text": "Usually not on your own. PlayHQ does merge duplicate participant profiles, but the tool is restricted to Super Admins within an Administration Body, which is your association rather than your club. Club and association admins are asked to contact their sporting organisation to get a merge done."},
            {"type": "h2", "text": "How merging works in PlayHQ"},
            {"type": "p", "text": "A Super Admin opens Participants, searches for the profile to keep, selects the duplicate, and confirms the merge. It combines registration history, statistics and transfer records onto one profile. PlayHQ is clear that the merge cannot be undone, and it can fail if too few personal details match. Players can also claim and merge their own duplicate accounts through Find My Profiles, verified by an email or text code."},
            {"type": "h2", "text": "Where this leaves a club statistician"},
            {"type": "p", "text": "The PlayHQ merge is built around participant accounts and registration, and it is gated behind your association. For the duplicate-player problem you actually see in your stats, a player whose career is split across two records, you are often waiting on someone else to act, and a wrong merge cannot be reversed."},
            {"type": "h2", "text": "How BetterCricket merges duplicate players"},
            {"type": "p", "text": "BetterCricket flags likely duplicates when it imports your club's history. A club admin reviews each pair and merges it in a click, and every innings, spell, catch and partnership moves onto one profile. It is fully reversible, so an accidental merge can be undone, and a manual merge handles name changes the scanner cannot spot, like a maiden name and a married name."},
            {"type": "h2", "text": "Side by side"},
            {"type": "table", "headers": ["", "PlayHQ", "BetterCricket"], "rows": [
                ["Who can merge", "Super Admins at your association", "Your own club admins"],
                ["What it combines", "Participant accounts and registration", "Every innings, spell, catch and partnership"],
                ["Reversible", "No, it cannot be undone", "Yes, undo any time"],
                ["Name changes", "Needs enough matching fields", "Manual merge by name"],
                ["Where the stats show", "PlayHQ profile", "Your public club website"],
            ]},
            {"type": "links", "heading": "Related", "items": [
                {"label": "Merging duplicate players in BetterCricket", "href": "/blog/how-to-merge-duplicate-player-records"},
                {"label": "BetterCricket features", "href": "/features"},
                {"label": "Pricing", "href": "/pricing"},
                {"label": "PlayHQ duplicate profile management", "href": "https://support.playhq.com/hc/en-au/articles/4406346808345-Participant-Profile-Duplicate-Management", "external": True},
                {"label": "PlayHQ", "href": "https://www.playhq.com", "external": True},
            ]},
            {"type": "callout", "text": "BetterCricket finds and merges your duplicate players when it brings your history across, and every merge can be undone. Bring your club online and we handle the first full historical sync."},
        ],
        "faq": [
            {"q": "How can I merge players in PlayHQ cricket?", "a": "PlayHQ merges duplicate participant profiles, but only a Super Admin within your Administration Body, which is your association, can do it. Club admins are asked to contact their organisation. The merge combines registration, statistics and transfers, and it cannot be undone."},
            {"q": "Can a club admin merge duplicate players in PlayHQ?", "a": "Usually not directly. The duplicate-profile tool is restricted to Super Admins at the Administration Body, so club admins contact their association. Players can also merge their own duplicate accounts through Find My Profiles, verified by email or text."},
            {"q": "Is merging players in PlayHQ reversible?", "a": "No. PlayHQ states a profile merge cannot be undone. BetterCricket's merge is reversible, so you can undo it if the wrong two records get joined."},
            {"q": "How does BetterCricket merge duplicate players?", "a": "It flags likely duplicates when it imports your history, then a club admin merges each pair in a click. Every innings, spell, catch and partnership moves onto one profile, and the merge can be undone."},
        ],
        "howto": [
            {"name": "Get Super Admin access", "text": "Profile merging is restricted to Super Admins within your Administration Body, so a club admin contacts their association to have it done."},
            {"name": "Open Participants and find the profile to keep", "text": "From the menu, open Participants and search for the profile you want to keep."},
            {"name": "Select the duplicate and review", "text": "Choose the duplicate profile and review the fields. PlayHQ keeps the destination profile details where they differ."},
            {"name": "Confirm the merge", "text": "Confirm to combine registration, statistics and transfers. PlayHQ cannot undo this, so check carefully first."},
        ],
    },
    {
        "slug": "bettercricket-vs-teamapp",
        "title": "BetterCricket vs TeamApp: Comms App or Club Platform?",
        "date": "2026-06-21",
        "image": "/marketing/blog/merge-duplicate-players.jpg",
        "description": (
            "TeamApp keeps your members talking; BetterCricket runs the cricket. "
            "How a comms app and a club platform compare, and why clubs use both."
        ),
        "body": [
            {"type": "p", "text": "TeamApp (Stack Team App) and BetterCricket both turn up when a club is getting organised online, but they do different things. TeamApp is about talking to your members. BetterCricket is about running the cricket."},
            {"type": "h2", "text": "What each one is"},
            {"type": "p", "text": "TeamApp is a free communications and membership app. It gives any club or social group a quick smartphone app and a website, with news, events, push notifications, chat, and the option to sell tickets and memberships. BetterCricket is a cricket club platform: automatic stats and history, a public club site, and modules for selection, social posts, fees and opposition analysis."},
            {"type": "h2", "text": "Side by side"},
            {"type": "table", "headers": ["", "TeamApp", "BetterCricket"], "rows": [
                ["Main job", "Club communication", "Running the club"],
                ["App and website", "Free app and website", "Public website, runs in the browser"],
                ["News, chat, push notifications", "Yes", "Member email with BetterAdmin"],
                ["Cricket stats and history", "No", "Full career stats, decades imported"],
                ["Leaderboards, records, yearbooks", "No", "Yes"],
                ["Team selection", "Rosters and attendance", "Availability plus smart selection"],
                ["Opposition analysis", "No", "Yes, with BetterIQ"],
                ["Pricing", "Free, with ads (paid to remove)", "Flat annual rate per club"],
            ]},
            {"type": "h2", "text": "Where TeamApp is strong"},
            {"type": "p", "text": "If you want a free, quick way to get an app in front of your members and keep everyone in the loop, TeamApp is hard to beat. It sets up in minutes and works for any club, not just cricket."},
            {"type": "h2", "text": "Where BetterCricket is strong"},
            {"type": "p", "text": "TeamApp does not handle cricket stats, history or analysis. If you want your full history online, leaderboards and records, season yearbooks, smart selection and opposition scouting, that is what BetterCricket is built for. Plenty of clubs run a comms app for chat and BetterCricket for the cricket."},
            {"type": "links", "heading": "Related", "items": [
                {"label": "BetterCricket features", "href": "/features"},
                {"label": "Pricing", "href": "/pricing"},
                {"label": "The modules", "href": "/modules"},
                {"label": "TeamApp", "href": "https://www.teamapp.com", "external": True},
                {"label": "PlayHQ", "href": "https://www.playhq.com", "external": True},
            ]},
            {"type": "callout", "text": "BetterCricket handles the cricket: stats, history, the website, selection and analysis. Bring your club online and we handle the first full historical sync."},
        ],
        "faq": [
            {"q": "Is TeamApp a cricket stats platform?", "a": "No. TeamApp is a free communications and membership app for any club. It handles news, chat, events and notifications, not cricket stats, history or analysis."},
            {"q": "Can I use TeamApp and BetterCricket together?", "a": "Yes. Many clubs use a comms app for chat and BetterCricket for stats, the website and the cricket-specific jobs."},
            {"q": "Is BetterCricket free like TeamApp?", "a": "TeamApp is free with ads. BetterCricket is a flat annual rate per club, from $399 for the Core, and the stats site is ad free."},
            {"q": "What does BetterCricket do that TeamApp does not?", "a": "Full cricket stats and history, leaderboards and records, season yearbooks, smart team selection, and opposition analysis."},
        ],
    },
    {
        "slug": "bettercricket-vs-play-cricket",
        "title": "BetterCricket vs Play-Cricket: How They Fit Together",
        "date": "2026-06-21",
        "image": "/marketing/blog/playhq-migration.jpg",
        "description": (
            "Play-Cricket runs UK league cricket; BetterCricket adds the club "
            "layer on top. How the two fit together for an English club."
        ),
        "body": [
            {"type": "p", "text": "Play-Cricket is to UK club cricket what PlayHQ is to Australia: the official platform clubs run on. BetterCricket is the club layer on top, and the two work together rather than against each other."},
            {"type": "h2", "text": "What each one is"},
            {"type": "p", "text": "Play-Cricket is the ECB's official platform for UK club cricket. Fixtures, results, league tables, scorecards and a free basic club site run through it. BetterCricket is a cricket club platform that connects to Play-Cricket through its official API and adds a richer public website, your full history and stats, selection, social posts and analytics. It started in Australia and is bringing the same approach to UK clubs."},
            {"type": "h2", "text": "Side by side"},
            {"type": "table", "headers": ["", "Play-Cricket", "BetterCricket"], "rows": [
                ["Main job", "Official UK competition admin", "Running the club"],
                ["Fixtures, results, league tables", "Yes", "Reads from Play-Cricket"],
                ["Scorecards", "Yes", "Reads finished scorecards"],
                ["Club website", "Free basic site", "Full branded club site"],
                ["Full history and career stats", "Recent seasons", "Decades, brought across on setup"],
                ["Team selection and availability", "No", "Yes, with BetterSelect"],
                ["Match-day social graphics", "No", "Yes, with BetterSocials"],
                ["Opposition analysis", "No", "Yes, with BetterIQ"],
                ["Pricing", "Free, funded by the ECB", "Flat annual rate per club"],
            ]},
            {"type": "h2", "text": "How they work together"},
            {"type": "p", "text": "You keep running fixtures and results in Play-Cricket. BetterCricket reads that data through the official API with your club's token, so your stats and website stay current and you enter the data once."},
            {"type": "h2", "text": "Where each one is strong"},
            {"type": "p", "text": "Play-Cricket is the official platform, it is free, and every UK club is already on it for league cricket. BetterCricket adds the parts it does not cover: a proper club website, your full history online, leaderboards and records, season yearbooks, smart selection and opposition scouting, all from the same data."},
            {"type": "links", "heading": "Related", "items": [
                {"label": "BetterCricket features", "href": "/features"},
                {"label": "Pricing", "href": "/pricing"},
                {"label": "The modules", "href": "/modules"},
                {"label": "Play-Cricket", "href": "https://www.play-cricket.com", "external": True},
                {"label": "England and Wales Cricket Board", "href": "https://www.ecb.co.uk", "external": True},
            ]},
            {"type": "callout", "text": "BetterCricket reads your Play-Cricket data through the official API and turns it into a club website, a full history and analytics. Get in touch to talk about bringing it to your club."},
        ],
        "faq": [
            {"q": "Is BetterCricket a replacement for Play-Cricket?", "a": "No. Play-Cricket is the ECB's official platform for fixtures, results and league tables. BetterCricket sits on top and adds a richer website, full history, stats and analytics."},
            {"q": "How does BetterCricket get my Play-Cricket data?", "a": "Through the official Play-Cricket API, using your club's own API token, so you do not enter anything twice."},
            {"q": "Is Play-Cricket free?", "a": "Yes. Play-Cricket is funded by the ECB and free for clubs. BetterCricket is a flat annual rate per club for the extra website, stats and analytics layer."},
            {"q": "Is BetterCricket available in the UK?", "a": "BetterCricket started in Australia and is bringing its platform to UK clubs through the Play-Cricket API. Get in touch to talk about your club."},
        ],
    },
    {
        "slug": "bettercricket-vs-playhq",
        "title": "BetterCricket vs PlayHQ: How They Fit Together",
        "date": "2026-06-21",
        "image": "/marketing/blog/stats-history.jpg",
        "description": (
            "PlayHQ runs the competition; BetterCricket runs the club. How the "
            "two cricket platforms differ, and why most clubs use both."
        ),
        "body": [
            {"type": "p", "text": "BetterCricket and PlayHQ get compared a lot, but they are not really rivals. They do different jobs, and most clubs end up using both. Here is how they line up."},
            {"type": "h2", "text": "What each one is for"},
            {"type": "p", "text": "PlayHQ is Cricket Australia's official competition management platform. Registration, fixtures, scoring, results and ladders run through it, and your association runs on it. BetterCricket is the club layer that sits on top: a public club website, your full history and stats, player profiles, selection, fees, social posts and analytics."},
            {"type": "h2", "text": "Side by side"},
            {"type": "table", "headers": ["", "PlayHQ", "BetterCricket"], "rows": [
                ["Main job", "Official competition management", "Running the club"],
                ["Registration and fixtures", "Yes", "Reads from your competition data"],
                ["Live scoring", "Yes", "Reads finished scorecards"],
                ["Public club website", "Basic club pages", "Full branded club site"],
                ["Full history and career stats", "Recent seasons", "Decades, imported on setup"],
                ["Team selection and availability", "No", "Yes, with BetterSelect"],
                ["Match-day social graphics", "No", "Yes, with BetterSocials"],
                ["Fees and member email", "Registration payments", "Yes, with BetterAdmin"],
                ["Opposition analysis", "No", "Yes, with BetterIQ"],
                ["Pricing", "Registration and transaction fees", "Flat annual rate per club"],
            ]},
            {"type": "h2", "text": "Do they overlap?"},
            {"type": "p", "text": "Only a little. Both show fixtures and results. BetterCricket brings that data across and turns it into a website, a history and analytics. You keep scoring in PlayHQ exactly as you do now."},
            {"type": "h2", "text": "Which do you need?"},
            {"type": "p", "text": "You do not choose PlayHQ. Your association runs on it, so your club uses it whatever else you do. The question worth asking is whether you also want a proper club website, your full history online, and the tools to run selection, fees and match-day from the same data. That is the part BetterCricket adds."},
            {"type": "links", "heading": "Related", "items": [
                {"label": "BetterCricket features", "href": "/features"},
                {"label": "Pricing", "href": "/pricing"},
                {"label": "The modules", "href": "/modules"},
                {"label": "PlayHQ", "href": "https://www.playhq.com", "external": True},
                {"label": "Cricket Australia", "href": "https://www.cricket.com.au", "external": True},
            ]},
            {"type": "callout", "text": "BetterCricket turns your club's match data into a full website, a full history and analytics. Bring your club online and we handle the first full historical sync."},
        ],
        "faq": [
            {"q": "Is BetterCricket a replacement for PlayHQ?", "a": "No. PlayHQ is the official competition platform for registration, fixtures and scoring. BetterCricket sits on top of it and adds the club website, history, stats and analytics."},
            {"q": "Can BetterCricket read my PlayHQ data?", "a": "BetterCricket brings your club's match history in and keeps it current automatically, so you never have to enter anything twice."},
            {"q": "How much does each one cost?", "a": "PlayHQ has no mandatory club setup fee and is funded through registration and small transaction fees, including a National Registration Fee. BetterCricket is a flat annual rate per club, from $399 for the Core, the same for one team or fifty."},
            {"q": "Do I still score in PlayHQ?", "a": "Yes. Nothing about your match day changes. BetterCricket reads the finished scorecards and updates your stats after every game."},
        ],
    },
    {
        "slug": "bettercricket-vs-cricketstatz",
        "title": "BetterCricket vs CricketStatz: Which Suits Your Club?",
        "date": "2026-06-21",
        "image": "/marketing/blog/milestones.jpg",
        "description": (
            "CricketStatz is a deep cricket stats engine; BetterCricket is a club "
            "platform with stats built in. How they compare for an Australian club."
        ),
        "body": [
            {"type": "p", "text": "CricketStatz is probably the closest thing to BetterCricket's stats core, so it is a fair comparison. Both turn cricket data into stats and web pages. They aim at different users, though."},
            {"type": "h2", "text": "What each one is"},
            {"type": "p", "text": "CricketStatz is dedicated cricket statistics software. It is browser based, handles live scoring or imported scorecards, and produces a large library of statistical reports for leagues, clubs, teams and players. BetterCricket is a club platform built for Australian cricket: the same kind of stats and a public club website, plus modules for selection, social posts, fees and opposition analysis."},
            {"type": "h2", "text": "Side by side"},
            {"type": "table", "headers": ["", "CricketStatz", "BetterCricket"], "rows": [
                ["Main job", "Cricket statistics", "Running the club"],
                ["Statistical depth", "Very deep, 190+ reports", "Deep, focused on what clubs use"],
                ["Live scoring", "Yes", "Reads finished scorecards"],
                ["Imports match history", "Yes", "Yes, automatic"],
                ["Public club website", "Generated stat pages", "Full branded club site"],
                ["History import", "You load the matches", "Decades imported on setup"],
                ["Selection, fees, socials, scouting", "No", "Yes, the modules"],
                ["Built for", "Statisticians, any country", "Australian clubs"],
                ["Pricing", "Annual plans by match count", "Flat annual rate per club"],
            ]},
            {"type": "h2", "text": "Where CricketStatz is strong"},
            {"type": "p", "text": "If your club has a dedicated statistician who wants every report imaginable and full control over scoring and data entry, CricketStatz is a strong choice and has been at it for years. Its statistical depth is hard to match."},
            {"type": "h2", "text": "Where BetterCricket is strong"},
            {"type": "p", "text": "If you would rather the stats were handled for you, alongside a public club site, automatic history import and the tools to run selection, fees and match-day, BetterCricket covers more of the club in one place and is built for the Australian game."},
            {"type": "links", "heading": "Related", "items": [
                {"label": "BetterCricket features", "href": "/features"},
                {"label": "Pricing", "href": "/pricing"},
                {"label": "The modules", "href": "/modules"},
                {"label": "CricketStatz", "href": "https://www.cricketstatz.com", "external": True},
                {"label": "PlayHQ", "href": "https://www.playhq.com", "external": True},
            ]},
            {"type": "callout", "text": "BetterCricket handles your stats automatically and adds a public club website and the tools to run the rest of the club. Bring your club online and we handle the first full historical sync."},
        ],
        "faq": [
            {"q": "Is BetterCricket like CricketStatz?", "a": "Both do cricket stats. CricketStatz is a dedicated statistics tool with a deep report library. BetterCricket is a club platform with stats plus a public website and modules for selection, fees, socials and scouting."},
            {"q": "Does BetterCricket import my club's history automatically?", "a": "Yes. It imports your full history on setup and updates after every game, so you do not load matches by hand."},
            {"q": "Which is better for a club statistician?", "a": "CricketStatz suits a statistician who wants the maximum number of reports and full control. BetterCricket suits a club that wants the stats automated and the rest of the club run from the same data."},
            {"q": "How is the pricing different?", "a": "CricketStatz charges annual plans sized by the number of matches played in a year. BetterCricket charges a flat annual rate per club, the same for one team or fifty."},
        ],
    },
    {
        "slug": "bettercricket-vs-pitchero",
        "title": "BetterCricket vs Pitchero: Cricket-Native or All-Sport?",
        "date": "2026-06-21",
        "image": "/marketing/blog/batting-average.jpg",
        "description": (
            "Pitchero builds club websites for any sport; BetterCricket is built "
            "for cricket. How they compare on stats, websites and price."
        ),
        "body": [
            {"type": "p", "text": "Pitchero and BetterCricket both help you run a club and put it online, so they come up together. The big difference is focus. Pitchero does many sports. BetterCricket does cricket."},
            {"type": "h2", "text": "What each one is"},
            {"type": "p", "text": "Pitchero is a club website and management platform used across many sports, mainly in the UK. It gives you a website, a club app, membership and payments. BetterCricket is built for cricket: automatic stats and history, a public club site, and modules for selection, social posts, fees and opposition analysis."},
            {"type": "h2", "text": "Side by side"},
            {"type": "table", "headers": ["", "Pitchero", "BetterCricket"], "rows": [
                ["Built for", "Any sport, UK focus", "Cricket, Australian focus"],
                ["Club website", "Yes, template based", "Yes, built from your match data"],
                ["Membership and payments", "Yes", "Yes, with BetterAdmin"],
                ["Club app", "Yes", "Runs in the browser"],
                ["Cricket stats and history", "Basic results", "Full career stats, decades imported"],
                ["Leaderboards, records, yearbooks", "No", "Yes"],
                ["Team selection", "Availability", "Availability plus smart selection"],
                ["Opposition analysis", "No", "Yes, with BetterIQ"],
                ["Pricing", "Free, then £38 or £99 a month", "Flat annual rate per club"],
            ]},
            {"type": "h2", "text": "Where Pitchero is strong"},
            {"type": "p", "text": "If you run several sports, or want a polished general club website with an app and you are in the UK, Pitchero is a mature option with a free tier to get started."},
            {"type": "h2", "text": "Where BetterCricket is strong"},
            {"type": "p", "text": "If you are a cricket club that cares about stats, history and the cricket-specific jobs, BetterCricket goes deeper: automatic history import, leaderboards and records, season yearbooks, smart selection and opposition scouting, all built for the Australian game."},
            {"type": "links", "heading": "Related", "items": [
                {"label": "BetterCricket features", "href": "/features"},
                {"label": "Pricing", "href": "/pricing"},
                {"label": "The modules", "href": "/modules"},
                {"label": "Pitchero", "href": "https://www.pitchero.com", "external": True},
                {"label": "PlayHQ", "href": "https://www.playhq.com", "external": True},
            ]},
            {"type": "callout", "text": "BetterCricket is built for the cricket-specific jobs Pitchero does not cover: automatic stats and history, leaderboards, records, yearbooks, selection and scouting. Bring your club online and we handle the first full historical sync."},
        ],
        "faq": [
            {"q": "Is Pitchero good for cricket clubs?", "a": "Pitchero works across many sports and gives you a website, membership and payments. It does not go deep on cricket stats, history, leaderboards or analysis, which is where a cricket-native platform fits."},
            {"q": "Does BetterCricket have an app to install?", "a": "BetterCricket is a public website that works on any phone, tablet or laptop, so you open a link rather than install an app."},
            {"q": "How do the prices compare?", "a": "Pitchero has a free tier and paid plans at £38 and £99 a month at the time of writing. BetterCricket is a flat annual rate per club, from $399 for the Core, the same for one team or fifty."},
            {"q": "Which is better for an Australian cricket club?", "a": "BetterCricket is built for Australian cricket, with automatic history import and cricket-specific tools. Pitchero is a general, UK-focused club platform."},
        ],
    },
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
            {"q": "Where does the opposition data come from?", "a": "The same scorecards your matches already produce, the games your club has played against them."},
            {"q": "Does BetterIQ need extra scoring?", "a": "No. It reads the scorecards you already generate and builds the opposition report from them, so your match day does not change."},
        ],
        "howto": [
            {"name": "Pull their recent scorecards", "text": "Find the opposition recent scorecards on PlayHQ to see how they have been going."},
            {"name": "Find the danger players", "text": "Look for the batter averaging well clear of their side and the bowler taking wickets most weeks, and note how the batters get out."},
            {"name": "Use your own head-to-head", "text": "Check your own scorecards against them for who has scored runs and which of your bowlers has their number."},
            {"name": "Build a one-page plan", "text": "Turn it into a few clear calls: who to get out early, who to bowl dry, and what a par score looks like at the ground."},
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
        "howto": [
            {"name": "List what the site needs", "text": "Decide on fixtures and results, teams, stats, news, sponsors and contact links, and a way to keep it current."},
            {"name": "Choose how to build it", "text": "Compare a general website builder, a generic club system, and a cricket platform that builds the site from your match data."},
            {"name": "Connect it to your match data", "text": "Wire the site to the data your club already records so fixtures, results and stats fill themselves in."},
            {"name": "Keep it current automatically", "text": "Let the platform refresh the site after every game so it stays accurate on its own."},
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
            {"q": "How do I get better statistics for my cricket club?", "a": "Get your full history online and keep it updating automatically. BetterCricket imports your club's complete batting, bowling and fielding history, then refreshes after every game, with leaderboards, records and player profiles."},
            {"q": "Where can I display all my historical cricket stats?", "a": "On a public club website built from your data. BetterCricket imports a club's full history, for many clubs going back decades, and shows it as player profiles, leaderboards, records and season yearbooks that update after every game."},
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
            {"type": "p", "text": "Nothing about your match day changes. You keep scoring in PlayHQ exactly as you do now. BetterCricket brings that history in, reconciles it and keeps your stats current after every game. The short version: use PlayHQ because you have to, and BetterCricket because you want to."},
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
            {"q": "What is the best community cricket stats platform that is not PlayHQ but works with it?", "a": "BetterCricket. It is built for community cricket stats and sits alongside PlayHQ, keeping your stats, history and website current without entering anything twice. PlayHQ stays your official competition platform."},
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
        "howto": [
            {"name": "Map the jobs", "text": "List the recurring jobs: registration, fixtures, availability and selection, fees, comms, the website, and stats."},
            {"name": "Use the official competition layer", "text": "Run registration, fixtures and scoring through PlayHQ, the platform your association uses."},
            {"name": "Add a club platform on top", "text": "Use a club platform to turn the same data into your website, stats, selection, fees and analysis without entering it twice."},
            {"name": "Start small and automate", "text": "Begin by getting your history and stats online, then add selection, fees and the rest as you go."},
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
        "howto": [
            {"name": "Open Merge Duplicates", "text": "In the admin sidebar, open Merge Duplicates. BetterCricket scans your players and surfaces pairs with matching names."},
            {"name": "Review the suggested pair", "text": "Each pair shows the two records side by side with seasons, runs, wickets and game counts so you can confirm they are the same person."},
            {"name": "Confirm the merge", "text": "Choose which record to keep and confirm. Every innings, spell, catch and partnership moves onto the surviving profile."},
            {"name": "Use Manual Merge for name changes", "text": "For records under different names, like a maiden and married name, use the Manual Merge panel to pick the two records yourself."},
            {"name": "Undo if needed", "text": "Every merge appears in the Merge History with an Undo button, so an accidental merge can be rolled back."},
        ],
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
