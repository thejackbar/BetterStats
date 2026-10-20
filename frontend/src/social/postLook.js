// How a post sits on the background the club picked.
//
// A layout paints its own opaque fill and its own dots, stripes and grain on top
// of whatever background is behind it. With a club's own photo behind it that
// reads as a veil: the photo is dimmed and the layout's texture is drawn over
// it. Two settings give that back to the club, and both go through this one
// context so the ~48 layouts need no change of their own:
//
//   veil    the alpha of the layout's own fill over the background, as two hex
//           digits ('99' is the 60% every layout has always had). null means
//           leave the layout's fill exactly as it draws it.
//   texture false hides Halftone, Stripes and the grain (see cricket-templates).
//
// With no provider (the football build, the export of a design with neither set)
// both read as "untouched", so nothing that was drawn before moves.
import { createContext, useContext } from 'react'

export const DEFAULT_VEIL = '99'

export const PostLookContext = createContext({ veil: null, texture: true })

export function usePostLook() {
  return useContext(PostLookContext) || { veil: null, texture: true }
}

// 0..1 to the two hex digits that follow a #rrggbb.
export function alphaHex(fraction) {
  const n = Math.max(0, Math.min(255, Math.round(Number(fraction) * 255)))
  return n.toString(16).padStart(2, '0')
}

// The editor gives every layout a palette whose `primary` carries the default
// veil (#rrggbb99), so a layout's root fill arrives as `#rrggbb99`, alone or
// inside a gradient. Swap that alpha for the club's own. Anything that does not
// carry the default veil (a plain colour, a layout drawing a different fill)
// is returned as it came.
export function veilBackground(value, veil) {
  if (veil == null || veil === DEFAULT_VEIL || typeof value !== 'string') return value
  return value.replace(/(#[0-9a-fA-F]{6})99(?![0-9a-fA-F])/g, `$1${veil}`)
}

export function veilStyle(style, veil) {
  if (!style || veil == null || veil === DEFAULT_VEIL) return style
  const next = { ...style }
  if (next.background !== undefined) next.background = veilBackground(next.background, veil)
  if (next.backgroundColor !== undefined) next.backgroundColor = veilBackground(next.backgroundColor, veil)
  return next
}
