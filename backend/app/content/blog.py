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

# Newest first, matching the order shown on /blog.
BLOG_POSTS: list[dict[str, str]] = [
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

_BY_SLUG: dict[str, dict[str, str]] = {p["slug"]: p for p in BLOG_POSTS}


def get_post(slug: str) -> dict[str, str] | None:
    """Return the post metadata for a slug, or None if there's no such post."""
    return _BY_SLUG.get(slug)
