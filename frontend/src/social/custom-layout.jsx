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

/** The id the editor gives the imported-template layout on the Lineup tab. */
export const CUSTOM_LAYOUT_ID = 'LC1'

/**
 * One imported-template layout per post type, all drawn by the same component. The post type is the
 * tab the layout sits on, so the Data tab, the players and the type's own Content panel all stay linked.
 */
export const CUSTOM_LAYOUTS = {
  lineup: 'LC1', fixtures: 'LC2', result: 'LC3', results: 'LC4', motm: 'LC5',
  totw: 'LC6', milestones: 'LC7', announcement: 'LC8', toss: 'LC9', events: 'LC10',
}
export const CUSTOM_LAYOUT_IDS = Object.values(CUSTOM_LAYOUTS)
export const isCustomLayout = (id) => CUSTOM_LAYOUT_IDS.includes(id)
/** The Content panel a custom layout shares with the built-in layouts of its type (the toss, the spotlight, the announcement). */
export const CUSTOM_PANEL_ALIAS = { LC5: 'C3', LC8: 'C1', LC9: 'C2' }
