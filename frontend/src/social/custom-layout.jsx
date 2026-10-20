// "Your template": the layout a Canva template becomes on the Lineup post type.
//
// The layout itself draws almost nothing, only the club's background and the
// platform credit. Everything the template brought (the fixed words, the panels,
// the player places, the opponent, the date) is a block on top of it, drawn
// INSIDE this root by the one layer stack like any other layout's extras. That is
// what lets it sit under Lineup with the rest: the Data tab pulls the XI from
// BetterSelect or Play-Cricket, and the blocks fill from the players, the opponent
// and the match details the editor already holds.
//
// There is no sponsor entry in SPONSOR_SLOTS on purpose: a template draws its own
// design, so the sponsor grid takes the generic bottom band and the club moves or
// removes it like any block.
import { LayerRoot } from './postLayers'
import { CreditMark } from './cricket-templates'

export function CustomLayout({ width = 1080, height = 1080, palette }) {
  return (
    <LayerRoot style={{
      width, height, position: 'relative', overflow: 'hidden',
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <div data-layer="Platform credit" style={{ position: 'absolute', right: 36, bottom: 30, pointerEvents: 'none' }}>
        <CreditMark ink={palette.ink} h={44} />
      </div>
    </LayerRoot>
  )
}
CustomLayout.displayName = 'CustomLayout'

/** The id the editor gives the imported-template layout. */
export const CUSTOM_LAYOUT_ID = 'LC1'
