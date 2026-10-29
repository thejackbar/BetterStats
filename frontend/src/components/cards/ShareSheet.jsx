// Share a card: a picture of it to the phone's share sheet (or saved, where there is none), and for the player's
// OWN card a link to their public card page and a short looping GIF, either the shine passing over it or the
// card turning over to its details and back. The GIF is made on the device from the flat card, so nothing is
// uploaded anywhere and the club's own font is in it, as in the picture.
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { deliverBlob, renderNodeBlob } from '../../lib/exportNodePng'
import { makeCardGif } from '../../lib/cardGif'
import { useClubSponsors } from '../../lib/useClubSponsors'
import { NO_SPONSOR, cardSponsor, cardSponsorOptions, onColor } from '../PlayerTradingCard'
import { CARD_H, CARD_W, CardInfoBack, CardView } from './CardFaces'

const MONO = "'JetBrains Mono', monospace"
const fileName = (card) => (card.name || 'card').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') + (card.kind === 'special' ? `-${(card.title || 'special').toLowerCase().replace(/[^a-z0-9]+/g, '-')}` : '-card')
const btn = { padding: '11px 16px', borderRadius: 12, border: '1px solid rgba(255,255,255,.35)', background: 'rgba(255,255,255,.08)', color: '#fff', font: `700 11px ${MONO}`, letterSpacing: 1.2, textTransform: 'uppercase', textAlign: 'center' }

export default function ShareSheet({ card, club, accent, display, sponsor: clubSponsor, onClose }) {
  // The sponsor on the shared picture. '' follows the club's pick (the `sponsor` the card book already shows).
  const sponsorData = useClubSponsors(club?.slug)
  const sponsorOptions = cardSponsorOptions(sponsorData)
  const [sponsorChoice, setSponsorChoice] = useState('')
  const sponsor = sponsorChoice ? cardSponsor(sponsorData, 'player_cards', sponsorChoice) : clubSponsor
  const frontRef = useRef(null)
  const backRef = useRef(null)
  const [busy, setBusy] = useState('')
  const [progress, setProgress] = useState(0)
  const [note, setNote] = useState('')
  const [gif, setGif] = useState(null) // { url, blob, mode }
  const canShareFiles = typeof navigator !== 'undefined' && !!navigator.canShare
  const own = !!card.mine

  useEffect(() => () => { if (gif?.url) URL.revokeObjectURL(gif.url) }, [gif])
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const said = (r) => setNote(r === 'shared' ? 'Shared.' : r === 'saved' ? 'Saved to your downloads.' : '')
  const run = async (what, fn) => {
    setBusy(what); setNote('')
    try { await fn() } catch (e) { setNote(e?.message || 'That did not work. Try again.') } finally { setBusy(''); setProgress(0) }
  }

  const sharePicture = () => run('picture', async () => {
    const blob = await renderNodeBlob(frontRef.current, { width: CARD_W, height: CARD_H, backgroundColor: 'transparent', scale: 2 })
    said(await deliverBlob(blob, `${fileName(card)}.png`, 'image/png'))
  })
  const copyLink = () => run('link', async () => {
    const url = `${window.location.origin}/players/${card.player_id}/share${sponsorChoice ? `?sponsor=${encodeURIComponent(sponsorChoice)}` : ''}`
    await navigator.clipboard.writeText(url)
    setNote('Link copied. It opens your public card page.')
  })
  const makeGif = (mode) => run(`gif-${mode}`, async () => {
    if (gif?.url) URL.revokeObjectURL(gif.url)
    setGif(null)
    const [frontBlob, backBlob] = await Promise.all([
      renderNodeBlob(frontRef.current, { width: CARD_W, height: CARD_H, backgroundColor: 'transparent', scale: 1 }),
      mode === 'turn' ? renderNodeBlob(backRef.current, { width: CARD_W, height: CARD_H, backgroundColor: 'transparent', scale: 1 }) : null,
    ])
    const blob = await makeCardGif({ frontBlob, backBlob, mode, width: 300, onProgress: setProgress })
    setGif({ url: URL.createObjectURL(blob), blob, mode })
  })
  const sendGif = () => run('send', async () => said(await deliverBlob(gif.blob, `${fileName(card)}-${gif.mode}.gif`, 'image/gif')))

  const ui = (
    <div role="dialog" aria-modal="true" aria-label="Share this card" data-share-sheet onClick={onClose}
      style={{ position: 'fixed', inset: 0, zIndex: 90, background: 'rgba(3,6,10,.97)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16, overflowY: 'auto' }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: '100%', maxWidth: 380, display: 'flex', flexDirection: 'column', gap: 12, margin: 'auto' }}>
        <div style={{ font: `800 italic 26px ${display}`, textTransform: 'uppercase', letterSpacing: 1, textAlign: 'center' }}>Share {card.kind === 'special' ? 'this card' : own ? 'your card' : `${card.name}'s card`}</div>

        {sponsorOptions.length > 0 && (
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6, font: `600 10px ${MONO}`, letterSpacing: 1.6, textTransform: 'uppercase', opacity: 0.9 }}>
            Sponsor on the card
            <select value={sponsorChoice} onChange={(e) => { setSponsorChoice(e.target.value); setGif(null); setNote('') }} disabled={!!busy} data-share-sponsor
              style={{ padding: '10px 12px', borderRadius: 12, border: '1px solid rgba(255,255,255,.35)', background: 'rgba(255,255,255,.08)', color: '#fff', font: `600 13px ${MONO}`, textTransform: 'none', letterSpacing: 0 }}>
              <option value="" style={{ color: '#000' }}>Club's choice</option>
              {sponsorOptions.map((o) => <option key={o.id} value={o.id} style={{ color: '#000' }}>{o.name}</option>)}
              <option value={NO_SPONSOR} style={{ color: '#000' }}>No sponsor</option>
            </select>
          </label>
        )}

        <button type="button" onClick={sharePicture} disabled={!!busy} data-share-picture style={{ ...btn, background: accent, color: onColor(accent), border: 0 }}>
          {busy === 'picture' ? 'Making the picture…' : canShareFiles ? 'Share the picture' : 'Save the picture'}
        </button>
        {own && (
          <>
            <button type="button" onClick={copyLink} disabled={!!busy} data-share-link style={btn}>Copy a link to your card page</button>
            <div style={{ font: `600 10px ${MONO}`, letterSpacing: 1.6, textTransform: 'uppercase', opacity: 0.7, textAlign: 'center', marginTop: 4 }}>Moving card (GIF)</div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button type="button" onClick={() => makeGif('shine')} disabled={!!busy} data-share-gif="shine" style={{ ...btn, flex: 1 }}>The shine</button>
              <button type="button" onClick={() => makeGif('turn')} disabled={!!busy} data-share-gif="turn" style={{ ...btn, flex: 1 }}>Turning over</button>
            </div>
          </>
        )}
        {busy.startsWith('gif') && (
          <div role="status" data-gif-progress style={{ textAlign: 'center', font: `600 11px ${MONO}`, letterSpacing: 1.2, textTransform: 'uppercase' }}>
            Making your GIF… {Math.round(progress * 100)}%
            <div style={{ height: 5, borderRadius: 3, background: 'rgba(255,255,255,.2)', marginTop: 6, overflow: 'hidden' }}><div style={{ width: `${progress * 100}%`, height: '100%', background: accent }} /></div>
          </div>
        )}
        {gif && (
          <div data-gif-ready style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
            <img src={gif.url} alt={`A moving picture of the card: ${gif.mode === 'shine' ? 'the shine' : 'turning over'}`} data-gif-preview style={{ width: 200, borderRadius: 14, background: 'rgba(255,255,255,.06)' }} />
            <button type="button" onClick={sendGif} disabled={!!busy} data-gif-send style={{ ...btn, width: '100%', background: accent, color: onColor(accent), border: 0 }}>{canShareFiles ? 'Share the GIF' : 'Save the GIF'}</button>
          </div>
        )}
        {note && <div role="status" data-share-note style={{ textAlign: 'center', fontSize: 13, opacity: 0.9 }}>{note}</div>}
        <button type="button" onClick={onClose} data-share-close style={{ ...btn, border: 0, background: 'none', textDecoration: 'underline', opacity: 0.8 }}>Close</button>
      </div>

      {/* Flat copies at the design size, off screen, that the picture and the GIF are made from. */}
      <div aria-hidden style={{ position: 'fixed', left: -10000, top: 0, pointerEvents: 'none' }}>
        <div ref={frontRef} style={{ width: CARD_W, height: CARD_H }}><CardView card={card} club={club} accent={accent} display={display} sponsor={sponsor} holo={false} /></div>
        <div ref={backRef} style={{ width: CARD_W, height: CARD_H }}><CardInfoBack card={card} club={club} accent={accent} display={display} /></div>
      </div>
    </div>
  )
  return createPortal(ui, document.body)
}
