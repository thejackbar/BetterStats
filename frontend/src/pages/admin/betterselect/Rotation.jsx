// BetterSelect → Junior Rotation (the list of groups).
//
// A coach saves a group of kids by name and gets a fair batting order and
// fielding rotation every game. Groups are typed names, never rows from the
// club's player list: a tee ball side is often not on Cricket Australia at all.
import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { PbSpinner } from '../../../lib/presskit'
import { Icon, Btn, Segmented, Empty } from './ui'
import { formatRoundDate } from './rotation/LineupSheet'

export const ROTATION_URL = '/admin/betterselect/rotation'

const FIELD = 'w-full bg-pb-surface2 border border-pb-hairline rounded-lg px-3 text-sm text-pb-text placeholder:text-pb-faint focus:outline-none focus:border-pb-accent'
const LABEL = 'block font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest mb-1'

function CreateGroup({ presets, onCreated }) {
  const toast = useToast()
  const [name, setName] = useState('')
  const [preset, setPreset] = useState('tee_ball')
  const [names, setNames] = useState('')
  const [busy, setBusy] = useState(false)
  const chosen = presets.find((p) => p.key === preset)

  const create = async () => {
    if (!name.trim()) { toast.error('Give the group a name.'); return }
    setBusy(true)
    try {
      const r = await api.rotCreateGroup({ name: name.trim(), preset, names })
      onCreated(r.group.id)
    } catch (e) { toast.error(e.message); setBusy(false) }
  }

  return (
    <div className="pb-card px-4 py-4 flex flex-col gap-4" data-create-group>
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <label className={LABEL} htmlFor="rot-name">Group name</label>
          <input id="rot-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Under 8 Tee Ball"
            className={`${FIELD} h-[38px]`} />
        </div>
        <div>
          <span className={LABEL}>Field positions to start with</span>
          <Segmented sm value={preset} onChange={setPreset}
            options={presets.map((p) => ({ value: p.key, label: p.label }))} />
          <p className="text-[12px] text-pb-faint mt-1.5" data-preset-note>
            {chosen && chosen.positions.length
              ? `${chosen.positions.length} positions: ${chosen.positions.map((p) => p.name).join(', ')}. You can change them any time.`
              : 'You will add your own positions after the group is made.'}
          </p>
        </div>
      </div>
      <div>
        <label className={LABEL} htmlFor="rot-names">Your kids (one name a line, or separated by commas)</label>
        <textarea id="rot-names" rows={5} value={names} onChange={(e) => setNames(e.target.value)}
          placeholder={'Sam Taylor\nAva Brown\nNoah Smith'}
          className={`${FIELD} py-2 resize-y`} />
        <p className="text-[12px] text-pb-faint mt-1">Names are saved with the group, so you only type them once. Add or remove kids later.</p>
      </div>
      <div><Btn variant="primary" icon="plus" onClick={create} disabled={busy}>{busy ? 'Creating…' : 'Create group'}</Btn></div>
    </div>
  )
}

export default function Rotation() {
  const { canEditCap } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const canEdit = canEditCap(CAP.SELECT_ROTATION, CAP.MANAGE_SELECTIONS)
  const [groups, setGroups] = useState(null)
  const [presets, setPresets] = useState([])
  const [archived, setArchived] = useState(false)
  const [creating, setCreating] = useState(false)

  const load = useCallback(() => {
    api.rotListGroups(archived).then((r) => setGroups(r.groups || [])).catch((e) => { toast.error(e.message); setGroups([]) })
  }, [archived, toast])
  useEffect(() => { setGroups(null); load() }, [load])
  useEffect(() => { api.rotPresets().then((r) => setPresets(r.presets || [])).catch(() => {}) }, [])

  return (
    <BetterSelectLayout title="Junior Rotation"
      caption="Fair batting and fielding"
      actions={canEdit && !archived ? <Btn variant="primary" sm icon="plus" onClick={() => setCreating((v) => !v)}>New group</Btn> : null}>
      <div className="flex flex-col gap-4">
        {creating && canEdit && presets.length > 0 && (
          <CreateGroup presets={presets} onCreated={(id) => navigate(`${ROTATION_URL}/${id}`)} />
        )}
        {groups === null ? <PbSpinner message="Loading groups…" /> : (
          <div className="pb-card divide-y divide-pb-hairline" data-groups>
            {groups.length === 0 ? (
              <Empty className="px-4 py-10 text-center">
                {archived
                  ? 'No archived groups.'
                  : 'No groups yet. Make one for your tee ball or junior side, paste in the kids, and it will shuffle the batting order and fielding positions fairly every week.'}
              </Empty>
            ) : groups.map((g) => (
              <div key={g.id} role="button" tabIndex={0} data-group={g.name}
                onClick={() => navigate(`${ROTATION_URL}/${g.id}`)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`${ROTATION_URL}/${g.id}`) } }}
                className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-pb-surface2/50 transition-colors">
                <span className="w-9 h-9 rounded-lg bg-pb-accent/12 text-pb-accent flex items-center justify-center shrink-0"><Icon name="rotation" size={18} /></span>
                <div className="flex-1 min-w-0">
                  <div className="font-display font-semibold text-[14.5px] truncate">{g.name}</div>
                  <div className="text-[12px] text-pb-faint">
                    {g.player_count} {g.player_count === 1 ? 'kid' : 'kids'} · {g.positions.length} positions
                    {g.locked_rounds > 0 ? ` · ${g.locked_rounds} ${g.locked_rounds === 1 ? 'game' : 'games'} locked, last ${formatRoundDate(g.last_round)}` : ' · no games locked yet'}
                  </div>
                </div>
                <Icon name="chevron" size={15} className="text-pb-faint shrink-0" />
              </div>
            ))}
          </div>
        )}
        <div>
          <button type="button" className="text-[12.5px] text-pb-faint underline" onClick={() => setArchived((v) => !v)}>
            {archived ? 'Back to current groups' : 'Show archived groups'}
          </button>
        </div>
      </div>
    </BetterSelectLayout>
  )
}
