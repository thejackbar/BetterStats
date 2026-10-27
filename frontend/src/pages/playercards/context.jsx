// What every screen of the Player Cards page shares: who is signed in, the club's look, the player's cards and packs
// (read once and kept current), the swap count for the badge, and the pack opening that any screen can start. The
// overlays for opening packs live in the shell, so a pack can be opened from Home or from Packs without moving.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from '../../lib/api'
import { useClubSponsors } from '../../lib/useClubSponsors'
import { cardSponsor } from '../../components/PlayerTradingCard'
import { useCardStyle } from '../../components/cards/useCardStyle'

const Ctx = createContext(null)
export const usePC = () => useContext(Ctx)

export function PlayerCardsProvider({ token, club, me, onSwitch, children }) {
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)
  const [swapsWaiting, setSwapsWaiting] = useState(0)
  const [wants, setWants] = useState({ keys: new Set(), ready: 0, count: 0 })
  const [pack, setPack] = useState(null)
  const [owned, setOwned] = useState(() => new Set())
  const [allResult, setAllResult] = useState(null)
  const [busyAll, setBusyAll] = useState(false)
  const [packErr, setPackErr] = useState('')
  const { accent, display } = useCardStyle(club)
  const sponsor = cardSponsor(useClubSponsors(club?.slug), 'player_cards')
  const base = `/playerdash/${token}`
  const basePath = `${base}/cards`

  const load = useCallback(() => api.availPublicCards(token).then((d) => { setData(d); setFailed(false); return d }).catch(() => setFailed(true)), [token])
  const loadSwaps = useCallback(() => api.availPublicSwaps(token).then((b) => setSwapsWaiting(b.incoming.length)).catch(() => {}), [token])
  // The wish list: which cards are on it (for the add and remove buttons) and how many someone could swap now (for the badge).
  const loadWants = useCallback(() => api.availPublicWants(token)
    .then((w) => setWants({ keys: new Set(w.wants.map((x) => x.key)), ready: w.ready, count: w.wants.length })).catch(() => {}), [token])
  const toggleWant = useCallback(async (card) => {
    const on = wants.keys.has(card.key)
    if (on) await api.availPublicRemoveWant(token, card.key); else await api.availPublicAddWant(token, card.key)
    await loadWants()
  }, [token, wants, loadWants])
  useEffect(() => { load(); loadSwaps(); loadWants() }, [load, loadSwaps, loadWants])

  const mine = useMemo(() => data?.cards.find((c) => c.mine) || null, [data])

  const startPack = useCallback((p) => {
    setOwned(new Set((data?.cards || []).map((c) => c.key)))
    setPack(p)
  }, [data])
  const closePack = useCallback(() => { setPack(null); load() }, [load])
  const nextPack = useCallback(async () => {
    // The pack that was just opened is gone; read the list again and go straight on to the next.
    const d = await api.availPublicCards(token)
    setData(d)
    setOwned(new Set(d.cards.map((c) => c.key)))
    setPack(d.packs[0] || null)
  }, [token])
  const openAll = useCallback(async () => {
    setBusyAll(true); setPackErr('')
    try {
      setAllResult(await api.availPublicOpenAllCards(token))
    } catch (e) {
      setPackErr(e?.message || 'Could not open the packs. Try again.')
    } finally {
      setBusyAll(false)
      load()
    }
  }, [token, load])

  const value = {
    token, club, me, onSwitch, accent, display, sponsor, base, basePath,
    data, failed, load, mine, swapsWaiting, loadSwaps, wants, loadWants, toggleWant,
    pack, owned, startPack, closePack, nextPack, allResult, setAllResult, busyAll, openAll, packErr,
    packsCount: data?.packs?.length || 0,
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
