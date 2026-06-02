# Community Cricket Analytics Platform Brief

## Purpose

This document outlines a long-form analytics framework for building professional-style cricket analysis for community cricket.

The goal is to give clubs, captains, coaches and players the ability to analyse themselves and their opposition at a level rarely seen outside professional cricket.

The assumption is that the available data is equivalent to online scoring and historical cricket scorecards. This means there is access to scorecard-level and potentially ball-by-ball data, but not broadcast or tracking data such as:

- Bowling speeds
- Pitch maps
- Wagon wheels
- Ball tracking
- Hawkeye-style trajectories
- Release points
- Swing or seam data
- Fielding position coordinates

Despite that, there is still enough data to build very powerful analytics using context, role, phase, matchups, venue history, score progression and historical performance patterns.

## Core Product Positioning

The product should not just be framed as better cricket stats.

A stronger positioning is:

**Professional-level opposition analysis for community cricket.**

Other possible positioning lines:

- Know your opponent before you play them.
- Community cricket analysis that goes beyond scorecards.
- Turn historical cricket stats into match-winning insight.
- The cricket analysis platform built for captains, coaches and community clubs.
- The kind of opposition analysis most community clubs have never had access to.

The strongest product idea is that BetterStats becomes less of a statistics table and more of a digital cricket analyst.

It should help users answer:

- Who matters in the opposition?
- Who scores their runs?
- Who takes their wickets?
- Where do they usually win games?
- Where do they break down?
- Which batters should we attack?
- Which bowlers should we see off?
- Which matchups work in our favour?
- What score is competitive at this ground?
- How should we structure our innings?
- Who should bowl to whom?
- What is the simplest game plan to beat this team?

## Professional Cricket Analytics Principles Translated to Community Cricket

Professional teams usually do not stop at raw averages. They analyse performance through context.

Key professional principles that can be translated to community cricket:

- Role matters.
- Phase matters.
- Match state matters.
- Opposition matters.
- Venue matters.
- Pressure matters.
- Matchups matter.
- Historical tendencies matter.
- Repeatable skills matter more than one-off scorecard outcomes.
- Averages need context.
- Wickets need context.
- Economy rates need context.
- Strike rates need context.
- Runs scored in pressure situations are more valuable.
- Wickets of key batters are more valuable than tail-end wickets.
- A bowler who creates pressure may be more valuable than a bowler who gets lucky wickets.
- A batter who reliably gets the team through dangerous phases may be more valuable than raw run totals suggest.

For community cricket, this means transforming scorecard and ball-by-ball data into:

- Phase splits
- Role profiles
- Player-vs-player matchups
- Team-vs-team reports
- Venue trends
- Chasing and defending profiles
- Pressure analysis
- Partnership analysis
- Form trends
- Captaincy recommendations
- Match plan generation
- Player impact scores
- Opposition scouting cards

## Assumed Data Availability

The platform can be built using data commonly available from online scoring platforms.

Potential data fields:

- Match ID
- Season
- Grade
- Competition
- Round
- Match date
- Venue
- Home team
- Away team
- Toss winner, if available
- Toss decision, if available
- Match format
- Innings number
- Batting team
- Bowling team
- Team score
- Team wickets
- Overs faced
- Result
- Margin
- Batting card
- Bowling card
- Fielding dismissals
- Fall of wickets
- Partnerships
- Ball-by-ball events, if available
- Batter
- Non-striker
- Bowler
- Over
- Ball
- Batter runs
- Extras
- Extra type
- Wicket
- Wicket type
- Dismissed batter
- Fielder involved
- Bowler credited

## Useful Optional Metadata

To unlock more advanced insights, BetterStats could allow clubs to manually tag players and venues.

### Player Metadata

- Right-hand batter
- Left-hand batter
- Opening batter
- Top-order batter
- Middle-order batter
- Lower-order batter
- Tailender
- Anchor
- Aggressive batter
- Finisher
- Wicketkeeper
- Captain
- Pace bowler
- Medium pace bowler
- Fast bowler
- Spin bowler
- Off spinner
- Leg spinner
- Left-arm orthodox
- Left-arm wrist spin
- Left-arm pace
- Right-arm pace
- New-ball bowler
- Death bowler
- Part-time bowler
- All-rounder
- Junior player
- Senior player

### Venue Metadata

- Turf wicket
- Synthetic wicket
- Hard wicket
- Small boundary
- Large boundary
- Fast outfield
- Slow outfield
- High-scoring venue
- Low-scoring venue
- Home ground
- Away ground

### Match Metadata

- Regular season
- Final
- Semi-final
- Grand final
- Two-day match
- One-day match
- T20
- Rain affected
- Reduced overs
- Forfeit
- Friendly
- Representative match

## Recommended Analysis Structure

The analytics should be organised around four major areas:

1. Player-by-player analysis
2. Team-by-team analysis
3. Player-vs-player analysis
4. Team-vs-team analysis

A fifth layer should sit above these:

5. Match planning and opposition intelligence

---

# 1. Player-by-Player Batting Analysis

## 1.1 Basic Batting Profile

Standard metrics every player profile should include:

- Matches
- Innings
- Not outs
- Runs
- Highest score
- Average
- Strike rate
- Balls faced
- Hundreds
- Fifties
- Ducks
- Fours
- Sixes
- Boundary runs
- Percentage of team runs
- Balls per dismissal
- Runs per innings
- Runs per match
- Average when batting first
- Average when chasing
- Average in wins
- Average in losses
- Average at home
- Average away
- Average by grade
- Average by season
- Average by venue
- Average by opponent
- Average by batting position
- Median score
- Mode score range
- Percentage of innings reaching double figures
- Percentage of innings reaching 25
- Percentage of innings reaching 50
- Percentage of innings reaching 100

## 1.2 Batting Style Profile

These metrics show how a batter scores rather than just how many they score.

- Dot ball percentage
- Single percentage
- Two percentage
- Three percentage
- Four percentage
- Six percentage
- Scoring shot percentage
- Strike rotation rate
- Boundary reliance
- Percentage of runs in boundaries
- Non-boundary scoring rate
- Balls per boundary
- Balls per four
- Balls per six
- Dot-to-boundary ratio
- Dot-to-single ratio
- Strike rate excluding boundaries
- Strike rate excluding sixes
- Strike rate from balls 1 to 10
- Strike rate from balls 11 to 25
- Strike rate from balls 26 to 50
- Strike rate after 50 balls
- Strike rate after reaching 25
- Strike rate after reaching 50
- Acceleration profile
- Slow starter index
- Fast starter index
- Anchor profile
- Boundary hitter profile
- Strike rotator profile
- High-risk hitter profile
- Low-risk accumulator profile

## 1.3 Batting Phase Analysis

Suggested phase definitions:

### T20

- Overs 1 to 6
- Overs 7 to 15
- Overs 16 to 20

### 40-over cricket

- Overs 1 to 10
- Overs 11 to 25
- Overs 26 to 35
- Overs 36 to 40

### 50-over cricket

- Overs 1 to 10
- Overs 11 to 30
- Overs 31 to 40
- Overs 41 to 50

### Two-day cricket

- New ball phase
- Pre-drinks phase
- Post-drinks phase
- Pre-tea phase
- Final hour
- Second innings chase phase
- Second innings survival phase

Metrics by phase:

- Runs by phase
- Balls faced by phase
- Strike rate by phase
- Average by phase
- Dot ball percentage by phase
- Boundary percentage by phase
- Dismissal rate by phase
- Percentage of innings spent in each phase
- Best phase
- Weakest phase
- Powerplay suitability
- Middle-over suitability
- Death-over suitability
- Chase finisher suitability
- Collapse repair suitability
- Anchor suitability
- Acceleration suitability

## 1.4 Starts and Conversion

Conversion is one of the most useful ways to analyse community batters.

- Dismissed under 5
- Dismissed under 10
- Dismissed between 10 and 24
- Dismissed between 25 and 49
- Scores 50+
- Scores 75+
- Scores 100+
- Starts per innings
- Conversion from 10 to 25
- Conversion from 25 to 50
- Conversion from 50 to 100
- Average after reaching 10
- Average after reaching 25
- Percentage of innings facing 20+ balls
- Percentage of innings batting 10+ overs
- Percentage of innings dismissed before scoring rate matters
- Gets in, gets out index
- Goes big index
- All-or-nothing index

## 1.5 Dismissal Analysis

Even without pitch maps, dismissal type can reveal patterns.

- Bowled percentage
- LBW percentage
- Caught percentage
- Caught keeper percentage
- Caught in field percentage
- Caught and bowled percentage
- Stumped percentage
- Run out percentage
- Hit wicket percentage
- Retired hurt percentage
- Dismissal type by bowler
- Dismissal type by phase
- Dismissal type by batting position
- Dismissal type by innings score
- Dismissal type when chasing
- Dismissal type when batting first
- Dismissal type after drinks
- Dismissal type against pace, if tagged
- Dismissal type against spin, if tagged
- Most common wicket-taking bowlers against the batter
- Most common dismissal fielders against the batter
- Balls faced before dismissal type
- Risk of dismissal after a boundary
- Risk of dismissal after three dots
- Risk of dismissal in first over faced
- Risk of dismissal against new bowler
- Risk of dismissal in bowler's first over
- Risk of dismissal after reaching milestone

## 1.6 Innings Construction

Show how a batter builds an innings.

- First 10 balls scoring pattern
- First boundary ball number
- First scoring shot ball number
- Balls to 10
- Balls to 25
- Balls to 50
- Balls to 100
- Dot balls before first boundary
- Dot balls before first single
- Scoring rate by 5-ball blocks
- Scoring rate by 10-ball blocks
- Number of momentum spikes
- Number of scoring lulls
- Longest dot streak
- Longest boundary drought
- Longest run-scoring streak
- Score after 10 balls
- Score after 20 balls
- Score after 30 balls
- Percentage of innings runs scored in final 25 percent of balls faced
- Acceleration after getting set
- Collapse involvement
- Rebuild involvement
- Finishing involvement

## 1.7 Pressure Batting

Pressure can be modelled using match context.

Useful inputs:

- Required run rate
- Balls remaining
- Wickets in hand
- Target
- Team score
- Batter entry point
- Wickets lost recently
- Opposition strength
- Finals or regular season
- Chase or setting target

Metrics:

- Runs under high required run rate
- Strike rate when required rate is above 6
- Strike rate when required rate is above 8
- Strike rate when required rate is above 10
- Average when entering under 3 wickets down
- Average when entering after quick wickets
- Average when entering with team under 20
- Average when entering with team 5 down or worse
- Boundary percentage when required rate climbs
- Dot ball percentage under pressure
- Dismissal rate under pressure
- Chase contribution
- Successful chase average
- Failed chase average
- Not out percentage in successful chases
- Runs in final five overs of successful chases
- Runs when team wins by fewer than 20 runs
- Runs when team wins by fewer than 3 wickets
- Runs in finals
- Runs against top-four teams
- Runs against bottom-four teams
- Pressure-adjusted runs
- Pressure-adjusted strike rate
- Clutch score
- Game state impact score

## 1.8 Batter Entry Point Analysis

This helps define roles properly.

- Average entry over
- Average entry score
- Average entry wickets down
- Average entry required run rate
- Average entry partnership
- Performance when opening
- Performance entering in overs 1 to 5
- Performance entering in overs 6 to 15
- Performance entering after over 15
- Performance entering at 0 or 1 down
- Performance entering at 2 or 3 down
- Performance entering at 4 or more down
- Performance when team is ahead of par
- Performance when team is behind par
- Performance when rebuilding
- Performance when accelerating
- Performance when finishing
- Best role based on historical outputs

## 1.9 Batting Position Analysis

- Runs by position
- Average by position
- Strike rate by position
- Dot percentage by position
- Boundary percentage by position
- Balls faced by position
- Dismissal rate by position
- Team win rate when player bats in each position
- Team run rate when player bats in each position
- Best position by average
- Best position by strike rate
- Best position by impact
- Best position by team result
- Overqualified or underused batters
- Players batting too low
- Players exposed too high
- Opening suitability
- Number 3 suitability
- Middle-order suitability
- Finisher suitability
- Tail-end resistance suitability

## 1.10 Opposition-Specific Batting

- Runs against each team
- Average against each team
- Strike rate against each team
- Dismissal type against each team
- Most successful opposition bowlers against the batter
- Teams the batter dominates
- Teams that keep the batter quiet
- Average against top teams
- Average against lower teams
- Average against teams with strong bowling attacks
- Performance against future opponent
- Performance against opponent at same venue
- Performance against opponent in finals
- Performance against opponent when chasing
- Performance against opponent when setting a target
- Opposition weakness flag
- Opposition danger flag

## 1.11 Venue Batting

- Runs by ground
- Average by ground
- Strike rate by ground
- Boundary percentage by ground
- Dismissal type by ground
- Best venues
- Worst venues
- Home advantage
- Away performance
- Big-ground profile
- Small-ground profile
- Synthetic wicket profile
- Turf wicket profile
- Fast outfield profile
- Slow outfield profile
- Venue-adjusted average
- Venue-adjusted strike rate

## 1.12 Form Analysis

Separate true form from statistical noise.

- Last 3 innings
- Last 5 innings
- Last 10 innings
- Last 3 matches
- Last 5 matches
- Current season
- Previous season
- Career trend
- Rolling average
- Rolling strike rate
- Rolling balls faced
- Rolling contribution to team runs
- Rolling dismissal rate
- Rolling dot ball percentage
- Rolling boundary percentage
- Form against upcoming opponent
- Form at upcoming venue
- Form in current grade
- Hot streak
- Cold streak
- Expected regression
- Overperforming recent average
- Underperforming career baseline
- Comeback innings after duck
- Bounce-back score after poor innings
- Consistency score
- Volatility score

## 1.13 Batter Value Metrics

- Runs above team average
- Strike rate above team average
- Average above grade average
- Strike rate above grade average
- Runs above replacement
- Runs above expected
- Phase-adjusted runs
- Role-adjusted batting score
- Opposition-adjusted batting score
- Venue-adjusted batting score
- Pressure-adjusted batting score
- Win contribution score
- Batting impact per innings
- Batting impact per ball
- Batting efficiency score
- Risk-versus-reward score
- Reliability score
- Match-winning innings count
- Match-saving innings count
- Low-value runs filter
- High-leverage runs
- Runs that mattered score

---

# 2. Player-by-Player Bowling Analysis

## 2.1 Basic Bowling Profile

- Matches
- Innings bowled
- Overs
- Maidens
- Runs conceded
- Wickets
- Best bowling
- Average
- Strike rate
- Economy rate
- Wickets per match
- Overs per match
- Maidens per match
- Five-wicket hauls
- Three-wicket hauls
- Dot balls
- Dot ball percentage
- Boundary balls conceded
- Boundary percentage conceded
- Wides
- No balls
- Extras conceded
- Extras per over
- Runs per over by season
- Wickets by season
- Economy by season
- Strike rate by season

## 2.2 Bowling Control Profile

Wickets can be noisy. Control is usually more repeatable.

- Dot ball percentage
- Scoring shot percentage conceded
- Single percentage conceded
- Boundary percentage conceded
- Six percentage conceded
- Balls per boundary conceded
- Balls per six conceded
- Economy excluding boundaries
- Economy excluding extras
- Percentage of overs under 3 runs
- Percentage of overs under 5 runs
- Percentage of overs over 10 runs
- Maiden over percentage
- Wicket maiden percentage
- Pressure over percentage
- Release-ball percentage
- Boundary after dot sequence conceded
- Dot after boundary response rate
- Over recovery rate after first ball boundary
- Bad over frequency
- Good over frequency
- Control score
- Containment score
- Chaos score

## 2.3 Bowling Phase Analysis

- Overs bowled by phase
- Wickets by phase
- Economy by phase
- Strike rate by phase
- Average by phase
- Dot percentage by phase
- Boundary percentage conceded by phase
- Wides by phase
- No balls by phase
- Maidens by phase
- New-ball effectiveness
- First-change effectiveness
- Middle-over control
- Death-over control
- Death-over wicket rate
- Death-over boundary prevention
- Opening spell impact
- Second spell impact
- Final spell impact
- Best phase
- Worst phase
- Ideal usage phase

## 2.4 Bowler Spell Analysis

This is extremely useful for captains.

- First over economy
- First over wicket rate
- Second over economy
- Third over economy
- Fourth over economy
- Economy by spell length
- Wicket rate by spell length
- Dot percentage by spell over
- Boundary rate by spell over
- Does the bowler improve after settling?
- Does the bowler fade after four overs?
- Best spell length
- Worst spell length
- Impact of being brought back
- Impact when bowling consecutive overs
- Impact when used in short bursts
- Performance after drinks
- Performance immediately after a wicket
- Performance when defending low total
- Performance when defending big total
- Best bowler to break partnerships
- Best bowler to close innings
- Best bowler to bowl after a boundary-heavy over

## 2.5 Wicket-Taking Analysis

- Wickets by dismissal type
- Bowled percentage
- LBW percentage
- Caught percentage
- Caught behind percentage
- Stumped percentage
- Caught and bowled percentage
- Run out involvement while bowling
- Top-order wickets
- Middle-order wickets
- Tail wickets
- Wickets by batting position
- Wickets by phase
- Wickets in first over
- Wickets in first spell
- Wickets after drinks
- Wickets in finals
- Wickets against top teams
- Wickets against lower teams
- Wickets when defending a total
- Wickets when bowling first
- Wickets after batter reaches 20
- Wickets of set batters
- Wickets of new batters
- Percentage of wickets from key batters
- Percentage of wickets from tailenders
- Quality-adjusted wickets
- Partnership-breaking wickets
- High-value wickets
- Low-value wickets
- Wicket impact score

## 2.6 Bowling to New Batters

- Balls to new batter
- Dot percentage to new batter
- Wicket rate in first 6 balls to new batter
- Wicket rate in first 12 balls to new batter
- Economy to new batter
- Boundary rate to new batter
- Best bowlers to new batters
- Worst bowlers to new batters
- Bowler most likely to dismiss a batter before they get set
- Bowler most likely to let new batter rotate strike
- Bowler best used immediately after a wicket

## 2.7 Bowling to Set Batters

- Economy to batters on 20+
- Economy to batters on 30+
- Economy to batters on 50+
- Wicket rate against set batters
- Dot percentage against set batters
- Boundary prevention against set batters
- Bowler most likely to stop a set batter
- Bowler most likely to dismiss a set batter
- Bowler most likely to get targeted by set batters
- Set batter damage conceded
- Set batter containment score

## 2.8 Batter-Type Analysis

If player metadata is available:

- Bowler to right-handers
- Bowler to left-handers
- Bowler to top-order batters
- Bowler to middle-order batters
- Bowler to tailenders
- Bowler to attacking batters
- Bowler to defensive batters
- Bowler to high strike-rate batters
- Bowler to low strike-rate batters
- Bowler to new batters
- Bowler to set batters
- Bowler to keeper-batters
- Bowler to all-rounders
- Bowler to opposition captains
- Best batter type for bowler
- Danger batter type for bowler

## 2.9 Bowling Discipline

At community level this is often decisive.

- Wides per over
- No balls per over
- Extras per over
- Extras percentage of total runs conceded
- Wides under pressure
- Wides at death
- Wides in first over
- No balls in wicket-taking overs
- No balls after boundary
- No balls when bowling to tail
- Extras in close games
- Cost of extras
- Runs conceded after extra ball
- Free-hit damage, if applicable
- Discipline score
- Reliability score
- Captain trust score

## 2.10 Bowler Match Situation Analysis

- Economy when defending under 120
- Economy when defending 120 to 150
- Economy when defending 150+
- Economy when opposition needs under 6 per over
- Economy when opposition needs 6 to 8 per over
- Economy when opposition needs 8+ per over
- Economy when team is ahead
- Economy when team is behind
- Wicket rate when team needs breakthrough
- Wicket rate after a partnership reaches 50
- Wicket rate when opposition is cruising
- Wicket rate during collapse
- Bowler best at creating collapses
- Bowler best at stopping damage
- Bowler best at closing out games
- Bowler most likely to leak pressure
- Bowler most likely to create pressure

## 2.11 Bowler Value Metrics

- Runs saved versus team average
- Runs saved versus grade average
- Economy adjusted by phase
- Wickets adjusted by phase
- Wickets adjusted by batter quality
- Runs saved above replacement
- Bowling impact per over
- Bowling impact per innings
- Pressure wickets
- Low-value wickets
- High-value wickets
- Expected wickets
- Wickets above expected
- Expected economy
- Economy above or below expected
- Role-adjusted bowling rating
- Opposition-adjusted bowling rating
- Venue-adjusted bowling rating
- Death-over value
- New-ball value
- Partnership-breaking value
- Control plus threat score

---

# 3. Fielding and Wicketkeeping Analysis

## 3.1 Fielding Basics

- Catches
- Run outs
- Stumpings
- Catches per match
- Run outs per match
- Fielding dismissals per match
- Keeper dismissals
- Outfield catches
- Infield catches
- Catches by bowler
- Catches by opposition batter
- Catches by phase
- Catches in wins
- Catches in close games
- Catches in finals

## 3.2 Fielder Value

- Dismissal involvement percentage
- Wickets supported by fielder
- Bowler partnership with fielder
- Most common bowler-fielder combinations
- Safe hands score, if dropped catches are tracked
- Catch impact score
- Run out impact score
- Wicketkeeper impact score
- Keeper dismissals per innings
- Stumping rate to spin
- Catch rate to pace
- Keeper involvement in wickets
- Fielding contribution in low-scoring games

## 3.3 Wicketkeeper Analysis

- Catches
- Stumpings
- Byes conceded, if available
- Byes per innings
- Keeper dismissals to pace
- Keeper dismissals to spin
- Keeper impact by bowler
- Keeper involvement percentage
- Keeper dismissals in close games
- Keeper contribution to spin bowling success

---

# 4. Captaincy and Usage Analysis

If captains are known, the platform can analyse leadership and tactical decisions.

- Win rate as captain
- Toss decisions
- Bat-first success as captain
- Bowl-first success as captain
- Team average score as captain
- Team bowling economy as captain
- Bowling change patterns
- Number of bowlers used
- Opening bowler combinations
- Death bowler choices
- Best captain-bowler combinations
- Batting order stability under captain
- Collapse response under captain
- Chasing success under captain
- Defending success under captain
- Finals record as captain
- Close-game record as captain

---

# 5. All-Rounder Analysis

All-rounders should be evaluated across both disciplines.

- Batting average plus bowling average
- Batting strike rate plus bowling economy
- Runs scored plus wickets taken
- Runs contribution plus runs saved
- Match impact score
- Player of the match likelihood
- Contribution balance
- Batting-heavy all-rounder
- Bowling-heavy all-rounder
- True all-rounder
- Utility player
- Selection flexibility score
- Covers top-order batting and overs
- Covers lower-order hitting and death overs
- Overs bowled when scoring runs
- Runs scored when taking wickets
- Games where player contributes with bat and ball
- Games where player fails in both
- Team win rate when player contributes in either discipline
- Team win rate when player contributes in both
- Replacement difficulty
- Role scarcity score

---

# 6. Player Consistency, Reliability and Selection Analysis

## 6.1 Reliability

- Availability percentage
- Matches played out of possible matches
- Consecutive games played
- Missed games
- Performance after breaks
- Performance in back-to-back games
- Performance in finals
- Performance under promotion
- Performance under demotion
- Performance when captain
- Performance when keeping
- Performance when opening bowling
- Consistency index
- Boom-or-bust index
- Floor score
- Ceiling score
- Median contribution
- Match impact distribution

## 6.2 Selection Value

- Team win rate with player
- Team win rate without player
- Team average score with player
- Team average score without player
- Team bowling economy with player
- Team wicket rate with player
- Net run rate with player
- Net run rate without player
- Average margin with player
- Role coverage
- Team balance improvement
- Best XI score
- Squad depth score
- Like-for-like replacement options
- Player similarity search
- Who replaces this player tool

---

# 7. Team-by-Team Batting Analysis

## 7.1 Basic Team Batting

- Matches
- Wins
- Losses
- Win percentage
- Runs
- Wickets lost
- Overs faced
- Runs per over
- Average score
- Median score
- Highest score
- Lowest score
- Average wickets lost
- All out percentage
- Batting first average
- Chasing average
- Home average
- Away average
- Venue average
- Grade average
- Finals average
- Top-order runs
- Middle-order runs
- Lower-order runs
- Tail runs
- Percentage of runs from top 3
- Percentage of runs from top 5
- Percentage of runs from boundaries
- Percentage of runs from extras
- Average balls used
- Batting resource usage

## 7.2 Team Batting Phases

- Runs in first 5 overs
- Runs in first 10 overs
- Wickets lost in first 10 overs
- Middle-over run rate
- Death-over run rate
- Dot percentage by phase
- Boundary percentage by phase
- Wickets lost by phase
- Phase win rate
- Best batting phase
- Worst batting phase
- Comparison to competition average
- First 10 overs aggression
- Middle-over stagnation
- Death-over acceleration
- Collapse phase
- Recovery phase
- Par score by phase

## 7.3 Team Batting Style

- Dot ball percentage
- Boundary percentage
- Single percentage
- Strike rotation rate
- Boundary reliance
- Runs in boundaries
- Runs in singles
- Runs in twos
- Six-hitting reliance
- Batting depth
- Top-order dependency
- Middle-order stability
- Tail-end contribution
- Collapse frequency
- Recovery frequency
- Partnership reliance
- Aggression index
- Risk index
- Batting tempo index
- Anchor dependency
- Finisher dependency

## 7.4 Team Starts

- Average opening partnership
- Median opening partnership
- Opening partnerships over 25
- Opening partnerships over 50
- First wicket lost before 10
- First wicket lost before 25
- First wicket lost before over 5
- Powerplay wickets lost
- Best opening pair
- Worst opening pair
- Number 3 entry pressure
- Top 3 contribution
- Top 3 failure rate
- Score at first wicket
- Score after 5 overs
- Score after 10 overs
- Team win rate after different starts

## 7.5 Team Collapse Analysis

- Losing 3 wickets for under 20
- Losing 4 wickets for under 30
- Losing 5 wickets for under 50
- Collapse frequency
- Collapse overs
- Collapse triggers
- Collapse after drinks
- Collapse after bowling change
- Collapse against specific teams
- Collapse at specific venues
- Collapse while chasing
- Collapse while setting
- Recovery after collapse
- Players involved in recoveries
- Players most often dismissed during collapses
- Opposition bowlers causing collapses

## 7.6 Team Partnerships

- Average partnership by wicket
- Median partnership by wicket
- Best partnership by wicket
- 25+ partnerships
- 50+ partnerships
- 100+ partnerships
- Opening partnership strength
- Middle-order partnership strength
- Tail partnership strength
- Most common successful pairings
- Fastest scoring pairings
- Safest pairings
- Left-right pairing impact, if handedness is tagged
- Pair compatibility score
- Running between wickets proxy using singles and twos
- Boundary partnership profile
- Rebuild partnership profile
- Finishing partnership profile

## 7.7 Chasing Analysis

- Chasing win percentage
- Average chase target
- Highest successful chase
- Failed chase average
- Successful chase average
- Required rate after 10 overs
- Wickets in hand after 10 overs
- Chase success by target band
- Chase success under 120
- Chase success 120 to 150
- Chase success 150+
- Chase success needing 6+ per over
- Chase success needing 8+ per over
- Chase success with early wicket
- Chase success with top-order platform
- Choking frequency
- Finishing strength
- Not-out finishers
- Boundary rate in final overs
- Dot percentage in final overs
- Players most involved in successful chases

## 7.8 Setting Target Analysis

- Bat-first win percentage
- Average first innings score
- Defendable score by venue
- Defendable score by opponent
- Score band win rate
- Win rate scoring under 120
- Win rate scoring 120 to 149
- Win rate scoring 150 to 179
- Win rate scoring 180+
- Average death-over runs batting first
- Last 5 overs acceleration
- All out before full overs
- Underused balls
- Score after 10 overs and final score relationship
- Par score projection
- Target quality index

---

# 8. Team-by-Team Bowling Analysis

## 8.1 Basic Team Bowling

- Wickets taken
- Runs conceded
- Overs bowled
- Economy rate
- Strike rate
- Average
- Maidens
- Dot balls
- Dot ball percentage
- Boundary percentage conceded
- Extras conceded
- Wides
- No balls
- All-outs achieved
- Opposition average score
- Opposition median score
- Bowling first economy
- Bowling second economy
- Home economy
- Away economy
- Venue economy
- Finals economy

## 8.2 Team Bowling Phases

- New-ball wickets
- New-ball economy
- First 10 overs wickets
- First 10 overs economy
- Middle-over control
- Middle-over wicket rate
- Death-over economy
- Death-over wickets
- Dot percentage by phase
- Boundary percentage by phase
- Extras by phase
- Best bowling phase
- Worst bowling phase
- Team pressure phase
- Team leakage phase
- Best phase bowler
- Worst phase bowler
- Phase depth

## 8.3 Bowling Attack Structure

- Overs by bowler
- Overs by pace, if tagged
- Overs by spin, if tagged
- Wickets by pace
- Wickets by spin
- Economy by pace
- Economy by spin
- New-ball pair performance
- First-change performance
- Death bowling options
- Bowler workload
- Bowler overuse
- Bowler underuse
- Attack balance
- Attack predictability
- Bowling variety
- Left-arm or right-arm split, if tagged
- Spin usage at venue
- Seam usage at venue

## 8.4 Team Wicket-Taking

- Wickets in clusters
- Wickets after drinks
- Wickets after bowling change
- Wickets in first over of spell
- Wickets against top 3
- Wickets against middle order
- Wickets against tail
- Partnership-breaking wickets
- Average opposition partnership
- Average opening stand conceded
- Opposition 50+ partnerships conceded
- Opposition 100+ partnerships conceded
- Wicket droughts
- Longest wicketless phase
- Wicket probability by over
- Best wicket-taking over ranges
- Best breakthrough bowlers

## 8.5 Team Discipline

- Extras per innings
- Extras per over
- Wides per innings
- No balls per innings
- Extras as percentage of opposition score
- Cost of extra balls
- Extras in close losses
- Wides at death
- No balls at key moments
- Bowling discipline trend
- Most disciplined bowlers
- Least disciplined bowlers
- Discipline-adjusted economy
- Games where extras heavily affected the result

## 8.6 Defending Totals

- Win rate defending
- Average defended target
- Lowest defended target
- Failed defence average
- Defence by score band
- Defence by venue
- Defence by opponent
- Defence after strong start
- Defence after poor start
- Wickets needed to win at each venue
- Dot balls needed to win
- Death-over defence success
- Best defenders
- Best low-total bowlers
- Bowlers who leak in close finishes

---

# 9. Team Fielding Analysis

- Catches taken
- Run outs
- Stumpings
- Catches per innings
- Dismissals by fielders
- Keeper dismissals
- Catches by phase
- Catches in wins
- Catches in losses
- Fielding impact in close games
- Most involved fielders
- Most common catcher-bowler combinations
- Run out specialists
- Keeper value to spin
- Keeper value to pace
- Fielding dismissals as percentage of wickets
- Caught percentage of wickets
- Bowled and LBW percentage
- Dropped catches, if manually added
- Dropped catch cost, if manually added
- Missed chance cost, if manually added

---

# 10. Player-vs-Player Analysis

## 10.1 Batter versus Bowler

For every batter-bowler pairing:

- Balls faced
- Runs scored
- Dismissals
- Average
- Strike rate
- Dot ball percentage
- Boundary percentage
- Singles percentage
- Balls per boundary
- Balls per dismissal
- Wicket type
- Phase split
- Venue split
- Season split
- Batting first split
- Chasing split
- Pressure split
- First 6 balls of matchup
- Last 6 balls of matchup
- Who has the edge?
- Matchup confidence level based on sample size
- Batter dominance score
- Bowler dominance score
- Risk score
- Recommended plan

## 10.2 Bowler versus Batter

- Bowlers who have dismissed this batter most
- Bowlers who keep this batter quiet
- Bowlers this batter attacks
- Bowlers this batter rotates easily
- Bowlers this batter cannot get away
- Bowlers this batter survives but does not score against
- Bowlers this batter scores quickly against without getting out
- Bowlers with false dominance due to small sample size
- Bowlers who should be saved for this batter
- Bowlers who should avoid this batter
- Best first-over matchup to this batter
- Best death-over matchup to this batter
- Best partnership-breaking matchup

## 10.3 Batter versus Bowling Type

With bowler tags:

- Batter versus pace
- Batter versus spin
- Batter versus medium pace
- Batter versus left-arm pace
- Batter versus right-arm pace
- Batter versus off spin
- Batter versus leg spin
- Batter versus left-arm orthodox
- Batter versus left-arm wrist spin
- Batter dismissal rate by bowling type
- Batter strike rate by bowling type
- Batter dot percentage by bowling type
- Batter boundary percentage by bowling type
- Best bowling type to use against batter
- Worst bowling type to use against batter

## 10.4 Bowler versus Batter Type

With batter tags:

- Bowler to right-handers
- Bowler to left-handers
- Bowler to aggressive batters
- Bowler to anchors
- Bowler to tailenders
- Bowler to openers
- Bowler to finishers
- Bowler to juniors
- Bowler to senior batters
- Bowler to opposition captain
- Bowler to keeper-batter
- Best batter type for bowler
- Danger batter type for bowler

---

# 11. Same-Team Player Pairings

## 11.1 Batting Pairs

- Partnership runs
- Partnership balls
- Partnership average
- Partnership strike rate
- Dot percentage together
- Boundary percentage together
- Running rate using singles and twos
- Run out frequency
- Left-right impact, if tagged
- Best opening pair
- Best rebuild pair
- Best finishing pair
- Fastest scoring pair
- Safest pair
- Worst pair
- Pairing that improves both players
- Pairing where one player gets stuck
- Pairing where strike is poorly distributed
- Pairing under pressure

## 11.2 Bowling Pairs

- New-ball pair wickets
- New-ball pair economy
- Bowling pair overs together
- Economy during combined spell
- Wickets during combined spell
- Pressure created by one bowler, wicket taken by another
- Dot-ball squeeze pair
- Strike pair
- Control pair
- Death pair
- Spin-twin pair
- Pace-spin combination
- Bowler who benefits from pressure created by another
- Best combination after drinks
- Best combination after a partnership reaches 50

---

# 12. Team-vs-Team Analysis

## 12.1 Head-to-Head Basics

- Matches played
- Wins
- Losses
- Win percentage
- Home wins
- Away wins
- Finals record
- Average score for
- Average score against
- Highest score
- Lowest score
- Biggest win
- Biggest loss
- Most common margin range
- Last 5 meetings
- Last 10 meetings
- Current streak
- Venue-specific head-to-head
- Grade-specific head-to-head
- Season-by-season trend

## 12.2 Head-to-Head Batting

- Average score against opponent
- Average wickets lost against opponent
- Run rate by phase
- Wickets lost by phase
- Top scorers against opponent
- Best averages against opponent
- Best strike rates against opponent
- Most ducks against opponent
- Batters who struggle against opponent
- Batters who dominate opponent
- Opening partnership against opponent
- Middle-order performance against opponent
- Death-over batting against opponent
- Collapse frequency against opponent
- Successful chases against opponent
- Failed chases against opponent
- Best target set against opponent

## 12.3 Head-to-Head Bowling

- Average score conceded
- Economy against opponent
- Wickets per innings against opponent
- Best bowlers against opponent
- Bowlers with best economy against opponent
- Bowlers with best strike rate against opponent
- Bowlers opponent attacks
- Bowlers opponent struggles to score against
- New-ball wickets against opponent
- Middle-over wickets against opponent
- Death-over economy against opponent
- Opposition top-order wickets
- Opposition collapse triggers
- Best bowling plans historically

## 12.4 Team Style Comparison

- Team A scoring rate versus Team B scoring rate
- Team A bowling economy versus Team B bowling economy
- Team A dot ball percentage versus Team B
- Team A boundary percentage versus Team B
- Team A extras conceded versus Team B
- Team A top-order dependency versus Team B
- Team A bowling depth versus Team B
- Team A chase success versus Team B defend success
- Team A home strength versus Team B away weakness
- Team A finals performance versus Team B finals performance
- Team A pressure score versus Team B pressure score
- Team A consistency versus Team B volatility

## 12.5 Tactical Head-to-Head Questions

- What score usually wins this fixture?
- Does this opponent chase well?
- Should we bat first against them?
- Where do they usually lose wickets?
- Which batter must we remove early?
- Which bowler do we need to see off?
- Which bowler can we target?
- Which phase decides this matchup?
- Do they rely too much on one batter?
- Do they have a weak fifth bowler?
- Do they collapse after early wickets?
- Do they struggle to finish innings?
- Do they leak extras?
- Do they have a dangerous tail?
- Do they defend small totals?
- Do they panic in chases?
- Are they better at home than away?
- What is the most likely match script?

---

# 13. Opposition Player Reports

## 13.1 Batter Scouting Card

Each opposition batter should have a card containing:

- Name
- Team
- Batting role
- Likely batting position
- Recent form
- Career record
- Season record
- Record against us
- Record at venue
- Record in grade
- Strike rate profile
- Dot ball profile
- Boundary profile
- Dismissal profile
- Phase profile
- Starts and conversion
- Pressure profile
- Chase profile
- Favourite matchup
- Weak matchup
- Bowlers who have dismissed them
- Bowlers who contain them
- Recommended bowling plan
- Risk level
- Key note

Example output:

> Danger player. Starts slowly but accelerates hard after 25 balls. Keep him under 15 from his first 20 balls and bring on spin early. Most dismissals are caught between 10 and 30. Avoid feeding him at the death.

## 13.2 Bowler Scouting Card

Each opposition bowler should have a card containing:

- Name
- Team
- Bowling role
- Likely opening, first change or death role
- Overs usually bowled
- Recent form
- Career record
- Season record
- Record against us
- Record at venue
- Economy by phase
- Wickets by phase
- Dot ball percentage
- Boundary percentage conceded
- Extras profile
- Spell profile
- First over profile
- Death over profile
- Batters who score well against them
- Batters who struggle against them
- Recommended batting plan
- Risk level
- Key note

Example output:

> High-control bowler. Does not take huge wicket bags but creates pressure. Low boundary rate in overs 1 to 10. Best plan is rotation, not attack. Target their change bowlers instead.

---

# 14. Team Opposition Reports

A proper pre-game opposition report should include the following sections.

## 14.1 Team Snapshot

- Ladder position
- Win-loss record
- Recent form
- Average score
- Average score conceded
- Net run rate
- Bat-first win rate
- Chase win rate
- Home-away split
- Venue record
- Key players
- Weak links
- Likely XI
- Likely batting order
- Likely bowling order

## 14.2 How They Win

- Top-order runs
- Early wickets
- Spin control
- Death hitting
- Low extras
- One superstar batter
- Balanced bowling
- Strong keeper and fielders
- Big partnerships
- Opposition collapses
- Defending par totals
- Chasing calmly

## 14.3 How They Lose

- Early wickets
- Middle-over stagnation
- Death-over leakage
- High extras
- Overreliance on top 3
- Weak fifth bowler
- Tail starts too early
- Poor chasing under pressure
- Poor fielding involvement
- No wicket-taking threat after opening bowlers

## 14.4 Key Opposition Vulnerabilities

- Batter X struggles early
- Batter Y gets bogged down by spin
- Batter Z has high dot percentage
- Bowler A leaks at death
- Bowler B bowls wides under pressure
- Team collapses after second wicket
- Team fails to accelerate after over 30
- Team struggles chasing more than 150
- Team allows big opening stands
- Team gives too many extras

## 14.5 Suggested Game Plan

- Bat-first or bowl-first recommendation
- Par score
- Minimum competitive score
- Bowlers to use in first 10 overs
- Bowlers to save for key batters
- Batters to protect or promote
- Bowlers to target
- Overs to attack
- Overs to consolidate
- Key matchup plan
- First 10 overs plan
- Middle overs plan
- Death overs plan
- Fielding focus
- Discipline focus
- One critical warning

---

# 15. Advanced Community Cricket Models

## 15.1 Win Probability Model

Use these inputs:

- Target
- Current score
- Wickets down
- Balls remaining
- Required run rate
- Venue
- Grade
- Team strength
- Batter quality
- Bowler quality
- Historical outcomes from similar positions

Outputs:

- Win probability by ball
- Biggest momentum swing
- Turning point
- Over where the match changed
- Win probability added by player
- Batting win probability added
- Bowling win probability added
- Fielding win probability added
- Pressure moments

## 15.2 Pressure Index

Use these inputs:

- Required run rate
- Balls remaining
- Wickets in hand
- Recent wickets
- Recent dot balls
- Batter newness
- Finals weighting
- Target size

Outputs:

- Pressure score per ball
- Batter performance under pressure
- Bowler performance under pressure
- Team pressure tolerance
- Team pressure collapse risk
- Pressure-adjusted runs
- Pressure-adjusted wickets
- Clutch ranking

## 15.3 Player Impact Score

For batters:

- Runs scored
- Strike rate
- Match context
- Team score
- Phase
- Pressure
- Opposition quality
- Venue par score
- Dismissal timing

For bowlers:

- Wickets
- Economy
- Dot balls
- Phase
- Batter quality
- Match context
- Runs saved
- Partnership broken
- Pressure created

Outputs:

- Match impact
- Season impact
- Career impact
- Impact per innings
- Impact per ball
- Best impact performances
- Quietly valuable performances
- Empty stats detector

## 15.4 Role-Adjusted Ratings

Separate players into roles:

- Opener
- Number 3
- Anchor
- Middle-order accumulator
- Finisher
- Tail-end hitter
- New-ball bowler
- First-change bowler
- Middle-over controller
- Strike bowler
- Death bowler
- Part-time bowler
- Keeper
- All-rounder

Then compare players only to similar roles.

Metrics:

- Role average
- Role strike rate
- Role economy
- Role wicket rate
- Role consistency
- Role impact
- Role scarcity
- Role-adjusted ranking

## 15.5 Expected Runs Model

Estimate what a batter should score based on:

- Batting position
- Over of entry
- Wickets down
- Balls remaining
- Venue
- Opposition
- Grade
- Historical player level
- Match format

Outputs:

- Runs above expected
- Strike rate above expected
- Underperformance
- Overperformance
- Best pressure innings
- Best low-score innings
- Worst high-score innings
- Role-adjusted innings value

## 15.6 Expected Wickets Model

Estimate how many wickets a bowler should take based on:

- Overs bowled
- Phase
- Batter quality
- Team score pressure
- Venue
- Match format
- Bowling role
- Opposition aggression

Outputs:

- Wickets above expected
- Economy above expected
- Wicket luck
- Under-rewarded bowlers
- Over-rewarded bowlers
- Bowlers creating chances without wickets
- Bowlers taking tail wickets only
- Bowlers taking high-value wickets

## 15.7 Replacement Value

- Best replacement batter
- Best replacement bowler
- Best like-for-like player
- Best XI without player
- Team impact if player unavailable
- Batting depth lost
- Bowling overs lost
- Fielding lost
- Captaincy lost
- Role scarcity
- Squad fragility

## 15.8 Similar Player Search

- Similar batting style
- Similar bowling style
- Similar phase profile
- Similar role
- Similar scoring tempo
- Similar dismissal pattern
- Similar bowling control
- Similar wicket-taking profile
- Similar all-round value
- Find another player like X

## 15.9 Team Strength Model

- Batting rating
- Bowling rating
- Fielding rating
- Depth rating
- Recent form
- Venue adjustment
- Opposition adjustment
- Predicted score
- Predicted wickets
- Win probability
- Key dependency
- Upset chance
- Fragility rating

---

# 16. High-Impact Product Features

## 16.1 How to Beat This Team Button

Automatically generate:

- Their key strength
- Their key weakness
- Par score
- Best toss decision
- Batter to dismiss early
- Bowler to see off
- Bowler to target
- Overs to attack
- Overs to survive
- Matchups to force
- Matchups to avoid
- One-sentence game plan

## 16.2 Danger Player Alerts

Flag players who are:

- In hot form
- Historically strong against the user's team
- Strong at the venue
- Strong in finals
- Strong while chasing
- Strong against the user's bowling type
- Due to face a weak matchup
- Better than their average suggests
- Returning from absence with strong history

## 16.3 False Threat Alerts

Flag players who look dangerous but may not be:

- Runs mostly against lower teams
- Runs mostly at one venue
- Runs at low strike rate
- Wickets mostly tailenders
- Wickets with poor economy
- Big season caused by one outlier game
- Good average inflated by not outs
- Reputation stronger than recent output

## 16.4 Target This Player Alerts

For opposition batters:

- High dot ball percentage
- Low strike rotation
- Poor against user's best bowler
- Poor starter
- Poor chaser
- High dismissal rate under pressure
- Weak at venue
- Weak against phase

For opposition bowlers:

- High wide percentage
- Poor death economy
- Boundary prone
- Struggles after first spell
- Poor against left-handers
- Poor against set batters
- Low wicket threat
- Can be milked safely

## 16.5 Matchup Advantage Matrix

Rows are the user's batters. Columns are opposition bowlers.

Each cell should show:

- Attack
- Neutral
- Danger
- Sample size confidence
- Expected strike rate
- Expected dismissal risk
- Historical record
- Tactical note

The reverse matrix should show:

- User's bowlers versus opposition batters

## 16.6 Captain's Cheat Sheet

One-page pre-game output:

- Opposition likely top 7
- Opposition likely bowlers
- Key matchups
- Who bowls to whom
- Who bats best against whom
- Death overs plan
- Bowlers to target
- Safe overs
- Danger overs
- Par score
- Toss recommendation
- First 10 overs target
- Do not bowl X to Y
- Save X for Y
- Attack Y before over 10

## 16.7 Live Match Assistant

If live scoring is available:

- Win probability
- Current par score
- Required phase score
- Batter phase warning
- Bowler matchup warning
- Partnership danger alert
- Collapse risk alert
- Death overs resource warning
- Suggested bowler next over
- Suggested batting tempo
- Historical warning notes
- Matchup reminders

## 16.8 What Changed the Game

Post-match automatic analysis:

- Biggest batting contribution
- Biggest bowling contribution
- Biggest turning point
- Best partnership
- Most damaging over
- Best over
- Worst over
- Cost of extras
- Cost of dropped chances, if tracked
- Win probability swing
- Phase won or lost
- Player impact ranking
- Tactical lesson

## 16.9 Community CricViz-Style Player Card

Each player gets:

- Role
- Career profile
- Season profile
- Recent form
- Best phase
- Weak phase
- Best matchup
- Weak matchup
- Pressure score
- Consistency
- Impact
- Similar players
- One-line scouting note

Example:

> Top-order accumulator. Low dismissal rate once set, but slow starter with a high dot percentage in first 12 balls. Best attacked early with tight new-ball bowling.

## 16.10 Opposition Memory

Club-specific historical intelligence:

- What happened last time we played them?
- Who hurt us?
- Who did we dismiss cheaply?
- Which bowler caused us issues?
- Which of our batters scored freely?
- What score was enough?
- Did we collapse?
- Did we leak extras?
- What should we do differently?

---

# 17. Suggested User-Facing Dashboards

## 17.1 Player Dashboard

Tabs:

1. Overview
2. Batting
3. Bowling
4. Fielding
5. Form
6. Matchups
7. Venues
8. Opposition
9. Pressure
10. Impact

## 17.2 Team Dashboard

Tabs:

1. Overview
2. Batting profile
3. Bowling profile
4. Fielding
5. Phases
6. Partnerships
7. Chasing
8. Defending
9. Venues
10. Opposition

## 17.3 Opposition Dashboard

Tabs:

1. Team snapshot
2. How they win
3. How they lose
4. Key batters
5. Key bowlers
6. Matchups
7. Venue history
8. Tactical plan
9. Predicted XI
10. Captain's cheat sheet

## 17.4 Match Preview

Sections:

1. Team comparison
2. Recent form
3. Venue trends
4. Key players
5. Key matchups
6. Par score
7. Phase battle
8. Tactical recommendation
9. Predicted result
10. Confidence level

---

# 18. Implementation Priorities

## Tier 1: Immediate Value

Build these first.

- Player form
- Team form
- Head-to-head
- Batting by position
- Bowling by phase
- Batting by phase
- Player versus player matchups
- Team versus team history
- Venue stats
- Chasing and defending records
- Partnerships
- Dot ball percentage
- Boundary percentage
- Extras analysis
- Opposition key player reports

## Tier 2: Differentiation

Build after the core reporting is stable.

- Role-adjusted player ratings
- Batter scouting cards
- Bowler scouting cards
- Captain's cheat sheet
- Matchup advantage matrix
- Collapse analysis
- Pressure batting
- Pressure bowling
- Phase win-loss analysis
- High-value wickets
- Runs above expected
- Wickets above expected
- Target score model
- Par score by venue and grade

## Tier 3: Premium or Advanced Features

These create the strongest competitive moat.

- Win probability
- Live tactical assistant
- Automated opposition reports
- Similar player search
- Replacement value
- Player impact score
- Clutch score
- False threat detection
- Weak link detection
- How to beat them engine
- AI-generated match plans
- AI-generated post-match review
- Predictive score simulator
- Best XI optimiser
- Bowling plan optimiser
- Batting order optimiser

---

# 19. Suggested Technical Implementation Notes for Claude Code

## 19.1 Suggested Data Entities

Core entities:

- Player
- Team
- Club
- Match
- Innings
- BallEvent
- BattingInnings
- BowlingSpell
- Partnership
- Venue
- Season
- Grade
- Competition
- Dismissal
- PlayerTag
- VenueTag
- TeamMatchSummary
- PlayerMatchSummary
- MatchupSummary

## 19.2 Suggested Derived Tables

To keep dashboards fast, precompute:

- player_batting_summary
- player_bowling_summary
- player_fielding_summary
- player_form_summary
- player_phase_summary
- player_venue_summary
- player_opposition_summary
- batter_bowler_matchups
- team_batting_summary
- team_bowling_summary
- team_phase_summary
- team_chasing_summary
- team_defending_summary
- team_venue_summary
- team_opposition_summary
- partnership_summary
- bowling_pair_summary
- batting_pair_summary
- opposition_report_summary
- match_preview_summary

## 19.3 Suggested API Routes

Example routes:

- GET /players/:id/overview
- GET /players/:id/batting
- GET /players/:id/bowling
- GET /players/:id/fielding
- GET /players/:id/form
- GET /players/:id/matchups
- GET /players/:id/venues
- GET /players/:id/opposition
- GET /teams/:id/overview
- GET /teams/:id/batting
- GET /teams/:id/bowling
- GET /teams/:id/phases
- GET /teams/:id/chasing
- GET /teams/:id/defending
- GET /teams/:id/venues
- GET /teams/:id/opposition
- GET /matches/:id/preview
- GET /matches/:id/review
- GET /opposition/:teamId/report
- GET /matchups/batter/:batterId/bowler/:bowlerId
- GET /venues/:id/par-score
- GET /reports/captains-cheat-sheet
- GET /reports/how-to-beat-team

## 19.4 Suggested Front-End Components

- PlayerSummaryCard
- TeamSummaryCard
- FormTrendChart
- PhaseBreakdownChart
- MatchupMatrix
- OppositionScoutingCard
- CaptainCheatSheet
- VenueParScoreCard
- ChaseProfileCard
- DefenceProfileCard
- CollapseTimeline
- PartnershipTable
- BowlerSpellChart
- PlayerImpactCard
- DangerPlayerAlert
- FalseThreatAlert
- TacticalRecommendationCard
- WinProbabilityChart
- MatchTurningPointCard

## 19.5 Suggested Scoring Concepts

These can be implemented progressively.

### Confidence Score

Every insight should include confidence based on sample size.

Example:

- Low confidence: fewer than 20 balls or fewer than 3 innings
- Medium confidence: 20 to 60 balls or 3 to 8 innings
- High confidence: 60+ balls or 8+ innings

### Context Weighting

Give more weight to:

- Recent matches
- Same grade
- Same format
- Same venue
- Same opposition
- Finals
- Similar match state

Give less weight to:

- Very old matches
- Different grades
- Tiny samples
- Lower-quality opposition
- Heavily rain-affected matches

### Insight Guardrails

Do not overstate insights based on tiny samples.

Use phrasing like:

- Small sample, but...
- Historically...
- In recent matches...
- Against this opponent...
- At this venue...
- The trend suggests...
- The data is limited, but this is worth noting...

## 19.6 Example Generated Insight Templates

### Batter Insight

`{playerName} has scored {runs} runs at {strikeRate} against {oppositionName}, but starts slowly with a {dotPercentage}% dot ball rate in their first {balls} balls. The best plan is to keep them under pressure early and avoid giving them boundary balls once set.`

### Bowler Insight

`{playerName} is most effective in overs {phase}, where they average {average} with an economy of {economy}. They are less effective at the death, conceding {deathEconomy} runs per over.`

### Team Insight

`{teamName} rely heavily on their top order, with {topThreePercentage}% of runs coming from the top three. Early wickets dramatically reduce their scoring rate.`

### Matchup Insight

`{batterName} has scored {runs} from {balls} balls against {bowlerName}, with {dismissals} dismissals. This matchup favours {advantagePlayer}, but confidence is {confidenceLevel} due to sample size.`

### Venue Insight

`At {venueName}, the average first innings score in this grade is {averageScore}. Teams scoring above {parScore} win {winPercentage}% of matches.`

### Captain's Note

`The key period is overs {startOver} to {endOver}. {oppositionName} lose wickets regularly in this phase, while {teamName} have strong control options available.`

---

# 20. Product Outcome

The end product should help community cricket clubs move from descriptive stats to actionable analysis.

Instead of showing:

- Player A averages 31.
- Bowler B has taken 18 wickets.
- Team C has won 5 from 8.

It should show:

- Player A starts slowly, accelerates after 25 balls, and is most vulnerable to spin before reaching 20.
- Bowler B takes wickets but leaks runs late in spells, so attack their fourth over.
- Team C relies on its top three. If they lose two wickets before 40, their win rate drops heavily.
- The venue usually requires 155+ batting first.
- The best bowling plan is to open with X and save Y for their number 4.
- The biggest danger player is Z, but only if they survive the first 15 balls.
- The weak link is their fifth bowler, who concedes heavily in overs 25 to 35.
- Your best chance is to bat first, protect wickets early, then attack their change bowlers.

That is the leap from a scorecard product to a cricket intelligence product.

---

# 21. Source Notes

These sources informed the original research framing:

- CricViz performance analysis overview: https://cricviz.com/performance-analysis/
- Cricsheet CSV ball-by-ball format reference: https://cricsheet.org/format/csv_original/
- CricketData ball-by-ball analysis examples: https://www.r-bloggers.com/2025/12/how-to-analyze-ball-by-ball-cricket-data-in-r-cricketdata/
- Journal of Sports Analytics research on pressure in cricket chases: https://journals.sagepub.com/doi/10.3233/JSA-240792
- Professional and franchise cricket analytics discussion: https://www.ijfmr.com/papers/2026/1/67546.pdf

