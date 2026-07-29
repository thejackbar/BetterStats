// Full-screen "Canva-class" editor chrome for the BetterPosts designer.
//
// Dumb layout only: header (52) / rail (74) | panel (306) | canvas well. All
// content comes in as nodes/slots so AdminSocialPost keeps every bit of state.
// The canvas well measures itself and hands its available box to `renderCanvas`
// so the post fits without the parent guessing viewport maths.
//
// Props:
//   headerLeft, headerRight   nodes for the 52px top bar
//   tool, onTool              drive the left ToolRail
//   panelTitle, panelMeta     44px panel header
//   panel                     scrolling panel body
//   renderCanvas({availW,availH}) => node   centred canvas region (page strip + post + caption)
//   inspector                 floating inspector node (positions itself)
import { useEffect, useRef, useState } from 'react'
import ToolRail from './ToolRail'

export default function PostEditorShell({
  headerLeft, headerRight, tool, onTool,
  panelTitle, panelMeta, panel, renderCanvas, inspector, tabBar,
}) {
  const wellRef = useRef(null)
  const [box, setBox] = useState({ w: 0, h: 0 })

  useEffect(() => {
    const el = wellRef.current
    if (!el) return undefined
    const ro = new ResizeObserver(() => {
      setBox({ w: el.clientWidth, h: el.clientHeight })
    })
    ro.observe(el)
    setBox({ w: el.clientWidth, h: el.clientHeight })
    return () => ro.disconnect()
  }, [])

  // The centred flex box carries 26px padding; hand back the usable interior so
  // the page strip (which sits 84px to the canvas's left) still has room.
  const pad = 26
  const availW = Math.max(0, box.w - pad * 2 - 84)
  const availH = Math.max(0, box.h - pad * 2 - 44) // leave room for the caption row

  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-pb-bg text-pb-text">
      {/* Header */}
      <header className="h-[52px] shrink-0 flex items-center gap-3.5 px-3.5 bg-pb-surface border-b pb-hairline">
        <div className="flex items-center gap-3.5 min-w-0">{headerLeft}</div>
        <div className="flex-1" />
        <div className="flex items-center gap-2.5 shrink-0">{headerRight}</div>
      </header>

      {/* Post-type bar — every type across the top */}
      {tabBar && (
        <div className="shrink-0 bg-pb-surface border-b pb-hairline overflow-x-auto">
          <div className="flex items-stretch gap-1 px-2 py-1.5 min-w-max">{tabBar}</div>
        </div>
      )}

      {/* Body */}
      <div className="flex-1 flex min-h-0">
        <ToolRail tool={tool} onTool={onTool} />

        {/* Panel */}
        <aside className="w-[306px] shrink-0 bg-pb-surface border-r pb-hairline flex flex-col min-h-0">
          <div className="h-11 shrink-0 flex items-center justify-between gap-2 px-3.5 border-b pb-hairline">
            <span className="font-mono text-[10px] tracking-wide2 uppercase text-pb-text">{panelTitle}</span>
            {panelMeta ? <span className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint">{panelMeta}</span> : null}
          </div>
          <div className="flex-1 overflow-y-auto p-3.5">{panel}</div>
        </aside>

        {/* Canvas well */}
        <main className="flex-1 relative min-w-0 overflow-hidden" style={{ background: '#07090f' }}>
          <div ref={wellRef} className="absolute inset-0 flex items-center justify-center" style={{ padding: pad }}>
            {box.w > 0 && renderCanvas({ availW, availH })}
          </div>
          {inspector}
        </main>
      </div>
    </div>
  )
}
