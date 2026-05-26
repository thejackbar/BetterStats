import { useParams, useSearchParams, useNavigate, Link } from 'react-router-dom'
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useClub } from '../hooks/useClub'
import { useClubData } from '../hooks/useClubData'
import { useAuth } from '../contexts/AuthContext'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import { Label, Card, Btn, PageHeader, PbSpinner } from '../lib/presskit'

// ─── Static config ────────────────────────────────────────────────────────────

const TARGETS = [
  { key: 'player_career',    label: 'Player career',     shape: 'aggregate', dim: 'player' },
  { key: 'player_season',    label: 'Player season',     shape: 'aggregate', dim: 'player_season' },
  { key: 'player_grade',     label: 'Player by grade',   shape: 'aggregate', dim: 'player_grade' },
  { key: 'family_career',    label: 'Family career',     shape: 'aggregate', dim: 'family' },
  { key: 'family_season',    label: 'Family by season',  shape: 'aggregate', dim: 'family_season' },
  { key: 'family_grade',     label: 'Family by grade',   shape: 'aggregate', dim: 'family_grade' },
  { key: 'innings_list',     label: 'Innings list',      shape: 'list',      dim: 'innings' },
  { key: 'spell_list',       label: 'Bowling spells',    shape: 'list',      dim: 'spell' },
  { key: 'match_list',       label: 'Match list',        shape: 'list',      dim: 'match' },
  { key: 'partnership_list', label: 'Partnerships',      shape: 'list',      dim: 'partnership' },
]

// Display labels for every metric. `label` is the full name shown in the
// query builder (pickers, sort menus, filter chips). `short` is an optional
// abbreviation used in tight spots like results-table column headers.
const METRIC_LABELS = {
  matches: { label: 'Matches', short: 'M', decimal: false },
  seasons_played: { label: 'Seasons Played', short: 'Seasons', decimal: false },
  batting_innings: { label: 'Batting Innings', short: 'Inns', decimal: false },
  runs: { label: 'Runs', short: 'Runs', decimal: false },
  not_outs: { label: 'Not Outs', short: 'NO', decimal: false },
  balls_faced: { label: 'Balls Faced', short: 'Balls', decimal: false },
  batting_average: { label: 'Batting Average', short: 'Avg', decimal: true },
  batting_strike_rate: { label: 'Batting Strike Rate', short: 'SR', decimal: true },
  high_score: { label: 'High Score', short: 'HS', decimal: false },
  fifties: { label: 'Fifties', short: '50s', decimal: false },
  hundreds: { label: 'Hundreds', short: '100s', decimal: false },
  ducks: { label: 'Ducks', short: 'Ducks', decimal: false },
  fours: { label: 'Fours', short: '4s', decimal: false },
  sixes: { label: 'Sixes', short: '6s', decimal: false },
  bowling_innings: { label: 'Bowling Spells', short: 'Spells', decimal: false },
  wickets: { label: 'Wickets', short: 'Wkts', decimal: false },
  overs: { label: 'Overs', short: 'Overs', decimal: false },
  runs_conceded: { label: 'Runs Conceded', short: 'R Conc', decimal: false },
  bowling_average: { label: 'Bowling Average', short: 'Bowl Avg', decimal: true },
  bowling_economy: { label: 'Economy Rate', short: 'Econ', decimal: true },
  bowling_strike_rate: { label: 'Bowling Strike Rate', short: 'Bowl SR', decimal: true },
  five_wicket_innings: { label: 'Five-Wicket Innings', short: '5w', decimal: false },
  maidens: { label: 'Maidens', short: 'Mdns', decimal: false },
  best_bowling_wickets: { label: 'Best Bowling (Wickets)', short: 'BBW', decimal: false },
  catches: { label: 'Catches', short: 'Ct', decimal: false },
  run_outs: { label: 'Run Outs', short: 'RO', decimal: false },
  stumpings: { label: 'Stumpings', short: 'St', decimal: false },
  balls: { label: 'Balls Faced', short: 'Balls', decimal: false },
  strike_rate: { label: 'Strike Rate', short: 'SR', decimal: true },
  batting_position: { label: 'Batting Position', short: 'Pos', decimal: false },
  innings_number: { label: 'Innings Number', short: 'Inn#', decimal: false },
  economy: { label: 'Economy Rate', short: 'Econ', decimal: true },
  wides: { label: 'Wides', short: 'Wd', decimal: false },
  no_balls: { label: 'No-Balls', short: 'NB', decimal: false },
  team_runs: { label: 'Team Runs (For)', short: 'For', decimal: false },
  team_wickets: { label: 'Team Wickets (For)', short: 'Wkts For', decimal: false },
  opp_runs: { label: 'Opposition Runs', short: 'Against', decimal: false },
  opp_wickets: { label: 'Opposition Wickets', short: 'Wkts Agst', decimal: false },
  margin_runs: { label: 'Win/Loss Margin (Runs)', short: 'Margin', decimal: false },
  wicket_number: { label: 'Wicket Number', short: 'Wkt #', decimal: false },
  batter1_runs: { label: 'Batter 1 Runs', short: 'B1 R', decimal: false },
  batter2_runs: { label: 'Batter 2 Runs', short: 'B2 R', decimal: false },
  member_count: { label: 'Members', short: 'Members', decimal: false },
}

const OPERATORS = [
  { key: 'gte', label: 'at least' },
  { key: 'gt',  label: 'more than' },
  { key: 'eq',  label: 'exactly' },
  { key: 'lte', label: 'at most' },
  { key: 'lt',  label: 'less than' },
  { key: 'ne',  label: 'not equal' },
]

const PRESET_GROUPS = [
  {
    key: 'popular', label: 'Popular', defaultOpen: true,
    items: [
      { type: 'preset', label: 'Top run aggregates',          target: 'player_career',    sortBy: 'runs',                sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Top run scores',              target: 'innings_list',     sortBy: 'runs',                sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Top batting averages',        target: 'player_career',    sortBy: 'batting_average',     sortDir: 'desc', filters: [{ field: 'batting_innings', op: 'gte', value: '20' }], context: {} },
      { type: 'preset', label: 'Top batting strike rates',    target: 'player_career',    sortBy: 'batting_strike_rate', sortDir: 'desc', filters: [{ field: 'balls_faced', op: 'gte', value: '500' }], context: {} },
      { type: 'preset', label: 'Most runs in a season',       target: 'player_season',    sortBy: 'runs',                sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Top partnerships',            target: 'partnership_list', sortBy: 'runs',                sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Top wicket takers',           target: 'player_career',    sortBy: 'wickets',             sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Best bowling in an innings',  target: 'spell_list',       sortBy: 'wickets',             sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Top bowling averages',        target: 'player_career',    sortBy: 'bowling_average',     sortDir: 'asc',  filters: [{ field: 'wickets', op: 'gte', value: '20' }], context: {} },
      { type: 'preset', label: 'Most wickets in a season',    target: 'player_season',    sortBy: 'wickets',             sortDir: 'desc', filters: [], context: {} },
      { type: 'derived', key: 'catches_stumpings',            label: 'Top catches & stumpings',  description: 'Combined catches + stumpings per player.' },
      { type: 'preset', label: 'Most matches played',         target: 'player_career',    sortBy: 'matches',             sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Top all-rounders',            target: 'player_career',    sortBy: 'runs',                sortDir: 'desc', filters: [{ field: 'runs', op: 'gte', value: '500' }, { field: 'wickets', op: 'gte', value: '50' }], context: {} },
    ],
  },
  {
    key: 'season', label: 'Season Honours', defaultOpen: false,
    items: [
      { type: 'preset', label: 'Top run aggregates by season',     target: 'player_season', sortBy: 'runs',            sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Top batting averages by season',   target: 'player_season', sortBy: 'batting_average', sortDir: 'desc', filters: [{ field: 'batting_innings', op: 'gte', value: '10' }], context: {} },
      { type: 'preset', label: 'Top wicket aggregates by season',  target: 'player_season', sortBy: 'wickets',         sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Top bowling averages by season',   target: 'player_season', sortBy: 'bowling_average', sortDir: 'asc',  filters: [{ field: 'wickets', op: 'gte', value: '10' }], context: {} },
      { type: 'preset', label: 'Most matches in a season',         target: 'player_season', sortBy: 'matches',         sortDir: 'desc', filters: [], context: {} },
    ],
  },
  {
    key: 'families', label: 'Families', defaultOpen: false,
    items: [
      { type: 'preset', label: 'Most runs by family (career)',      target: 'family_career', sortBy: 'runs',     sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Most wickets by family (career)',   target: 'family_career', sortBy: 'wickets',  sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Most matches by family (career)',   target: 'family_career', sortBy: 'matches',  sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Most catches by family (career)',   target: 'family_career', sortBy: 'catches',  sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Family runs by season',             target: 'family_season', sortBy: 'runs',     sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Family wickets by season',          target: 'family_season', sortBy: 'wickets',  sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Family matches by season',          target: 'family_season', sortBy: 'matches',  sortDir: 'desc', filters: [], context: {} },
    ],
  },
  {
    key: 'batting', label: 'Batting', defaultOpen: false,
    items: [
      // Aggregates
      { type: 'preset', label: 'Top run aggregates',           target: 'player_career', sortBy: 'runs',                sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Top run scores',               target: 'innings_list',  sortBy: 'runs',                sortDir: 'desc', filters: [], context: {} },
      { type: 'derived', key: 'top_scores_by_position',        label: 'Top run scores by batting position', description: 'Best individual score at each position 1-11.' },
      { type: 'preset', label: 'Top batting averages',         target: 'player_career', sortBy: 'batting_average',     sortDir: 'desc', filters: [{ field: 'batting_innings', op: 'gte', value: '20' }], context: {} },
      { type: 'preset', label: 'Top batting average in a season', target: 'player_season', sortBy: 'batting_average',  sortDir: 'desc', filters: [{ field: 'batting_innings', op: 'gte', value: '10' }], context: {} },
      { type: 'preset', label: 'Top batting strike rates',     target: 'player_career', sortBy: 'batting_strike_rate', sortDir: 'desc', filters: [{ field: 'balls_faced', op: 'gte', value: '500' }], context: {} },
      { type: 'derived', key: 'most_runs_in_match',            label: 'Most runs in a match', description: 'Highest combined runs by one batter in a single match.' },
      { type: 'derived', key: 'most_boundaries_in_match',      label: 'Most boundaries in a match', description: 'Most 4s + 6s by one batter in a match.' },
      // Sixes
      { type: 'preset', label: 'Most sixes (career)',          target: 'player_career', sortBy: 'sixes',              sortDir: 'desc', filters: [{ field: 'sixes', op: 'gte', value: '1' }], context: {} },
      { type: 'preset', label: 'Most sixes in an innings',     target: 'innings_list',  sortBy: 'sixes',              sortDir: 'desc', filters: [{ field: 'sixes', op: 'gte', value: '1' }], context: {} },
      { type: 'derived', key: 'most_sixes_in_match',           label: 'Most sixes in a match', description: 'Most sixes by one batter across both innings.' },
      { type: 'preset', label: 'Most sixes in a season',       target: 'player_season', sortBy: 'sixes',              sortDir: 'desc', filters: [], context: {} },
      // Fours
      { type: 'preset', label: 'Most fours (career)',          target: 'player_career', sortBy: 'fours',              sortDir: 'desc', filters: [{ field: 'fours', op: 'gte', value: '1' }], context: {} },
      { type: 'preset', label: 'Most fours in an innings',     target: 'innings_list',  sortBy: 'fours',              sortDir: 'desc', filters: [{ field: 'fours', op: 'gte', value: '1' }], context: {} },
      { type: 'derived', key: 'most_fours_in_match',           label: 'Most fours in a match', description: 'Most fours by one batter across both innings.' },
      { type: 'preset', label: 'Most fours in a season',       target: 'player_season', sortBy: 'fours',              sortDir: 'desc', filters: [], context: {} },
      // Ducks
      { type: 'preset', label: 'Most ducks (career)',          target: 'player_career', sortBy: 'ducks',              sortDir: 'desc', filters: [{ field: 'ducks', op: 'gte', value: '1' }], context: {} },
      { type: 'preset', label: 'Most ducks in a season',       target: 'player_season', sortBy: 'ducks',              sortDir: 'desc', filters: [], context: {} },
      { type: 'derived', key: 'ducks_on_debut',                label: 'Ducks on debut',           description: 'Players whose debut innings was a duck.' },
      { type: 'derived', key: 'consecutive_ducks',             label: 'Most consecutive ducks',    description: 'Longest run of consecutive innings out for 0.' },
      { type: 'derived', key: 'consecutive_no_duck',           label: 'Most consecutive scores without a duck', description: 'Longest streak of innings without a duck.' },
      { type: 'derived', key: 'golden_ducks',                  label: 'Most golden ducks',         description: 'Out for 0 off 0 or 1 ball.' },
      { type: 'derived', key: 'duck_pairs',                    label: 'Duck pairs',                description: 'Ducks in both innings of the same match.' },
      // Scores ranges
      // Most 90s/40s — count per player (the "leaderboard" view)
      { type: 'derived', key: 'most_90s',                      label: 'Most 90s',                  description: 'Count per player of innings scored in the 90s.' },
      { type: 'derived', key: 'most_40s',                      label: 'Most 40s',                  description: 'Count per player of innings scored in the 40s.' },
      // The individual-scores list (preserved under a clearer name)
      { type: 'preset', label: 'Scores in the 90s',            target: 'innings_list',  sortBy: 'runs',                sortDir: 'desc', filters: [{ field: 'runs', op: 'gte', value: '90' }, { field: 'runs', op: 'lt', value: '100' }], context: {} },
      { type: 'preset', label: 'Scores in the 40s',            target: 'innings_list',  sortBy: 'runs',                sortDir: 'desc', filters: [{ field: 'runs', op: 'gte', value: '40' }, { field: 'runs', op: 'lt', value: '50' }], context: {} },
      // Hundreds
      { type: 'preset', label: 'Most hundreds (career)',       target: 'player_career', sortBy: 'hundreds',            sortDir: 'desc', filters: [{ field: 'hundreds', op: 'gte', value: '1' }], context: {} },
      { type: 'preset', label: 'Most hundreds in a season',    target: 'player_season', sortBy: 'hundreds',            sortDir: 'desc', filters: [{ field: 'hundreds', op: 'gte', value: '1' }], context: {} },
      { type: 'derived', key: 'consecutive_hundreds',          label: 'Most consecutive hundreds',  description: 'Longest run of innings scoring 100+.' },
      { type: 'preset', label: 'Centurions',                   target: 'player_career', sortBy: 'hundreds',            sortDir: 'desc', filters: [{ field: 'hundreds', op: 'gte', value: '1' }], context: {} },
      { type: 'derived', key: 'century_each_innings',          label: 'A century in each innings',  description: 'Players who scored 100+ in both innings of a match.' },
      { type: 'derived', key: 'century_and_duck',              label: 'Century and duck in same match', description: 'A 100 and a 0 in the same match.' },
      { type: 'derived', key: 'innings_without_century',       label: 'Most innings without a century', description: 'Players with most innings and no 100.' },
      { type: 'derived', key: 'consecutive_no_century',        label: 'Most consecutive scores without a century', description: 'Longest sub-100 streak.' },
      { type: 'derived', key: 'lowest_century_conversion',     label: 'Lowest century conversions', description: '50→100 conversion rate (5+ scores of 50+).' },
      // Fifties
      { type: 'preset', label: 'Most fifties (career)',        target: 'player_career', sortBy: 'fifties',             sortDir: 'desc', filters: [{ field: 'fifties', op: 'gte', value: '1' }], context: {} },
      { type: 'preset', label: 'Most fifties in a season',     target: 'player_season', sortBy: 'fifties',             sortDir: 'desc', filters: [], context: {} },
      { type: 'derived', key: 'consecutive_fifties',           label: 'Most consecutive fifties',  description: 'Longest streak of innings scoring 50+.' },
      { type: 'derived', key: 'innings_per_fifty',             label: 'Top innings per fifty',     description: 'Lowest innings-per-50 ratio (most frequent 50+ scorer).' },
      { type: 'derived', key: 'top_scores_pct_innings',        label: 'Top run scores as % of innings', description: 'Individual scores as % of club innings total.' },
      // Other
      { type: 'preset', label: 'Top all-rounders',             target: 'player_career', sortBy: 'runs',                sortDir: 'desc', filters: [{ field: 'runs', op: 'gte', value: '500' }, { field: 'wickets', op: 'gte', value: '50' }], context: {} },
      { type: 'derived', key: 'opening_bat_and_bowl',          label: 'Opening batting and bowling in the same match', description: 'Opened batting AND bowled in innings 1.' },
      { type: 'derived', key: 'batting_on_debut',              label: 'Top batting on debut',      description: 'Best score in a player\'s first match.' },
      { type: 'preset', label: 'Most balls faced in an innings', target: 'innings_list', sortBy: 'balls',              sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Most balls faced for a duck',  target: 'innings_list',  sortBy: 'balls',               sortDir: 'desc', filters: [{ field: 'runs', op: 'eq', value: '0' }], context: { dismissal: '' } },
      { type: 'derived', key: 'carried_bat',                   label: 'Carrying the bat',           description: 'Openers not out when team was bowled out.' },
      { type: 'preset', label: 'Hundreds in losses',           target: 'innings_list',  sortBy: 'runs',                sortDir: 'desc', filters: [{ field: 'runs', op: 'gte', value: '100' }], context: { result: 'lost' } },
      { type: 'preset', label: 'Captain runs',                 target: 'player_career', sortBy: 'runs',                sortDir: 'desc', filters: [], context: { captain_only: true } },
      { type: 'preset', label: 'Finals run scorers',           target: 'player_career', sortBy: 'runs',                sortDir: 'desc', filters: [], context: { finals_only: true } },
      { type: 'derived', key: 'most_runs_first_n',             label: 'Most runs after X matches',  description: 'Who scored most in their first N matches (set N in Context).' },
      { type: 'derived', key: 'milestone_runs',                label: 'Fastest to milestone',       description: 'Who reached a runs milestone in fewest matches.' },
      // Not out / dismissal
      { type: 'preset', label: 'Highest not out count',        target: 'player_career', sortBy: 'not_outs',            sortDir: 'desc', filters: [{ field: 'not_outs', op: 'gte', value: '1' }], context: {} },
      { type: 'derived', key: 'dismissal_bowled',              label: 'Highest bowled count',       description: 'Players most often dismissed bowled.' },
      { type: 'derived', key: 'dismissal_caught',              label: 'Highest caught count',       description: 'Players most often dismissed caught.' },
      { type: 'derived', key: 'dismissal_lbw',                 label: 'Highest LBW count',          description: 'Players most often dismissed LBW.' },
      { type: 'derived', key: 'dismissal_run_out',             label: 'Highest run-out count',      description: 'Players most often run out.' },
      { type: 'derived', key: 'dismissal_stumped',             label: 'Highest stumped count',      description: 'Players most often stumped.' },
      { type: 'derived', key: 'unusual_dismissals',            label: 'Unusual dismissals',         description: 'Rare dismissals (hit wicket, retired hurt, handled, etc.).' },
      { type: 'derived', key: 'caught_and_bowled',             label: 'Highest C&B count (batter)', description: 'Batters most often dismissed caught & bowled.' },
      { type: 'derived', key: 'most_minutes_in_season',        label: 'Most batting minutes in a season', description: 'Most minutes at the crease over one season.' },
      // Collapses
      { type: 'derived', key: 'collapse_5w',                   label: '5-wicket batting collapses', description: '5 wickets fell within 30 runs.' },
      { type: 'derived', key: 'collapse_6w',                   label: '6-wicket batting collapses', description: '6 wickets fell within 40 runs.' },
      { type: 'derived', key: 'collapse_7w',                   label: '7-wicket batting collapses', description: '7 wickets fell within 50 runs.' },
      { type: 'derived', key: 'collapse_8w',                   label: '8-wicket batting collapses', description: '8 wickets fell within 60 runs.' },
      { type: 'derived', key: 'collapse_9w',                   label: '9-wicket batting collapses', description: '9 wickets fell within 70 runs.' },
      // On this day
      { type: 'preset', label: 'On this day — batting',        target: 'innings_list',  sortBy: 'runs',                sortDir: 'desc', filters: [], context: { on_this_day: true } },
    ],
  },
  {
    key: 'partnerships', label: 'Partnerships', defaultOpen: false,
    items: [
      { type: 'preset', label: 'Top partnerships',               target: 'partnership_list', sortBy: 'runs', sortDir: 'desc', filters: [], context: {} },
      { type: 'derived', key: 'top_partnerships_by_wicket',      label: 'Top partnerships by wicket',  description: 'Best partnership at each wicket position.' },
      { type: 'derived', key: 'partnership_aggregates_pair',     label: 'Top partnership aggregates',  description: 'Total partnership runs per pair of batters.' },
      { type: 'derived', key: 'century_partnerships_pair',       label: 'Most century partnerships by pair', description: 'Count of 100+ partnerships per pair.' },
      { type: 'derived', key: 'best_partnership_pair',           label: 'Best partnership by pair',    description: 'Highest single partnership for each pair.' },
      { type: 'preset', label: 'On this day — partnerships',     target: 'partnership_list', sortBy: 'runs', sortDir: 'desc', filters: [], context: { on_this_day: true } },
    ],
  },
  {
    key: 'bowling', label: 'Bowling', defaultOpen: false,
    items: [
      // Aggregates
      { type: 'preset', label: 'Top wicket takers',                target: 'player_career', sortBy: 'wickets',             sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Best bowling in an innings',       target: 'spell_list',    sortBy: 'wickets',             sortDir: 'desc', filters: [], context: {} },
      { type: 'derived', key: 'best_bowling_in_match',             label: 'Best bowling in a match',  description: 'Combined wickets across both innings of a match.' },
      { type: 'preset', label: 'Top bowling averages',             target: 'player_career', sortBy: 'bowling_average',     sortDir: 'asc',  filters: [{ field: 'wickets', op: 'gte', value: '20' }], context: {} },
      { type: 'preset', label: 'Top bowling average in a season',  target: 'player_season', sortBy: 'bowling_average',     sortDir: 'asc',  filters: [{ field: 'wickets', op: 'gte', value: '10' }], context: {} },
      { type: 'preset', label: 'Top economy rates',                target: 'player_career', sortBy: 'bowling_economy',     sortDir: 'asc',  filters: [{ field: 'overs', op: 'gte', value: '50' }], context: {} },
      { type: 'preset', label: 'Top bowling strike rates',         target: 'player_career', sortBy: 'bowling_strike_rate', sortDir: 'asc',  filters: [{ field: 'wickets', op: 'gte', value: '20' }], context: {} },
      { type: 'preset', label: 'Most wickets in a season',         target: 'player_season', sortBy: 'wickets',             sortDir: 'desc', filters: [], context: {} },
      // Five-wicket innings
      { type: 'preset', label: 'Most five-wicket innings',         target: 'player_career', sortBy: 'five_wicket_innings', sortDir: 'desc', filters: [{ field: 'five_wicket_innings', op: 'gte', value: '1' }], context: {} },
      { type: 'preset', label: 'Most 5WI in a season',             target: 'player_season', sortBy: 'five_wicket_innings', sortDir: 'desc', filters: [], context: {} },
      { type: 'derived', key: 'consecutive_5wi',                   label: 'Most consecutive 5-wicket innings', description: 'Longest run of bowling spells with 5+ wickets.' },
      { type: 'derived', key: 'consecutive_innings_with_wicket',   label: 'Most consecutive innings taking a wicket', description: 'Longest bowling streak with 1+ wicket.' },
      // Debut
      { type: 'derived', key: 'bowling_on_debut',                  label: 'Best bowling on debut',     description: 'Best figures in a player\'s first spell.' },
      // Spells
      { type: 'preset', label: 'Most expensive bowling in an innings', target: 'spell_list', sortBy: 'runs',               sortDir: 'desc', filters: [{ field: 'overs', op: 'gte', value: '3' }], context: {} },
      { type: 'preset', label: 'Least expensive bowling in an innings', target: 'spell_list', sortBy: 'runs',              sortDir: 'asc',  filters: [{ field: 'overs', op: 'gte', value: '5' }], context: {} },
      { type: 'preset', label: 'Most wides in an innings',         target: 'spell_list',    sortBy: 'wides',               sortDir: 'desc', filters: [{ field: 'wides', op: 'gte', value: '1' }], context: {} },
      { type: 'preset', label: 'Most no-balls in an innings',      target: 'spell_list',    sortBy: 'no_balls',            sortDir: 'desc', filters: [{ field: 'no_balls', op: 'gte', value: '1' }], context: {} },
      { type: 'preset', label: 'Most overs in an innings',         target: 'spell_list',    sortBy: 'overs',               sortDir: 'desc', filters: [], context: {} },
      { type: 'derived', key: 'most_balls_bowled_match',           label: 'Most balls bowled in a match', description: 'Most deliveries by one bowler in a match.' },
      // Career extras
      { type: 'preset', label: 'Most wides bowled (career)',       target: 'player_career', sortBy: 'wides',               sortDir: 'desc', filters: [{ field: 'wides', op: 'gte', value: '1' }], context: {} },
      { type: 'preset', label: 'Most no-balls bowled (career)',    target: 'player_career', sortBy: 'no_balls',            sortDir: 'desc', filters: [{ field: 'no_balls', op: 'gte', value: '1' }], context: {} },
      { type: 'preset', label: 'Most maidens (career)',            target: 'player_career', sortBy: 'maidens',             sortDir: 'desc', filters: [], context: {} },
      // Special bowling reports
      { type: 'derived', key: 'hat_tricks',                        label: 'Hat tricks',                description: 'From Admin → Awards (manually recorded).' },
      { type: 'derived', key: 'ducks_inflicted',                   label: 'Most ducks inflicted',      description: 'Bowlers who dismissed batters for 0 most often.' },
      { type: 'derived', key: 'golden_ducks_inflicted',            label: 'Most golden ducks inflicted', description: 'Bowlers who dismissed batters for 0 off 0–1 balls.' },
      { type: 'derived', key: 'caught_and_bowled_bowler',          label: 'Highest C&B count (bowler)', description: 'Bowlers ranked by caught-and-bowled wickets taken.' },
      { type: 'derived', key: 'most_wickets_in_match',             label: 'Most wickets in a match',   description: 'Most wickets by one bowler across both innings.' },
      { type: 'derived', key: 'bowler_fielder_combo',              label: 'Top bowler/fielder combinations', description: 'Most productive bowler+catcher partnerships.' },
      { type: 'derived', key: 'top_opening_bowlers',               label: 'Top opening bowlers by match count', description: 'Players who most often take the new ball.' },
      { type: 'preset', label: 'On this day — bowling',            target: 'spell_list',    sortBy: 'wickets',             sortDir: 'desc', filters: [], context: { on_this_day: true } },
    ],
  },
  {
    key: 'fielding', label: 'Fielding & Keeping', defaultOpen: false,
    items: [
      { type: 'preset', label: 'Most catches (career)',     target: 'player_career', sortBy: 'catches',   sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Most catches in a season',  target: 'player_season', sortBy: 'catches',   sortDir: 'desc', filters: [], context: {} },
      { type: 'derived', key: 'most_catches_in_match',      label: 'Most catches in a match', description: 'Most catches by one fielder in a single match.' },
      { type: 'preset', label: 'Wicket-keeper catches',     target: 'player_career', sortBy: 'catches',   sortDir: 'desc', filters: [], context: { keeper_only: true } },
      { type: 'preset', label: 'Most stumpings (career)',   target: 'player_career', sortBy: 'stumpings', sortDir: 'desc', filters: [{ field: 'stumpings', op: 'gte', value: '1' }], context: {} },
      { type: 'preset', label: 'Most stumpings in a season',target: 'player_season', sortBy: 'stumpings', sortDir: 'desc', filters: [{ field: 'stumpings', op: 'gte', value: '1' }], context: {} },
      { type: 'derived', key: 'most_stumpings_in_match',    label: 'Most stumpings in a match', description: 'Most stumpings by one keeper in a single match.' },
      { type: 'preset', label: 'Most run outs (career)',    target: 'player_career', sortBy: 'run_outs',  sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Most run outs in a season', target: 'player_season', sortBy: 'run_outs',  sortDir: 'desc', filters: [], context: {} },
      { type: 'derived', key: 'most_run_outs_in_match',     label: 'Most run outs in a match', description: 'Most run outs effected by one fielder in a single match.' },
      { type: 'derived', key: 'catches_stumpings',          label: 'Top catches & stumpings combined', description: 'Sum of catches + stumpings per player.' },
    ],
  },
  {
    key: 'match', label: 'Match', defaultOpen: false,
    items: [
      { type: 'preset', label: 'Highest team scores',      target: 'match_list', sortBy: 'team_runs',    sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Lowest team scores',       target: 'match_list', sortBy: 'team_runs',    sortDir: 'asc',  filters: [{ field: 'team_runs', op: 'gt', value: '0' }], context: {} },
      { type: 'preset', label: 'Highest opposition scores',target: 'match_list', sortBy: 'opp_runs',     sortDir: 'desc', filters: [], context: {} },
      { type: 'preset', label: 'Lowest opposition scores', target: 'match_list', sortBy: 'opp_runs',     sortDir: 'asc',  filters: [{ field: 'opp_runs', op: 'gt', value: '0' }], context: {} },
      { type: 'preset', label: 'Biggest winning margins',  target: 'match_list', sortBy: 'margin_runs',  sortDir: 'desc', filters: [{ field: 'margin_runs', op: 'gt', value: '0' }], context: { result: 'won' } },
      { type: 'preset', label: 'Closest wins',             target: 'match_list', sortBy: 'margin_runs',  sortDir: 'asc',  filters: [{ field: 'margin_runs', op: 'gt', value: '0' }], context: { result: 'won' } },
      { type: 'preset', label: 'Biggest defeats',          target: 'match_list', sortBy: 'margin_runs',  sortDir: 'asc',  filters: [{ field: 'margin_runs', op: 'lt', value: '0' }], context: { result: 'lost' } },
      { type: 'preset', label: 'Finals',                   target: 'match_list', sortBy: 'team_runs',    sortDir: 'desc', filters: [], context: { finals_only: true } },
    ],
  },
]

const RESULT_OPTIONS = [
  { value: '', label: 'Any result' },
  { value: 'won', label: 'Won' },
  { value: 'lost', label: 'Lost' },
  { value: 'drawn', label: 'Drawn' },
  { value: 'tied', label: 'Tied' },
]

const DISMISSAL_OPTIONS = [
  { value: '', label: 'Any dismissal' },
  { value: 'bowled', label: 'Bowled' },
  { value: 'caught', label: 'Caught' },
  { value: 'lbw', label: 'LBW' },
  { value: 'run out', label: 'Run out' },
  { value: 'stumped', label: 'Stumped' },
  { value: 'hit wicket', label: 'Hit wicket' },
  { value: 'not out', label: 'Not out' },
]

// Columns to display per target shape. Match the keys to backend response keys.
const COLUMN_SETS = {
  player_career:    ['matches','batting_innings','runs','not_outs','batting_average','high_score','hundreds','fifties','ducks','wickets','bowling_average','bowling_economy','five_wicket_innings','catches','run_outs','stumpings'],
  player_season:    ['matches','batting_innings','runs','batting_average','high_score','hundreds','fifties','wickets','bowling_average','catches'],
  player_grade:     ['matches','batting_innings','runs','batting_average','high_score','hundreds','wickets','bowling_average','catches'],
  family_career:    ['member_count','matches','batting_innings','runs','batting_average','high_score','hundreds','fifties','ducks','wickets','bowling_average','five_wicket_innings','catches','run_outs','stumpings'],
  family_season:    ['member_count','matches','batting_innings','runs','batting_average','high_score','hundreds','wickets','bowling_average','catches'],
  family_grade:     ['member_count','matches','batting_innings','runs','batting_average','high_score','wickets','bowling_average','catches'],
  innings_list:     ['runs','balls','fours','sixes','strike_rate','batting_position'],
  spell_list:       ['overs','maidens','runs','wickets','economy'],
  match_list:       ['team_runs','team_wickets','opp_runs','opp_wickets','margin_runs'],
  partnership_list: ['runs','balls','wicket_number','batter1_runs','batter2_runs'],
}

const CONTEXT_KEYS = [
  'season_id','grade_id','grade_name','opposition','date_from','date_to',
  'min_year','max_year','finals_only','captain_only','keeper_only','result',
  'dismissal','position_min','position_max',
  'first_n_matches','milestone_runs','on_this_day',
  'gender','player_role','award_category','award_subcategory','award_name','office_bearer',
  'family_id',
]
// Context keys that carry an array of IDs (multi-select). Encoded in the URL
// as a single comma-separated value (c_season_ids=a,b,c) for compact links,
// and sent to the API the same way (the backend accepts either form).
const CONTEXT_LIST_KEYS = ['season_ids', 'grade_ids']

// Category groupings for the field picker. Field membership is intersected
// with each target's allowed metrics on render — categories with no eligible
// fields hide automatically. Kept in sync with backend METRIC_CATEGORIES.
const FILTER_CATEGORIES = [
  { key: 'participation', label: 'Participation',
    fields: ['matches','seasons_played','batting_innings','bowling_innings','member_count'] },
  { key: 'batting', label: 'Batting',
    fields: ['runs','not_outs','batting_average','batting_strike_rate','high_score',
             'fifties','hundreds','ducks','fours','sixes','balls_faced','balls',
             'strike_rate','batting_position'] },
  { key: 'bowling', label: 'Bowling',
    fields: ['wickets','overs','maidens','bowling_average','bowling_economy',
             'bowling_strike_rate','five_wicket_innings','best_bowling_wickets',
             'runs_conceded','wides','no_balls','economy'] },
  { key: 'fielding', label: 'Fielding',
    fields: ['catches','run_outs','stumpings'] },
  { key: 'match', label: 'Match',
    fields: ['team_runs','team_wickets','opp_runs','opp_wickets','margin_runs','innings_number'] },
  { key: 'partnership', label: 'Partnership',
    fields: ['wicket_number','batter1_runs','batter2_runs'] },
]

const CATEGORY_LOOKUP = (() => {
  const m = {}
  FILTER_CATEGORIES.forEach(c => c.fields.forEach(f => { if (!m[f]) m[f] = c }))
  return m
})()

const OPERATOR_SYMBOLS = { gte: '≥', gt: '>', eq: '=', lte: '≤', lt: '<', ne: '≠' }

const PAIR_DERIVED = new Set([
  'best_partnership_pair',
  'partnership_aggregates_pair',
  'century_partnerships_pair',
  'top_partnerships_by_wicket',
  'bowler_fielder_combo',
])

let _treeIdCounter = 1000
const newTreeId = () => ++_treeIdCounter

const emptyTree = () => ({ id: newTreeId(), type: 'group', op: 'AND', clauses: [] })

function flatToTree(filters) {
  return {
    id: newTreeId(),
    type: 'group',
    op: 'AND',
    clauses: (filters || []).map(f => ({
      id: newTreeId(),
      type: 'leaf',
      field: f.field,
      op: f.op,
      value: f.value,
    })),
  }
}

function ensureTreeIds(node) {
  if (!node || typeof node !== 'object') return node
  const withId = { ...node, id: node.id ?? newTreeId() }
  if (withId.type === 'group') {
    withId.clauses = (withId.clauses || []).map(ensureTreeIds)
  }
  return withId
}

function treeLeafCount(node) {
  if (!node) return 0
  if (node.type === 'leaf') return (node.field && node.value !== '' && node.value != null) ? 1 : 0
  return (node.clauses || []).reduce((n, c) => n + treeLeafCount(c), 0)
}

function treeFields(node) {
  const out = new Set()
  const walk = (n) => {
    if (!n) return
    if (n.type === 'leaf' && n.field) out.add(n.field)
    if (n.type === 'group') (n.clauses || []).forEach(walk)
  }
  walk(node)
  return [...out]
}

// Strip null/empty leaves so the backend / saved JSON never carries placeholder rows.
function cleanTree(node) {
  if (!node) return null
  if (node.type === 'leaf') {
    if (!node.field || !node.op || node.value === '' || node.value == null) return null
    return { type: 'leaf', field: node.field, op: node.op, value: node.value }
  }
  if (node.type === 'group') {
    const cleaned = (node.clauses || []).map(cleanTree).filter(Boolean)
    if (cleaned.length === 0) return null
    return { type: 'group', op: node.op || 'AND', clauses: cleaned }
  }
  return null
}

const DEFAULT_QUERY = {
  target: 'player_career',
  sortBy: 'runs',
  sortDir: 'desc',
  limit: 100,
  filterTree: emptyTree(),
  context: {},
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function encodeQueryToParams(q) {
  const p = new URLSearchParams()
  p.set('target', q.target)
  p.set('sort', q.sortBy)
  p.set('dir', q.sortDir)
  if (q.limit !== DEFAULT_QUERY.limit) p.set('limit', q.limit)
  const cleaned = cleanTree(q.filterTree)
  if (cleaned) p.set('ft', JSON.stringify(cleaned))
  Object.entries(q.context || {}).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '' || v === false) return
    if (Array.isArray(v)) {
      // Multi-select lists encoded as one comma-separated value.
      const joined = v.filter(x => x !== '' && x != null).join(',')
      if (joined) p.set(`c_${k}`, joined)
      return
    }
    p.set(`c_${k}`, v === true ? '1' : String(v))
  })
  return p
}

function decodeParamsToQuery(params) {
  const target = params.get('target') || DEFAULT_QUERY.target
  const sortBy = params.get('sort') || DEFAULT_QUERY.sortBy
  const sortDir = params.get('dir') || DEFAULT_QUERY.sortDir
  const limit = Number(params.get('limit')) || DEFAULT_QUERY.limit
  let filterTree = emptyTree()
  const ftRaw = params.get('ft')
  if (ftRaw) {
    try { filterTree = ensureTreeIds(JSON.parse(ftRaw)) } catch { /* ignore */ }
  } else {
    // Back-compat: ?f=field:op:value repeated → flat AND tree
    const flat = []
    params.getAll('f').forEach(raw => {
      const parts = raw.split(':')
      if (parts.length >= 3) flat.push({ field: parts[0], op: parts[1], value: parts.slice(2).join(':') })
    })
    if (flat.length) filterTree = flatToTree(flat)
  }
  const context = {}
  CONTEXT_KEYS.forEach(k => {
    const v = params.get(`c_${k}`)
    if (v == null) return
    if (k === 'finals_only' || k === 'captain_only' || k === 'keeper_only' || k === 'on_this_day') {
      context[k] = v === '1' || v === 'true'
    } else {
      context[k] = v
    }
  })
  CONTEXT_LIST_KEYS.forEach(k => {
    const v = params.get(`c_${k}`)
    if (!v) return
    const arr = v.split(',').map(s => s.trim()).filter(Boolean)
    if (arr.length) context[k] = arr
  })
  return { target, sortBy, sortDir, limit, filterTree, context }
}

function csvEscape(v) {
  if (v == null) return ''
  const s = String(v)
  if (s.includes(',') || s.includes('"') || s.includes('\n')) return `"${s.replace(/"/g, '""')}"`
  return s
}

// ─── Subcomponents ────────────────────────────────────────────────────────────

const inputCls = 'bg-pb-surface border border-pb-hairline2 text-pb-text text-xs rounded px-2 py-1.5 focus:outline-none focus:border-pb-accent w-full'
const selectCls = inputCls + ' cursor-pointer'

// Searchable picker for Player Role / Award / Office Bearer attribute filters.
// Hits /statlab/picker-values with the chosen kind and debounced search text.
function PickerInput({ orgId, kind, value, placeholder, onChange }) {
  const [query, setQuery] = useState(value || '')
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const wrapRef = useRef(null)

  useEffect(() => { setQuery(value || '') }, [value])

  useEffect(() => {
    if (!open || !orgId) return
    let cancelled = false
    const timer = setTimeout(async () => {
      setLoading(true)
      try {
        const data = await api.statlabPickerValues(orgId, kind, query)
        if (!cancelled) setItems(Array.isArray(data) ? data : [])
      } catch {
        if (!cancelled) setItems([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    }, 180)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [open, orgId, kind, query])

  useEffect(() => {
    const onClick = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const pick = (v) => { onChange(v); setQuery(v); setOpen(false) }
  const clear = () => { onChange(''); setQuery(''); setOpen(false) }

  return (
    <div ref={wrapRef} className="relative">
      <div className="flex gap-1">
        <input
          className={inputCls}
          placeholder={placeholder || 'Search…'}
          value={query}
          onChange={e => { setQuery(e.target.value); onChange(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
        />
        {value && (
          <button onClick={clear} className="text-pb-faint hover:text-pb-red text-xs px-1" title="Clear">×</button>
        )}
      </div>
      {open && (
        <div className="absolute z-50 mt-1 w-full bg-pb-bg pb-card shadow-xl max-h-52 overflow-auto pb-scroll">
          {loading && <div className="text-pb-faintest font-mono text-[10px] px-3 py-2">Loading…</div>}
          {!loading && items.length === 0 && (
            <div className="text-pb-faintest font-mono text-[10px] px-3 py-2">No matches.</div>
          )}
          {items.map(it => (
            <button
              key={it.value}
              onMouseDown={(e) => { e.preventDefault(); pick(it.value) }}
              className="block w-full text-left px-3 py-1.5 text-xs text-pb-dim hover:bg-pb-surface2 hover:text-pb-text"
            >
              {it.value}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// Compact multi-select checkbox panel. Renders selected count + opens a
// drop-down with a search box and a checkbox per option. Used for the
// Season and Grade context filters so users can combine selections (e.g.
// "2nd grade AND 3rd grade across 2022-2024 inclusive").
function MultiCheckPicker({ label, allLabel, options, value, onChange, searchPlaceholder }) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const wrapRef = useRef(null)
  const selected = Array.isArray(value) ? value : []
  const selectedSet = new Set(selected)

  useEffect(() => {
    const onClick = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const toggle = (id) => {
    const next = selectedSet.has(id)
      ? selected.filter(x => x !== id)
      : [...selected, id]
    onChange(next)
  }
  const clearAll = () => onChange([])

  const term = search.trim().toLowerCase()
  const filtered = term
    ? options.filter(o => (o.label || '').toLowerCase().includes(term))
    : options

  const summary = selected.length === 0
    ? allLabel
    : selected.length === 1
      ? (options.find(o => o.id === selected[0])?.label || '1 selected')
      : `${selected.length} selected`

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className={selectCls + ' mt-1 flex items-center justify-between text-left'}
      >
        <span className={selected.length ? 'text-pb-text' : 'text-pb-faint'}>{summary}</span>
        <span className="font-mono text-[10px] text-pb-faintest ml-1">▾</span>
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-full bg-pb-bg pb-card shadow-xl max-h-72 overflow-hidden flex flex-col">
          <div className="p-2 pb-hairline-b">
            <input
              autoFocus
              className={inputCls}
              placeholder={searchPlaceholder || `Search ${label.toLowerCase()}…`}
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <div className="flex-1 overflow-auto pb-scroll py-1">
            {filtered.length === 0 && (
              <p className="text-pb-faintest font-mono text-[10px] px-3 py-2">No matches.</p>
            )}
            {filtered.map(o => {
              const checked = selectedSet.has(o.id)
              return (
                <label
                  key={o.id}
                  className="flex items-center gap-2 px-3 py-1.5 cursor-pointer hover:bg-pb-surface2 select-none"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggle(o.id)}
                    className="accent-pb-accent"
                  />
                  <span className={`text-xs ${checked ? 'text-pb-text' : 'text-pb-dim'}`}>{o.label}</span>
                </label>
              )
            })}
          </div>
          <div className="flex items-center justify-between px-2 py-1.5 pb-hairline-t bg-pb-surface2/40">
            <span className="font-mono text-[10px] text-pb-faintest">
              {selected.length} of {options.length} selected
            </span>
            <div className="flex gap-2">
              {selected.length > 0 && (
                <button
                  type="button"
                  onClick={clearAll}
                  className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text"
                >
                  Clear
                </button>
              )}
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function ContextFiltersPanel({ ctx, onChange, seasons, grades, targetShape, target, activeDerived, orgId }) {
  const set = (k, v) => onChange({ ...ctx, [k]: v })
  const showInningsFilters = targetShape === 'list' || targetShape === 'aggregate'
  // Family targets are themselves family-aggregations, so a "filter to one
  // family" dropdown is redundant (you'd just see one row). Hide it there.
  const isFamilyTarget = typeof target === 'string' && target.startsWith('family_')
  const [families, setFamilies] = useState([])
  useEffect(() => {
    if (!orgId) return
    api.listFamilies(orgId).then(setFamilies).catch(() => setFamilies([]))
  }, [orgId])

  // Normalise legacy single-select context (season_id / grade_id) into the
  // new multi-select arrays so a saved-report URL from before multi-select
  // still pre-fills the picker. The single-select keys are kept on the ctx
  // unchanged until the user touches the picker (back-compat for the API).
  const seasonIds = Array.isArray(ctx.season_ids)
    ? ctx.season_ids
    : (ctx.season_id ? [ctx.season_id] : [])
  const gradeIds = Array.isArray(ctx.grade_ids)
    ? ctx.grade_ids
    : (ctx.grade_id ? [ctx.grade_id] : [])

  const setSeasonIds = (ids) => {
    const next = { ...ctx, season_ids: ids }
    // Once the user touches the multi-select picker we drop the legacy single
    // key so the two don't fight each other.
    delete next.season_id
    onChange(next)
  }
  const setGradeIds = (ids) => {
    const next = { ...ctx, grade_ids: ids }
    delete next.grade_id
    onChange(next)
  }

  return (
    <div className="flex flex-col gap-2.5">
      <div>
        <Label>Seasons</Label>
        <MultiCheckPicker
          label="Seasons"
          allLabel="All seasons"
          options={(seasons || []).map(s => ({ id: s.id, label: s.name }))}
          value={seasonIds}
          onChange={setSeasonIds}
        />
      </div>
      <div>
        <Label>Grades</Label>
        <MultiCheckPicker
          label="Grades"
          allLabel="All grades"
          options={(grades || []).map(g => ({ id: g.id, label: g.display_name || g.name }))}
          value={gradeIds}
          onChange={setGradeIds}
        />
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        <div>
          <Label>From</Label>
          <input type="date" className={inputCls + ' mt-1'} value={ctx.date_from || ''} onChange={e => set('date_from', e.target.value)} />
        </div>
        <div>
          <Label>To</Label>
          <input type="date" className={inputCls + ' mt-1'} value={ctx.date_to || ''} onChange={e => set('date_to', e.target.value)} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        <div>
          <Label>Min year</Label>
          <input type="number" className={inputCls + ' mt-1'} value={ctx.min_year || ''} placeholder="1996" onChange={e => set('min_year', e.target.value)} />
        </div>
        <div>
          <Label>Max year</Label>
          <input type="number" className={inputCls + ' mt-1'} value={ctx.max_year || ''} placeholder="2026" onChange={e => set('max_year', e.target.value)} />
        </div>
      </div>
      <div>
        <Label>Opposition</Label>
        <input className={inputCls + ' mt-1'} value={ctx.opposition || ''} placeholder="e.g. Bayswater" onChange={e => set('opposition', e.target.value)} />
      </div>
      <div>
        <Label>Result</Label>
        <select className={selectCls + ' mt-1'} value={ctx.result || ''} onChange={e => set('result', e.target.value)}>
          {RESULT_OPTIONS.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
        </select>
      </div>
      <div className="flex flex-wrap gap-2 pt-1">
        {[
          { k: 'finals_only',  label: 'Finals only' },
          { k: 'captain_only', label: 'As captain' },
          { k: 'keeper_only',  label: 'As keeper' },
          { k: 'on_this_day',  label: 'On this day' },
        ].map(({ k, label }) => (
          <label key={k} className="flex items-center gap-1 text-xs text-pb-dim cursor-pointer">
            <input type="checkbox" checked={!!ctx[k]} onChange={e => set(k, e.target.checked)} />
            {label}
          </label>
        ))}
      </div>
      {showInningsFilters && (
        <>
          <div>
            <Label>Dismissal</Label>
            <select className={selectCls + ' mt-1'} value={ctx.dismissal || ''} onChange={e => set('dismissal', e.target.value)}>
              {DISMISSAL_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            <div>
              <Label>Position (min)</Label>
              <input type="number" min="1" max="11" className={inputCls + ' mt-1'} value={ctx.position_min || ''} placeholder="1" onChange={e => set('position_min', e.target.value)} />
            </div>
            <div>
              <Label>Position (max)</Label>
              <input type="number" min="1" max="11" className={inputCls + ' mt-1'} value={ctx.position_max || ''} placeholder="11" onChange={e => set('position_max', e.target.value)} />
            </div>
          </div>
        </>
      )}
      {activeDerived === 'most_runs_first_n' && (
        <div>
          <Label>First N matches</Label>
          <select className={selectCls + ' mt-1'} value={ctx.first_n_matches || '50'}
                  onChange={e => set('first_n_matches', e.target.value)}>
            {[10, 25, 50, 100, 200].map(n => <option key={n} value={n}>First {n}</option>)}
          </select>
        </div>
      )}
      {activeDerived === 'milestone_runs' && (
        <div>
          <Label>Runs milestone</Label>
          <select className={selectCls + ' mt-1'} value={ctx.milestone_runs || '1000'}
                  onChange={e => set('milestone_runs', e.target.value)}>
            {[100, 500, 1000, 2000, 5000].map(n => <option key={n} value={n}>{n.toLocaleString()} runs</option>)}
          </select>
        </div>
      )}

      {/* Player attribute filters — restrict the result set to players matching
          a profile attribute (gender, player role) or an Admin → Awards entry. */}
      <div className="pt-2 mt-1 pb-hairline-t">
        <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">PLAYER ATTRIBUTES</div>
        <div className="flex flex-col gap-2">
          <div>
            <Label>Gender</Label>
            <select className={selectCls + ' mt-1'} value={ctx.gender || ''} onChange={e => set('gender', e.target.value)}>
              <option value="">Any gender</option>
              <option value="Male">Male</option>
              <option value="Female">Female</option>
            </select>
          </div>
          <div>
            <Label>Player role</Label>
            <PickerInput orgId={orgId} kind="player_role" value={ctx.player_role || ''}
                         placeholder="e.g. Batter, Bowler, Wicket-keeper"
                         onChange={v => set('player_role', v)} />
          </div>
          <div>
            <Label>Has award (category)</Label>
            <PickerInput orgId={orgId} kind="award_category" value={ctx.award_category || ''}
                         placeholder="e.g. Hall of Fame, Premiership"
                         onChange={v => set('award_category', v)} />
          </div>
          <div>
            <Label>Has award (name)</Label>
            <PickerInput orgId={orgId} kind="award_name" value={ctx.award_name || ''}
                         placeholder="e.g. Best & Fairest"
                         onChange={v => set('award_name', v)} />
          </div>
          <div>
            <Label>Office bearer</Label>
            <PickerInput orgId={orgId} kind="office_bearer" value={ctx.office_bearer || ''}
                         placeholder="e.g. President, Secretary"
                         onChange={v => set('office_bearer', v)} />
          </div>
          {families.length > 0 && !isFamilyTarget && (
            <div>
              <Label>In family</Label>
              <select className={selectCls + ' mt-1'} value={ctx.family_id || ''} onChange={e => set('family_id', e.target.value)}>
                <option value="">Any family</option>
                {families.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
              </select>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Filter Bar (top-of-page boolean filter tree) ─────────────────────────────

function categoriesForTarget(targetMetrics) {
  const metricSet = new Set(targetMetrics || [])
  return FILTER_CATEGORIES
    .map(c => ({ ...c, fields: c.fields.filter(f => metricSet.has(f)) }))
    .filter(c => c.fields.length > 0)
}

function FieldPicker({ open, onClose, onPick, categories, anchorRect }) {
  const [search, setSearch] = useState('')
  useEffect(() => { if (open) setSearch('') }, [open])
  if (!open) return null
  const term = search.trim().toLowerCase()
  const filtered = categories.map(c => ({
    ...c,
    fields: c.fields.filter(f => !term || (METRIC_LABELS[f]?.label || f).toLowerCase().includes(term) || f.toLowerCase().includes(term)),
  })).filter(c => c.fields.length > 0)

  return (
    <>
      <div className="fixed inset-0 z-30" onClick={onClose} />
      <div
        className="absolute z-40 mt-1 bg-pb-bg pb-card shadow-xl w-[340px] max-h-[420px] overflow-auto pb-scroll"
        style={{ top: anchorRect?.bottom ? `${anchorRect.bottom + window.scrollY}px` : undefined, left: anchorRect?.left ? `${anchorRect.left + window.scrollX}px` : undefined }}
      >
        <div className="sticky top-0 bg-pb-bg pb-hairline-b p-2">
          <input
            autoFocus
            className={inputCls}
            placeholder="Search metrics…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <div className="py-1">
          {filtered.length === 0 && <p className="text-pb-faintest text-xs px-3 py-3">No matching metrics for this query type.</p>}
          {filtered.map(c => (
            <div key={c.key} className="px-2 py-1.5">
              <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest px-1 mb-1">{c.label.toUpperCase()}</div>
              <div className="flex flex-col gap-0.5">
                {c.fields.map(f => (
                  <button
                    key={f}
                    onClick={() => { onPick(f); onClose() }}
                    title={METRIC_LABELS[f]?.label || f}
                    className="text-left px-2 py-1.5 rounded hover:bg-pb-surface2 text-[12px] text-pb-dim hover:text-pb-text transition"
                  >
                    {METRIC_LABELS[f]?.label || f}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}

function FilterLeaf({ leaf, categories, onChange, onRemove }) {
  const [pickerOpen, setPickerOpen] = useState(false)
  const [anchor, setAnchor] = useState(null)
  const fieldBtnRef = useRef(null)
  const openPicker = () => {
    if (fieldBtnRef.current) setAnchor(fieldBtnRef.current.getBoundingClientRect())
    setPickerOpen(true)
  }
  const cat = leaf.field ? CATEGORY_LOOKUP[leaf.field] : null
  const fieldLabel = leaf.field ? (METRIC_LABELS[leaf.field]?.label || leaf.field) : 'Choose metric'
  return (
    <div className="flex items-center gap-1.5 bg-pb-surface border border-pb-hairline rounded-md px-1 py-1 hover:border-pb-hairline2 transition">
      <button
        ref={fieldBtnRef}
        onClick={openPicker}
        className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-pb-surface2 transition min-w-[180px] text-left"
      >
        {cat && <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest uppercase">{cat.label}</span>}
        <span className="text-pb-text font-medium text-xs truncate">{fieldLabel}</span>
        <span className="text-pb-faint text-[10px]">▾</span>
      </button>
      <select
        className={selectCls + ' w-28'}
        value={leaf.op}
        onChange={e => onChange({ ...leaf, op: e.target.value })}
        title="Operator"
      >
        {OPERATORS.map(o => (
          <option key={o.key} value={o.key}>{o.label}</option>
        ))}
      </select>
      <input
        type="number"
        className={inputCls + ' w-20'}
        value={leaf.value}
        placeholder="0"
        onChange={e => onChange({ ...leaf, value: e.target.value })}
      />
      <button
        onClick={onRemove}
        className="text-pb-faint hover:text-pb-red font-mono text-base leading-none px-1.5"
        title="Remove filter"
      >×</button>
      <FieldPicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onPick={(field) => onChange({ ...leaf, field })}
        categories={categories}
        anchorRect={anchor}
      />
    </div>
  )
}

function FilterGroup({ node, categories, onChange, onRemove, depth = 0 }) {
  const isRoot = depth === 0
  const setOp = (op) => onChange({ ...node, op })
  const addLeaf = () => {
    const cl = [...(node.clauses || []), { id: newTreeId(), type: 'leaf', field: '', op: 'gte', value: '' }]
    onChange({ ...node, clauses: cl })
  }
  const addGroup = () => {
    const cl = [...(node.clauses || []), {
      id: newTreeId(), type: 'group', op: 'OR', clauses: [
        { id: newTreeId(), type: 'leaf', field: '', op: 'gte', value: '' },
      ],
    }]
    onChange({ ...node, clauses: cl })
  }
  const updateChild = (id, next) => {
    if (next == null) {
      onChange({ ...node, clauses: node.clauses.filter(c => c.id !== id) })
      return
    }
    onChange({ ...node, clauses: node.clauses.map(c => c.id === id ? next : c) })
  }
  const isEmpty = !node.clauses || node.clauses.length === 0
  return (
    <div className={isRoot ? '' : 'border-l-2 border-pb-accent/40 pl-3 ml-1 my-1'}>
      <div className="flex items-center gap-2 flex-wrap mb-2">
        <Label>{isRoot ? 'Filters' : 'Group'}</Label>
        <div className="flex gap-1">
          {['AND','OR'].map(op => (
            <button
              key={op}
              onClick={() => setOp(op)}
              className={`px-2 py-0.5 font-mono text-[10px] tracking-wide2 rounded border transition ${node.op === op ? 'text-pb-text bg-pb-surface2 border-pb-hairline2' : 'text-pb-faint border-transparent hover:border-pb-hairline'}`}
            >
              {op}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <button onClick={addLeaf} className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">+ filter</button>
        <button onClick={addGroup} className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">+ group</button>
        {!isRoot && (
          <button onClick={onRemove} className="text-pb-faint hover:text-pb-red font-mono text-base leading-none px-1">×</button>
        )}
      </div>
      {isEmpty && isRoot && (
        <p className="text-pb-faintest font-mono text-[10.5px] mb-2">No filters yet. Click <span className="text-pb-faint">+ filter</span> to narrow your results.</p>
      )}
      <div className="flex flex-wrap gap-1.5 items-center">
        {(node.clauses || []).map((c, i) => (
          <div key={c.id} className="flex items-center gap-1.5">
            {i > 0 && (
              <span className="font-mono text-[10px] tracking-wide2 text-pb-faint px-1.5 py-0.5 rounded bg-pb-surface2/50">{node.op}</span>
            )}
            {c.type === 'leaf' ? (
              <FilterLeaf
                leaf={c}
                categories={categories}
                onChange={(next) => updateChild(c.id, next)}
                onRemove={() => updateChild(c.id, null)}
              />
            ) : (
              <FilterGroup
                node={c}
                categories={categories}
                onChange={(next) => updateChild(c.id, next)}
                onRemove={() => updateChild(c.id, null)}
                depth={depth + 1}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function FilterBar({ tree, categories, onChange, onClear }) {
  const count = treeLeafCount(tree)
  return (
    <div className="pb-card p-3 mb-5">
      <FilterGroup
        node={tree}
        categories={categories}
        onChange={onChange}
        onRemove={() => {}}
        depth={0}
      />
      {count > 0 && (
        <div className="flex justify-end pt-2 mt-2 pb-hairline-t">
          <button onClick={onClear} className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">Clear all filters</button>
        </div>
      )}
    </div>
  )
}

function SaveReportModal({ open, onClose, onSave, defaultTitle, initial }) {
  const [title, setTitle] = useState(initial?.title || defaultTitle || '')
  const [description, setDescription] = useState(initial?.description || '')
  const [visibility, setVisibility] = useState(initial?.visibility || 'club')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  useEffect(() => {
    if (open) {
      setTitle(initial?.title || defaultTitle || '')
      setDescription(initial?.description || '')
      setVisibility(initial?.visibility || 'club')
      setError(null)
    }
  }, [open, initial, defaultTitle])
  if (!open) return null
  const submit = async () => {
    if (title.trim().length < 2) { setError('Title is required'); return }
    setSaving(true); setError(null)
    try { await onSave({ title: title.trim(), description: description.trim() || null, visibility }) }
    catch (e) { setError(e.message); setSaving(false); return }
    setSaving(false)
  }
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="bg-pb-bg pb-card max-w-md w-full p-5" onClick={e => e.stopPropagation()}>
        <Label>{initial ? 'EDIT REPORT' : 'SAVE REPORT'}</Label>
        <h3 className="text-pb-text font-semibold text-lg mt-1 mb-4">{initial ? 'Update saved report' : 'Save this query'}</h3>
        <div className="flex flex-col gap-3">
          <div>
            <Label>Title</Label>
            <input className={inputCls + ' mt-1'} value={title} onChange={e => setTitle(e.target.value)} maxLength={120} />
          </div>
          <div>
            <Label>Description</Label>
            <textarea className={inputCls + ' mt-1'} rows="2" value={description} maxLength={500} onChange={e => setDescription(e.target.value)} placeholder="Optional context for whoever opens this report" />
          </div>
          <div>
            <Label>Visibility</Label>
            <div className="flex gap-2 mt-1">
              {['club','private'].map(v => (
                <button key={v} onClick={() => setVisibility(v)} className={`flex-1 py-1.5 font-mono text-[10.5px] tracking-wide2 rounded border ${visibility === v ? 'text-pb-text bg-pb-surface2 border-pb-hairline2' : 'text-pb-faint border-transparent hover:border-pb-hairline'}`}>
                  {v === 'club' ? 'CLUB · PUBLIC' : 'PRIVATE'}
                </button>
              ))}
            </div>
            <p className="text-[10px] text-pb-faintest mt-1">
              {visibility === 'club'
                ? 'Sent to your club admin for approval. Once approved, it will appear in the Saved Reports list for everyone at your club.'
                : 'Only you (when logged in) will see this report in the list.'}
            </p>
          </div>
          {error && <p className="text-pb-red text-sm">{error}</p>}
          <div className="flex gap-2 justify-end pt-2">
            <Btn onClick={onClose}>Cancel</Btn>
            <Btn primary onClick={submit} disabled={saving}>{saving ? 'Saving…' : (initial ? 'Update' : 'Save')}</Btn>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function StatLab() {
  const { clubSlug, reportSlug } = useParams()
  const { club, orgId, inactive } = useClub(clubSlug)
  const { org, seasons, loading: clubLoading } = useClubData(orgId)
  const { user } = useAuth()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const [schema, setSchema] = useState(null)
  const [query, setQuery] = useState(() => decodeParamsToQuery(searchParams))
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [hasQueried, setHasQueried] = useState(false)
  const [error, setError] = useState(null)
  const [clientSort, setClientSort] = useState({ col: null, dir: null })
  const [currentPage, setCurrentPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)

  const [reports, setReports] = useState([])
  const [reportsLoading, setReportsLoading] = useState(false)
  const [openReport, setOpenReport] = useState(null) // when viewing a saved report
  const [saveOpen, setSaveOpen] = useState(false)
  const [editingReport, setEditingReport] = useState(null)

  const [grades, setGrades] = useState([])
  const [activeDerived, setActiveDerived] = useState(null)
  const [openGroups, setOpenGroups] = useState(() => Object.fromEntries(PRESET_GROUPS.map(g => [g.key, g.defaultOpen])))
  const [showCustomise, setShowCustomise] = useState(false)

  const queryRef = useRef(query)
  queryRef.current = query

  const activeDerivedRef = useRef(activeDerived)
  activeDerivedRef.current = activeDerived

  // Load schema once
  useEffect(() => {
    let cancelled = false
    api.statlabSchema().then(s => { if (!cancelled) setSchema(s) }).catch(() => {})
    return () => { cancelled = true }
  }, [])

  // Load grades whenever org changes
  useEffect(() => {
    if (!orgId) return
    api.getOrgGrades(orgId).then(setGrades).catch(() => setGrades([]))
  }, [orgId])

  // Load reports whenever org changes
  const refreshReports = useCallback(async () => {
    if (!orgId) return
    setReportsLoading(true)
    try { setReports(await api.statlabListReports(orgId)) }
    catch { setReports([]) }
    finally { setReportsLoading(false) }
  }, [orgId])
  useEffect(() => { refreshReports() }, [refreshReports])

  // Load a saved report when URL has reportSlug
  useEffect(() => {
    if (!orgId || !reportSlug) {
      setOpenReport(null)
      return
    }
    let cancelled = false
    api.statlabGetReport(reportSlug, orgId).then(r => {
      if (cancelled) return
      setOpenReport(r)
      const incoming = r.query_json || {}
      const q = { ...DEFAULT_QUERY, ...incoming }
      // Migrate legacy reports (flat filters array) and ensure tree node ids
      if (incoming.filterTree) {
        q.filterTree = ensureTreeIds(incoming.filterTree)
      } else if (Array.isArray(incoming.filters) && incoming.filters.length) {
        q.filterTree = flatToTree(incoming.filters)
      } else {
        q.filterTree = emptyTree()
      }
      delete q.filters
      q.context = q.context || {}
      setQuery(q)
      setHasQueried(false)
    }).catch(() => setOpenReport(null))
    return () => { cancelled = true }
  }, [orgId, reportSlug])

  const targetMeta = useMemo(() => TARGETS.find(t => t.key === query.target) || TARGETS[0], [query.target])
  const targetMetrics = useMemo(() => schema?.targets?.[query.target]?.metrics || [], [schema, query.target])

  // If user switches target and the current sortBy isn't valid, snap to default
  useEffect(() => {
    if (!schema) return
    const validMetrics = schema.targets?.[query.target]?.metrics || []
    if (!validMetrics.includes(query.sortBy)) {
      const def = schema.targets?.[query.target]?.default_sort || validMetrics[0]
      if (def) setQuery(q => ({ ...q, sortBy: def }))
    }
  }, [query.target, schema])

  // Sync URL whenever query changes
  useEffect(() => {
    if (reportSlug) return // when viewing a saved report, keep URL clean
    const p = encodeQueryToParams(query)
    setSearchParams(p, { replace: true })
  }, [query, reportSlug, setSearchParams])

  if (inactive) return <ClubInactive />

  const runQuery = useCallback(async (overrideQuery, overrideDerived = undefined, page = 1) => {
    if (!orgId) return
    const q = overrideQuery || queryRef.current
    // undefined = preserve current derived; null = clear it; string = set new derived
    const useDerived = overrideDerived !== undefined ? overrideDerived : activeDerivedRef.current
    setLoading(true); setError(null); setHasQueried(true); setClientSort({ col: null, dir: null })
    setActiveDerived(useDerived)
    const cleaned = cleanTree(q.filterTree)
    try {
      let data
      if (useDerived) {
        data = await api.statlabDerived(orgId, useDerived, { limit: q.limit, page, context: q.context })
      } else {
        data = await api.statlabQuery(orgId, {
          target: q.target, sortBy: q.sortBy, sortDir: q.sortDir,
          limit: q.limit, page, filterTree: cleaned, context: q.context,
        })
      }
      setRows(data.rows)
      setHasMore(data.has_more)
      setCurrentPage(data.page)
    } catch (e) {
      setError(e.message); setRows([]); setHasMore(false); setCurrentPage(1)
    } finally { setLoading(false) }
  }, [orgId])

  const applyPreset = useCallback(async (preset) => {
    const next = {
      target: preset.target,
      sortBy: preset.sortBy,
      sortDir: preset.sortDir,
      limit: DEFAULT_QUERY.limit,
      filterTree: flatToTree(preset.filters || []),
      context: preset.context || {},
    }
    setQuery(next)
    setOpenReport(null)
    if (reportSlug) navigate(`/${clubSlug}/statlab`, { replace: true })
    await runQuery(next, null)
  }, [runQuery, clubSlug, navigate, reportSlug])

  const applyDerived = useCallback(async (name) => {
    const next = { ...queryRef.current, filterTree: emptyTree() }
    setQuery(next)
    await runQuery(next, name)
  }, [runQuery])

  const applyGroupItem = useCallback(async (item) => {
    if (item.type === 'derived') {
      await applyDerived(item.key)
    } else {
      await applyPreset(item)
    }
  }, [applyPreset, applyDerived])

  const changePage = useCallback((page) => {
    runQuery(undefined, undefined, page)
  }, [runQuery])

  const toggleGroup = (key) => setOpenGroups(prev => ({ ...prev, [key]: !prev[key] }))

  const resetAll = () => {
    setQuery(DEFAULT_QUERY)
    setRows([]); setHasQueried(false); setError(null); setActiveDerived(null)
    setCurrentPage(1); setHasMore(false)
    setOpenReport(null)
    if (reportSlug) navigate(`/${clubSlug}/statlab`, { replace: true })
  }

  const handleColSort = (col) => {
    const dir = clientSort.col === col && clientSort.dir === 'desc' ? 'asc' : 'desc'
    setClientSort({ col, dir })
  }

  const sortedRows = useMemo(() => {
    if (!clientSort.col) return rows
    return [...rows].sort((a, b) => {
      const va = a[clientSort.col]
      const vb = b[clientSort.col]
      const nva = typeof va === 'number' ? va : parseFloat(va)
      const nvb = typeof vb === 'number' ? vb : parseFloat(vb)
      const an = isFinite(nva), bn = isFinite(nvb)
      if (an && bn) return clientSort.dir === 'asc' ? nva - nvb : nvb - nva
      const sa = String(va ?? ''), sb = String(vb ?? '')
      return clientSort.dir === 'asc' ? sa.localeCompare(sb) : sb.localeCompare(sa)
    })
  }, [rows, clientSort])

  // Columns to render in the results table
  const tableColumns = useMemo(() => {
    if (activeDerived && schema?.derived?.[activeDerived]) {
      // Skip player identity columns — those are rendered as the dim column already.
      const dimKeys = new Set(['player_id', 'player_name', 'player_a_id', 'player_a_name', 'player_b_id', 'player_b_name', 'pair'])
      return schema.derived[activeDerived].columns.filter(c => !dimKeys.has(c.key))
    }
    const set = COLUMN_SETS[query.target] || []
    // Promote filtered fields and the active sort to the front
    const filteredKeys = treeFields(query.filterTree)
    const order = []
    const seen = new Set()
    ;[...filteredKeys, query.sortBy, ...set].forEach(k => {
      if (!seen.has(k) && METRIC_LABELS[k]) { order.push(k); seen.add(k) }
    })
    return order.map(k => ({ key: k, ...METRIC_LABELS[k] }))
  }, [query, schema, activeDerived])

  const downloadCSV = () => {
    if (!sortedRows.length) return
    const dimCols = entityHeader(query.target, activeDerived)
    const cols = activeDerived
      ? schema.derived[activeDerived].columns
      : tableColumns
    const header = [...dimCols.map(c => c.label), ...cols.map(c => c.label || c.key)]
    const lines = [header.join(',')]
    sortedRows.forEach(row => {
      const left = dimCols.map(c => csvEscape(row[c.key] ?? ''))
      const right = cols.map(c => csvEscape(row[c.key] ?? ''))
      lines.push([...left, ...right].join(','))
    })
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `statlab_${activeDerived || query.target}_${Date.now()}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const [saveFlash, setSaveFlash] = useState(null)
  const saveReport = useCallback(async (payload) => {
    const q = queryRef.current
    const cleanedTree = cleanTree(q.filterTree)
    const queryJson = {
      target: q.target,
      sortBy: q.sortBy,
      sortDir: q.sortDir,
      limit: q.limit,
      filterTree: cleanedTree,
      context: q.context || {},
      derived: activeDerived || null,
    }
    let saved
    if (editingReport) {
      saved = await api.statlabPatchReport(editingReport.id, { ...payload, query_json: queryJson })
    } else {
      saved = await api.statlabCreateReport({ ...payload, query_json: queryJson })
    }
    setSaveOpen(false)
    setEditingReport(null)
    refreshReports()
    if (saved?.status === 'pending') {
      setSaveFlash({
        kind: 'pending',
        message: 'Sent to your club admin for approval. Once approved, it will appear in the Saved Reports list for everyone at your club.',
      })
    } else if (saved?.visibility === 'private') {
      setSaveFlash({ kind: 'ok', message: 'Saved as a private report. Only you will see it.' })
    } else {
      setSaveFlash({ kind: 'ok', message: 'Report saved and published to your club.' })
    }
    setTimeout(() => setSaveFlash(null), 8000)
  }, [editingReport, activeDerived, refreshReports])

  const deleteReport = useCallback(async (r) => {
    if (!window.confirm(`Delete saved report "${r.title}"?`)) return
    await api.statlabDeleteReport(r.id)
    refreshReports()
    if (openReport?.id === r.id) {
      setOpenReport(null)
      navigate(`/${clubSlug}/statlab`)
    }
  }, [refreshReports, openReport, navigate, clubSlug])

  if (clubLoading || !schema) return <PbSpinner message="Loading…" />

  const canSave = !!user && user.club_id === orgId

  // Indicators for the Customise drawer — show how many fields are "active"
  // relative to defaults so users can see at a glance what's been tweaked.
  const filterCount = treeLeafCount(query.filterTree)
  const contextCount = countActiveContext(query.context)
  // The sort is "active" when it's set (any value) and we're not currently
  // viewing a derived report (derived reports manage their own sort).
  const sortIsActive = !activeDerived && !!query.sortBy
  const activeFieldCount = filterCount + contextCount + (sortIsActive ? 1 : 0)

  // ─── Layout ────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1500px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow={openReport ? 'SAVED REPORT' : 'STAT LAB · CUSTOM QUERY'}
          title={openReport ? openReport.title : 'Build your own table.'}
          meta={openReport
            ? [
                <span key="d">{openReport.description || `${org?.name || ''} · saved report`}</span>,
                openReport.owner_name ? <span key="o">by {openReport.owner_name}</span> : null,
                <span key="v">{openReport.view_count || 0} view{(openReport.view_count || 0) === 1 ? '' : 's'}</span>,
              ].filter(Boolean)
            : [<span key="s">{org?.name || ''} · Filter, sort, discover, share.</span>]
          }
          actions={openReport && canSave ? (
            <div className="flex gap-2">
              <Btn onClick={() => { setEditingReport(openReport); setSaveOpen(true) }}>Edit</Btn>
              <Btn onClick={() => deleteReport(openReport)}>Delete</Btn>
              <Btn onClick={() => { setOpenReport(null); navigate(`/${clubSlug}/statlab?${encodeQueryToParams(query).toString()}`) }}>Edit a copy</Btn>
            </div>
          ) : null}
        />

        {/* Target tabs — informational on what data type results are showing */}
        <div className="flex gap-1 pb-hairline-b mb-4 overflow-x-auto pb-no-scrollbar">
          {TARGETS.map(t => (
            <button key={t.key} onClick={() => { setQuery(q => ({ ...q, target: t.key })); setRows([]); setHasQueried(false); setActiveDerived(null); setShowCustomise(true) }}
              className={`relative px-3.5 py-2.5 text-[11px] font-mono font-semibold tracking-wide3 whitespace-nowrap transition ${query.target === t.key && !activeDerived ? 'text-pb-text' : 'text-pb-faint hover:text-pb-dim'}`}>
              {t.label.toUpperCase()}
              {query.target === t.key && !activeDerived && <span className="absolute left-2 right-2 -bottom-px h-[2px]" style={{ background: 'var(--pb-accent)' }} />}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[320px_1fr] gap-5">
          {/* Left panel: REPORTS (primary) + SAVED REPORTS */}
          <div className="space-y-4">
            <Card title="REPORTS" pad="p-0">
              <div>
                {PRESET_GROUPS.map(group => {
                  const isOpen = openGroups[group.key]
                  return (
                    <div key={group.key} className="pb-hairline-b last:border-0">
                      <button
                        onClick={() => toggleGroup(group.key)}
                        className="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-pb-surface2/60 transition text-left select-none"
                      >
                        <span className={`font-mono text-[10.5px] font-semibold tracking-wide3 flex-1 transition ${isOpen ? 'text-pb-text' : 'text-pb-dim'}`}>
                          {group.label.toUpperCase()}
                        </span>
                        <span className="font-mono text-[9px] text-pb-faintest tabular-nums">{group.items.length}</span>
                        <span className={`font-mono text-[11px] text-pb-faintest transition-transform duration-150 inline-block ${isOpen ? 'rotate-90' : ''}`}>›</span>
                      </button>
                      {isOpen && (
                        <div className="px-2 pb-2">
                          {group.items.map((item, idx) => {
                            const isActive = item.type === 'derived' && activeDerived === item.key
                            const isDerived = item.type === 'derived'
                            return (
                              <button
                                key={item.key || item.label + idx}
                                onClick={() => applyGroupItem(item)}
                                className={`w-full text-left flex items-start gap-1.5 px-2 py-1.5 rounded transition group ${isActive ? 'bg-pb-surface2' : 'hover:bg-pb-surface2/60'}`}
                              >
                                <span className={`font-mono text-[9px] mt-0.5 shrink-0 select-none ${isActive ? 'text-pb-accent' : 'text-pb-faintest group-hover:text-pb-dim'}`}>
                                  {isDerived ? '≈' : '·'}
                                </span>
                                <div className="flex-1 min-w-0">
                                  <div className={`font-mono text-[11px] tracking-wide leading-snug ${isActive ? 'text-pb-accent font-medium' : 'text-pb-faint group-hover:text-pb-text'}`}>
                                    {item.label}
                                  </div>
                                  {isDerived && item.description && (
                                    <div className="text-[9.5px] text-pb-faintest font-sans normal-case tracking-normal mt-0.5 leading-tight">
                                      {item.description}
                                    </div>
                                  )}
                                </div>
                              </button>
                            )
                          })}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </Card>

            <Card title={`SAVED REPORTS · ${reports.length}`}>
              {reportsLoading
                ? <p className="text-pb-faintest font-mono text-[10.5px]">Loading…</p>
                : reports.length === 0
                  ? <p className="text-pb-faintest font-mono text-[10.5px]">No saved reports yet.</p>
                  : (
                    <ul className="flex flex-col gap-1">
                      {reports.map(r => (
                        <li key={r.id}>
                          <Link to={`/${clubSlug}/statlab/r/${r.slug}`} className="block px-2 py-1.5 rounded hover:bg-pb-surface2 transition">
                            <div className="font-semibold text-[12px] text-pb-text">{r.title}</div>
                            <div className="font-mono text-[10px] text-pb-faintest tracking-wide2">
                              {(r.owner_name || 'club')} · {r.view_count} view{r.view_count === 1 ? '' : 's'}
                            </div>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )
              }
            </Card>
          </div>

          {/* Right panel: customise drawer + results */}
          <div className="space-y-4">
            {/* Customise drawer — modify the current report's sort, filters, context */}
            <div className="pb-card">
              <button
                onClick={() => setShowCustomise(v => !v)}
                className="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-pb-surface2/60 transition text-left select-none"
              >
                <div className="flex-1 min-w-0">
                  <span className="font-mono text-[10.5px] font-semibold tracking-wide3 text-pb-dim block">
                    CUSTOMISE QUERY
                  </span>
                  <span className="font-sans text-[10.5px] text-pb-faintest mt-0.5 block normal-case tracking-normal">
                    Tweak sort, filters and context for the current report.
                  </span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {!showCustomise && activeFieldCount > 0 && (
                    <span
                      className="font-mono text-[9px] tracking-wide2 px-1.5 py-0.5 rounded"
                      style={{ background: 'color-mix(in srgb, var(--pb-accent) 18%, transparent)', color: 'var(--pb-accent)' }}
                    >
                      {activeFieldCount} ACTIVE
                    </span>
                  )}
                  <span className={`font-mono text-[11px] text-pb-faintest transition-transform duration-150 inline-block ${showCustomise ? 'rotate-90' : ''}`}>›</span>
                </div>
              </button>
              {showCustomise && (
                <div className="px-4 pb-4 pt-3 pb-hairline-t space-y-3">
                  {/* Sort + Direction + Limit on one row */}
                  <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto_auto] gap-2 items-end">
                    <div>
                      <Label>
                        Sort by
                        {sortIsActive && <ActiveDot />}
                      </Label>
                      <select
                        className={selectCls + ' mt-1' + (sortIsActive ? ' border-pb-accent' : '')}
                        value={query.sortBy}
                        onChange={e => setQuery(q => ({ ...q, sortBy: e.target.value }))}
                        disabled={!!activeDerived}
                      >
                        {targetMetrics.map(m => <option key={m} value={m}>{METRIC_LABELS[m]?.label || m}</option>)}
                      </select>
                    </div>
                    <div>
                      <Label>Direction</Label>
                      <div className="flex gap-1 mt-1">
                        {['desc','asc'].map(d => (
                          <button key={d} onClick={() => setQuery(q => ({ ...q, sortDir: d }))}
                            disabled={!!activeDerived}
                            className={`px-2.5 py-1.5 font-mono text-[10px] tracking-wide2 rounded border transition ${query.sortDir === d ? 'text-pb-text bg-pb-surface2 border-pb-hairline2' : 'text-pb-faint border-pb-hairline hover:border-pb-hairline2'} ${activeDerived ? 'opacity-50 cursor-not-allowed' : ''}`}>
                            {d === 'desc' ? '↓' : '↑'}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div>
                      <Label>Limit</Label>
                      <select className={selectCls + ' mt-1 w-24'} value={query.limit} onChange={e => setQuery(q => ({ ...q, limit: Number(e.target.value) }))}>
                        {[25, 50, 100, 200, 500].map(n => <option key={n} value={n}>Top {n}</option>)}
                      </select>
                    </div>
                  </div>

                  {/* Filter bar — categorised picker, nested AND/OR */}
                  <div className={filterCount > 0 ? 'ring-1 ring-pb-accent/40 rounded-md' : ''}>
                    <FilterBar
                      tree={query.filterTree}
                      categories={categoriesForTarget(targetMetrics)}
                      onChange={(tree) => setQuery(q => ({ ...q, filterTree: tree }))}
                      onClear={() => setQuery(q => ({ ...q, filterTree: emptyTree() }))}
                    />
                  </div>

                  {/* Context filters */}
                  <div>
                    <Label>
                      Context
                      {contextCount > 0 && <ActiveDot />}
                    </Label>
                    <div className={`mt-1 p-3 pb-card ${contextCount > 0 ? 'border-pb-accent/40' : ''}`}>
                      <ContextFiltersPanel
                        ctx={query.context || {}}
                        onChange={ctx => setQuery(q => ({ ...q, context: ctx }))}
                        seasons={seasons}
                        grades={grades}
                        targetShape={targetMeta.shape}
                        target={query.target}
                        activeDerived={activeDerived}
                        orgId={orgId}
                      />
                    </div>
                  </div>

                  {/* Action buttons */}
                  <div className="flex gap-2">
                    <Btn primary onClick={() => runQuery()} className="flex-1" disabled={loading}>
                      {loading ? 'Running…' : 'Run query →'}
                    </Btn>
                    <Btn onClick={resetAll}>Reset</Btn>
                    {canSave && hasQueried && rows.length > 0 && (
                      <Btn onClick={() => { setEditingReport(null); setSaveOpen(true) }}>Save…</Btn>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Save flash — surfaces approval-pending notice or save confirmation */}
            {saveFlash && (
              <div
                className={`pb-card p-3 ${saveFlash.kind === 'pending' ? 'border-pb-accent/40' : ''}`}
                style={saveFlash.kind === 'pending' ? { borderColor: 'color-mix(in srgb, var(--pb-accent) 40%, transparent)' } : undefined}
              >
                <div className="flex items-start gap-2">
                  <span
                    className="font-mono text-[10px] tracking-wide3 px-1.5 py-0.5 rounded mt-0.5"
                    style={{ background: 'color-mix(in srgb, var(--pb-accent) 18%, transparent)', color: 'var(--pb-accent)' }}
                  >
                    {saveFlash.kind === 'pending' ? 'PENDING' : 'SAVED'}
                  </span>
                  <p className="text-pb-text text-sm flex-1">{saveFlash.message}</p>
                  <button
                    onClick={() => setSaveFlash(null)}
                    className="text-pb-faint hover:text-pb-text font-mono text-base leading-none px-1"
                  >×</button>
                </div>
              </div>
            )}

            {/* Results */}
            {!hasQueried && !loading && (
              <div className="pb-card p-8 flex flex-col items-center justify-center text-center gap-3" style={{ minHeight: 320 }}>
                <Label>READY</Label>
                <p className="text-pb-dim text-[15px]">
                  Pick a report from the <span className="text-pb-text font-semibold">REPORTS</span> panel
                  {' '}<span className="hidden xl:inline">on the left</span><span className="xl:hidden">above</span>,
                  {' '}then open <span className="text-pb-text font-semibold">Customise Query</span> to tweak its sort, filters or context.
                </p>
              </div>
            )}

            {loading && <PbSpinner message="Querying…" />}

            {error && <p className="text-pb-red text-sm py-4">{error}</p>}

            {hasQueried && !loading && !error && sortedRows.length === 0 && (
              <div className="pb-card p-8 text-center">
                <p className="text-pb-faint">No results match your filters.</p>
              </div>
            )}

            {sortedRows.length > 0 && (
              <div className="pb-card">
                <div className="flex items-center justify-between gap-3 px-5 sm:px-6 py-3.5 pb-hairline-b">
                  <div className="flex items-center gap-3 min-w-0">
                    <Label>
                      {`${sortedRows.length} ${activeDerived ? 'PLAYERS' : (targetMeta.shape === 'list' ? 'ROWS' : 'GROUPS')}${activeDerived ? ' · ' + schema.derived[activeDerived].label.toUpperCase() : ''}`}
                    </Label>
                    {(currentPage > 1 || hasMore) && (
                      <span className="font-mono text-[10px] text-pb-faintest">PAGE {currentPage}{hasMore ? '' : ' · END'}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-2xs tracking-wide2 text-pb-faintest hidden sm:inline">
                      {activeDerived
                        ? ''
                        : `SORTED BY ${(METRIC_LABELS[query.sortBy]?.label || query.sortBy).toUpperCase()} ${query.sortDir === 'asc' ? '↑' : '↓'}`}
                    </span>
                    {canSave && (
                      <Btn primary onClick={() => { setEditingReport(null); setSaveOpen(true) }}>
                        Save report
                      </Btn>
                    )}
                    <button onClick={downloadCSV} className="font-mono text-[10.5px] tracking-wide2 text-pb-faint hover:text-pb-text px-2 py-1 rounded border border-pb-hairline hover:border-pb-hairline2 transition">
                      CSV
                    </button>
                  </div>
                </div>
                <ResultsTable
                  rows={sortedRows}
                  columns={tableColumns}
                  target={query.target}
                  activeDerived={activeDerived}
                  clientSort={clientSort}
                  onSort={handleColSort}
                  sortBy={query.sortBy}
                  clubSlug={clubSlug}
                  rowOffset={(currentPage - 1) * query.limit}
                />
                {(currentPage > 1 || hasMore) && (
                  <div className="flex items-center justify-center gap-2 px-5 py-3 pb-hairline-t">
                    <button
                      onClick={() => changePage(currentPage - 1)}
                      disabled={currentPage <= 1 || loading}
                      className="font-mono text-[10.5px] tracking-wide2 px-3 py-1.5 rounded border border-pb-hairline hover:border-pb-hairline2 text-pb-faint hover:text-pb-text transition disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                      ← Prev
                    </button>
                    <span className="font-mono text-[10.5px] text-pb-faint px-2">Page {currentPage}</span>
                    <button
                      onClick={() => changePage(currentPage + 1)}
                      disabled={!hasMore || loading}
                      className="font-mono text-[10.5px] tracking-wide2 px-3 py-1.5 rounded border border-pb-hairline hover:border-pb-hairline2 text-pb-faint hover:text-pb-text transition disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                      Next →
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </main>

      <SaveReportModal
        open={saveOpen}
        onClose={() => { setSaveOpen(false); setEditingReport(null) }}
        onSave={saveReport}
        defaultTitle={defaultTitleFor(query, activeDerived, schema)}
        initial={editingReport}
      />
    </div>
  )
}

// ─── Results table ────────────────────────────────────────────────────────────

function entityHeader(target, activeDerived) {
  if (activeDerived && PAIR_DERIVED.has(activeDerived)) {
    return [{ key: 'pair', label: 'PAIR' }]
  }
  switch (target) {
    case 'player_career':
      return [{ key: 'player_name', label: 'PLAYER' }]
    case 'player_season':
      return [{ key: 'player_name', label: 'PLAYER' }, { key: 'season_name', label: 'SEASON' }]
    case 'player_grade':
      return [{ key: 'player_name', label: 'PLAYER' }, { key: 'display_grade_name', label: 'GRADE' }]
    case 'family_career':
      return [{ key: 'family_name', label: 'FAMILY' }, { key: 'members', label: 'MEMBERS' }]
    case 'family_season':
      return [{ key: 'family_name', label: 'FAMILY' }, { key: 'season_name', label: 'SEASON' }, { key: 'members', label: 'MEMBERS' }]
    case 'family_grade':
      return [{ key: 'family_name', label: 'FAMILY' }, { key: 'display_grade_name', label: 'GRADE' }, { key: 'members', label: 'MEMBERS' }]
    case 'innings_list':
      return [
        { key: 'player_name', label: 'PLAYER' },
        { key: 'opposition',  label: 'VS' },
        { key: 'grade_name',  label: 'GRADE' },
        { key: 'played_at',   label: 'DATE' },
        { key: 'dismissal_type', label: 'OUT' },
      ]
    case 'spell_list':
      return [
        { key: 'player_name', label: 'PLAYER' },
        { key: 'opposition',  label: 'VS' },
        { key: 'grade_name',  label: 'GRADE' },
        { key: 'played_at',   label: 'DATE' },
      ]
    case 'match_list':
      return [
        { key: 'opposition', label: 'VS' },
        { key: 'grade_name', label: 'GRADE' },
        { key: 'played_at',  label: 'DATE' },
        { key: 'result',     label: 'RESULT' },
      ]
    case 'partnership_list':
      return [
        { key: 'pair',       label: 'PAIR' },
        { key: 'opposition', label: 'VS' },
        { key: 'grade_name', label: 'GRADE' },
        { key: 'played_at',  label: 'DATE' },
      ]
    default:
      return [{ key: 'player_name', label: 'NAME' }]
  }
}

function ResultsTable({ rows, columns, target, activeDerived, clientSort, onSort, sortBy, clubSlug, rowOffset = 0 }) {
  const dimCols = activeDerived
    ? (PAIR_DERIVED.has(activeDerived)
        ? [{ key: 'pair', label: 'PAIR' }]
        : [{ key: 'player_name', label: 'PLAYER' }])
    : entityHeader(target, null)
  return (
    <div className="overflow-x-auto pb-scroll">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
            <th className="py-3 pl-5 w-8">#</th>
            {dimCols.map(dc => (
              <th key={dc.key} className="py-3 font-medium pr-3">{dc.label}</th>
            ))}
            {columns.map(col => (
              <th key={col.key} onClick={() => onSort(col.key)}
                className="py-3 text-right font-medium cursor-pointer hover:text-pb-text pr-3 select-none"
                style={{ color: (clientSort.col === col.key || sortBy === col.key) ? 'var(--pb-accent)' : undefined }}
              >
                {col.short || col.label}{clientSort.col === col.key ? (clientSort.dir === 'asc' ? ' ↑' : ' ↓') : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
              <td className="py-2.5 pl-5 font-mono text-pb-faintest">{rowOffset + i + 1}</td>
              {dimCols.map(dc => (
                <td key={dc.key} className="py-2.5 pr-3 font-medium text-pb-text">
                  {renderDimCell(dc.key, row, clubSlug)}
                </td>
              ))}
              {columns.map(col => (
                <td key={col.key} className="py-2.5 pr-3 text-right">
                  <span className={`font-mono pb-num ${(clientSort.col === col.key || (sortBy === col.key && !clientSort.col)) ? 'font-bold' : ''}`}
                        style={{ color: (clientSort.col === col.key || (sortBy === col.key && !clientSort.col)) ? 'var(--pb-accent)' : 'var(--pb-text)' }}>
                    {formatCell(row[col.key], col)}
                  </span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function formatCell(v, col) {
  if (v == null || v === '') return '—'
  // Overs are stored as Numeric(5,1) — display X.Y where Y is 0-5 (balls).
  // Use 1 decimal place; never round to .6 etc. (the DB already enforces 0-5).
  if (col?.kind === 'overs' || col?.key === 'overs') {
    const n = Number(v)
    return isFinite(n) ? n.toFixed(1) : v
  }
  if (col?.decimal) return Number(v).toFixed(2)
  if (col?.key === 'played_at' && typeof v === 'string') {
    try { return new Date(v).toISOString().slice(0, 10) } catch { return v }
  }
  return v
}

function renderDimCell(key, row, clubSlug) {
  if (key === 'pair') {
    const a = row.player_a_name || row.batter1_name
    const b = row.player_b_name || row.batter2_name
    const aId = row.player_a_id || row.batter1_id
    const bId = row.player_b_id || row.batter2_id
    return (
      <span>
        {aId ? <Link to={`/players/${aId}`} className="text-pb-text hover:text-pb-accent">{a}</Link> : a}
        <span className="text-pb-faintest"> & </span>
        {bId ? <Link to={`/players/${bId}`} className="text-pb-text hover:text-pb-accent">{b}</Link> : b}
      </span>
    )
  }
  if (key === 'player_name' && row.player_id) {
    return <Link to={`/players/${row.player_id}`} className="text-pb-text hover:text-pb-accent">{row.player_name || row.name}</Link>
  }
  if (key === 'family_name') {
    return <span className="text-pb-text">{row.family_name || '—'}</span>
  }
  if (key === 'members') {
    return <span className="text-pb-faint text-xs">{row.members || '—'}</span>
  }
  if (key === 'result') {
    const r = row.result
    if (r === 'won') return <span className="text-pb-green">Won</span>
    if (r === 'lost') return <span className="text-pb-red">Lost</span>
    return <span className="text-pb-dim">{r || '—'}</span>
  }
  if (key === 'played_at' && row.played_at) {
    try { return new Date(row.played_at).toISOString().slice(0, 10) } catch { return row.played_at }
  }
  return row[key] || '—'
}

// Small inline indicator placed next to a section label when the user has
// changed it from the preset's defaults. Keeps the customise drawer scannable.
function ActiveDot() {
  return (
    <span
      className="inline-block w-1.5 h-1.5 rounded-full ml-1.5 align-middle"
      style={{ background: 'var(--pb-accent)' }}
      title="Active — modified from the report's defaults"
    />
  )
}

function countActiveContext(ctx) {
  if (!ctx || typeof ctx !== 'object') return 0
  return Object.entries(ctx).filter(([, v]) => {
    if (v === '' || v == null || v === false) return false
    if (Array.isArray(v)) return v.length > 0
    return true
  }).length
}

function defaultTitleFor(q, activeDerived, schema) {
  if (activeDerived && schema?.derived?.[activeDerived]) return schema.derived[activeDerived].label
  const t = TARGETS.find(x => x.key === q.target)?.label || 'Query'
  const sb = METRIC_LABELS[q.sortBy]?.label || q.sortBy
  return `${t} — ${sb}`
}
