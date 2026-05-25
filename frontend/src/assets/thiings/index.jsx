import trophy from './trophy.png'
import goldMedal from './gold-medal.png'
import necktie from './necktie.png'
import cricketBat from './cricket-bat.png'
import ribbon from './ribbon.png'
import locationPin from './location-pin.png'
import lightningBolt from './lightning-bolt.png'
import calendar from './calendar.png'
import handshake from './handshake.png'
import barChart from './bar-chart.png'
import target from './target.png'
import star from './star.png'

export const thiings = {
  trophy,
  goldMedal,
  necktie,
  cricketBat,
  ribbon,
  locationPin,
  lightningBolt,
  calendar,
  handshake,
  barChart,
  target,
  star,
}

export const CATEGORY_ICON_SRC = {
  'Club Award': trophy,
  'Association Award': goldMedal,
  'Office Bearer': necktie,
  'Premiership': cricketBat,
  'Hall of Fame': star,
  'Life Membership': ribbon,
  'Milestone': locationPin,
}

export const MILESTONE_ICON_SRC = {
  runs: cricketBat,
  wickets: lightningBolt,
  matches: calendar,
  catches: handshake,
  grade_matches: target,
}

export function ThiingIcon({ src, alt = '', className = 'w-5 h-5', ...rest }) {
  if (!src) return null
  return <img src={src} alt={alt} className={`inline-block object-contain ${className}`} {...rest} />
}
