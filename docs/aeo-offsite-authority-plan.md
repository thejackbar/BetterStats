# Off-site authority plan for AEO

## Why this exists

Every AEO and SEO audit of betterat.cricket this year has landed on the same
split. The on-page work is strong: the site is readable without JavaScript, the
structured data is comprehensive, the content answers the questions clubs ask,
and the checkers that score technical factors now sit in the 70s and 90s.

The scores that stay low are not on-page. They are the brand scores. One tool
rated the brand 35 on ChatGPT, 41 on Perplexity and 44 on Gemini, across
Brand Recognition, Market Score, Presence Quality, Sentiment and Share of Voice.
Another flagged the backlink profile and social footprint. The "answer engines"
and "AI Overviews" surfaces read as not appearing yet.

These all measure one thing: how much the wider web knows and talks about
BetterCricket. An answer engine can only recommend you confidently if it has
seen you described, linked and reviewed in places it trusts. Good markup makes
you eligible to be quoted. Off-site authority is what gets you actually quoted.

This plan is the work that moves those numbers. It is slower than the on-page
work, measured in months rather than days, and most of it happens off the
codebase.

## What "authority" means to an answer engine

When ChatGPT or Perplexity answers "what is the best cricket club stats
platform", it leans on a few kinds of signal:

- **Entity records.** Does a knowledge base (Wikidata, Google's knowledge graph,
  Crunchbase) have a clean record of who BetterCricket is, who makes it, and
  what it does?
- **Directory and review listings.** Is BetterCricket listed on the software
  directories the engine reads for "best X" answers, the same ones that already
  carry CricketStatz, Pitchero and TeamApp?
- **Independent mentions and links.** Do other sites link to and write about
  BetterCricket, especially sites about cricket and club sport?
- **Reviews and sentiment.** Are there real reviews from real clubs, and are
  they positive?
- **Consistency.** Do the name, URL, founder and company details match
  everywhere they appear?

The actions below build each of these.

## The actions

### 1. Entity and knowledge graph

The goal is for the major knowledge bases to hold a clean, consistent record of
BetterCricket and BetterSports.

- Create a **Google Business Profile** for BetterSports, with the betterat.cricket
  URL, category, and a short description that matches the homepage.
- Create a **Crunchbase** profile for BetterSports, with the founder, founding
  year, location and product.
- Create a **Wikidata** item once there are a couple of independent references to
  cite. Wikidata feeds knowledge graphs that answer engines read.
- Keep the **name, URL, ABN (32 624 335 397) and founder** identical across every
  listing. The JSON-LD on the site already states these, so match it exactly
  everywhere else.
- The site schema already lists the X and Facebook profiles as `sameAs`. Make
  sure each of those profiles links back to betterat.cricket so the loop closes.

### 2. Software directories

This is the best early action to take first, because these directories are exactly
where answer engines look for "best software" answers, and the competitors are
already there.

- List BetterCricket on **Capterra, GetApp, G2, SoftwareSuggest, Software Advice,
  SourceForge and Crozdesk**. These all surfaced when we researched CricketStatz,
  Pitchero and TeamApp, which means engines read them for cricket-software
  answers.
- List BetterCricket on **AlternativeTo** as an alternative to PlayHQ and to
  CricketStatz. People searching "PlayHQ alternative" land there, and it is a
  clean match for the positioning.
- Launch on **Product Hunt**. It is a credible early backlink and gets the
  product in front of a tech audience.

Each listing should use the same description, category and feature list as the
site, so the entity stays consistent.

### 3. Reviews from real clubs

Reviews are social proof for people and a sentiment signal for engines.

- Ask the club admins already on BetterCricket (Applecross, High Wycombe,
  Murdoch, Portland and the rest) to leave a review on **Capterra, G2 and the
  Google Business Profile**. A handful of genuine reviews from named clubs is
  worth more than any amount of copy.
- Collect a short written quote and, where a club is happy, a logo, for a
  testimonials section on the site. Real club names and crests are hard to fake
  and read as trustworthy.

### 4. Backlinks from the cricket ecosystem

These are the most natural and most relevant links available, and they cost
nothing but a few emails.

- Ask **every onboarded club** to add a link to their BetterCricket stats page
  from their own website, Facebook page and email newsletter. A "Stats" or
  "Records" link to betterat.cricket/their-club is useful for their members and
  is a relevant backlink for us.
- Approach **local cricket associations** to be listed as a recommended or
  partner tool on their resources pages.
- Get listed in **cricket directories and link pages** that catalogue club tools.

### 5. Content distribution and mentions

The blog guides are written to answer real questions. They only earn authority
if people see and link to them.

- Share each guide where the question actually gets asked: **r/Cricket**,
  Australian club-cricket **Facebook groups**, cricket **forums**, and
  **LinkedIn**. Lead with the answer, not the link.
- Answer questions genuinely on **Reddit, Quora and forums** where "PlayHQ
  alternative", "merge players in PlayHQ" and "club cricket stats" come up, and
  point to the relevant guide when it actually helps. Helpful first, promotional
  never.
- Pitch a **guest article** or two to cricket sites and local sport media. The
  founder story, preserving a club's history at Applecross, is a strong angle.

### 6. Earned media

- Pitch the founder story to **local WA cricket and community media**, Cricket
  Australia community channels, and club-cricket newsletters. A club volunteer
  who built the platform his club now runs on is a real story.
- Each piece of coverage is both a backlink and a reference that can later
  support a Wikidata or Wikipedia entry.

### 7. Wikipedia

Worth naming so it is handled correctly. BetterCricket is **not yet notable
enough** for a Wikipedia article. Wikipedia needs multiple independent,
significant sources, and creating an article before those exist gets it deleted
and can hurt later attempts. Revisit this once the earned-media work in section 6
has produced a few solid pieces of independent coverage.

## Roadmap

Do the cheap, high-return work first.

**Phase 1, the first few weeks.** Google Business Profile, Crunchbase, the
software directory listings (Capterra, GetApp, G2, SoftwareSuggest, AlternativeTo,
Product Hunt), and an email to every onboarded club asking for a stats link and a
review. Lock the name, URL, ABN and founder consistent across all of them.

**Phase 2, the next one to three months.** Collect club reviews and
testimonials, distribute the blog guides into the cricket communities, line up
association and directory backlinks, and place a guest article or two.

**Phase 3, three to six months and beyond.** Pursue earned media and the founder
story, build the independent coverage, then revisit Wikidata depth and a
Wikipedia article once the sources support it.

## How to measure it

Track these monthly so the work stays honest.

- **Re-run the AEO checkers** and watch the brand scores and the answer-engine,
  AI Overview and People Also Ask surfaces. These are the numbers this plan is
  built to move.
- **Ask the engines directly.** Once a month, ask ChatGPT, Perplexity and Gemini
  the target questions ("best cricket club stats platform that works with
  PlayHQ", "how to merge players in PlayHQ", "where to display historical cricket
  stats") and record whether BetterCricket appears and how it is described.
- **Count referring domains** in Google Search Console or a backlink tool, and
  track how many onboarded clubs link back.
- **Track reviews and listings** as they go live, so the directory and review
  coverage is visible at a glance.

## The short version

The site is now about as strong as on-page AEO gets. The remaining gap is that
the wider web does not yet know BetterCricket well enough for an answer engine to
recommend it with confidence. Closing that gap is directory listings, club
backlinks, real reviews, content that gets shared, and earned coverage, built up
over a few months and measured against the brand scores.
