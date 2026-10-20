// "Import a Canva template": paste the text the BetterCricket Canva app copied, and
// the editor builds the post from it. One box, used wherever an import can start
// (the Blank canvas and the Lineup design tab), so the wording and the choices are
// the same in both. The file itself says where it goes: a line up goes to Lineup,
// anything else to the Blank canvas.
//
// Props:
//   clubStyle, onClubStyle(bool)   use the club's own colours and fonts (ticked by default)
//   onImport(text)                 async; the editor reads the text and does the import
//   busy                           an import or upload is under way
//   hint                           optional line saying where this import will land
//
// The text lives here (it is a draft, not editor state) and is cleared after an
// import the editor accepted: `onImport` resolves true for that.
import { useState } from 'react'

export default function CanvaImportBox({ clubStyle, onClubStyle, onImport, busy = false, hint = null }) {
  const [text, setText] = useState('')
  const go = async () => {
    const accepted = await onImport(text)
    if (accepted) setText('')
  }
  return (
    <div className="flex flex-col gap-2" data-testid="canva-import">
      <div className="font-mono text-[9px] text-pb-faintest uppercase tracking-wide2">Import a Canva template</div>
      <p className="text-[11px] text-pb-dim leading-relaxed">
        In the BetterCricket Canva app press <span className="text-pb-text">Copy template text</span>, then paste it here.
        {hint ? ` ${hint}` : ''}
      </p>
      <label className="flex items-start gap-2 text-[11px] text-pb-dim leading-relaxed cursor-pointer" data-testid="club-style">
        <input type="checkbox" checked={clubStyle} onChange={(e) => onClubStyle(e.target.checked)} className="mt-0.5" data-testid="club-style-input" />
        <span>Use my club's colours and fonts <span className="text-pb-faintest">(recommended). Untick to keep the colours and fonts from Canva.</span></span>
      </label>
      <textarea value={text} onChange={(e) => setText(e.target.value)} data-testid="template-paste" rows={4}
        placeholder="Paste what the Canva app copied here"
        className="w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-[11px] font-mono text-pb-text placeholder:text-pb-faintest" />
      <div>
        <button onClick={go} disabled={busy || !text.trim()} data-testid="template-paste-import"
          className="px-3 py-1.5 rounded text-[11px] font-mono border pb-hairline text-pb-text hover:border-pb-text transition-colors disabled:opacity-50">
          {busy ? 'Importing…' : 'Import pasted text'}
        </button>
      </div>
    </div>
  )
}
CanvaImportBox.displayName = 'CanvaImportBox'
