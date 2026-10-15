// The two small pure pieces of the Selection board's draft handling, shared by
// the board and the draft table.

// What Confirm would write: the named XI in batting order, captain, keeper and
// the call-up cascades. Gaps between slots are not part of it.
export const confirmSig = (filled, capId, wkId, demoList) =>
  JSON.stringify([filled.map((id) => [id, id === capId, id === wkId]), demoList])

// A saved draft laid back onto the board. Anyone no longer in the pool is
// dropped; the server re-judges everything at Confirm.
export function restoreDraft(dd, pool, size) {
  const inPool = new Set((pool || []).map((p) => p.id))
  let slots = (dd.slots || []).map((id) => (id && inPool.has(id) ? id : null))
  if (size === 0) slots = slots.filter(Boolean)
  else {
    while (slots.length > size && slots[slots.length - 1] == null) slots.pop()
    while (slots.length < size) slots.push(null)
  }
  const kept = new Set(slots.filter(Boolean))
  const demo = {}
  ;(dd.demotions || []).forEach((x) => {
    if (x.callup_id && kept.has(x.callup_id)) demo[x.player_id] = { fixture_id: x.fixture_id, batting_order: x.batting_order, callupId: x.callup_id }
  })
  return {
    slots,
    cap: kept.has(dd.captain_id) ? dd.captain_id : null,
    wk: kept.has(dd.wicket_keeper_id) ? dd.wicket_keeper_id : null,
    demo,
  }
}

