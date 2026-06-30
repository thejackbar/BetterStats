import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

const ACTION_LABELS = {
  merge_players: 'Merged players',
  undo_merge_players: 'Undid player merge',
  merge_grades: 'Merged grades',
  undo_merge_grades: 'Undid grade merge',
  merge_seasons: 'Merged seasons',
  undo_merge_seasons: 'Undid season merge',
  patch_settings: 'Updated club settings',
  player_profile_import: 'Imported player details',
}

const ACTION_COLOURS = {
  merge_players: 'var(--pb-accent)',
  merge_grades: 'var(--pb-accent)',
  merge_seasons: 'var(--pb-accent)',
  undo_merge_players: 'var(--pb-amber, #f59e0b)',
  undo_merge_grades: 'var(--pb-amber, #f59e0b)',
  undo_merge_seasons: 'var(--pb-amber, #f59e0b)',
  patch_settings: 'var(--pb-dim)',
  player_profile_import: 'var(--pb-accent)',
}

function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('en-AU', {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: 'numeric', minute: '2-digit',
  })
}

function DetailLine({ entry }) {
  const d = entry.details || {}
  switch (entry.action) {
    case 'merge_players':
      return (
        <>
          <span className="text-pb-text">{d.removed_player?.name}</span>
          <span className="text-pb-faint mx-2">→</span>
          <span className="text-pb-text">{d.kept_player?.name}</span>
          {d.rows_moved && (
            <span className="font-mono text-[10px] text-pb-faintest ml-3">
              {d.rows_moved.batting || 0}b · {d.rows_moved.bowling || 0}bw · {d.rows_moved.fielding || 0}f
            </span>
          )}
        </>
      )
    case 'undo_merge_players':
      return (
        <>
          <span className="text-pb-text">{d.restored_player?.name}</span>
          <span className="text-pb-faint mx-2">restored from</span>
          <span className="text-pb-text">{d.kept_player?.name}</span>
        </>
      )
    case 'merge_grades':
      return (
        <>
          <span className="text-pb-text">{d.alias_name}</span>
          <span className="text-pb-faint mx-2">→</span>
          <span className="text-pb-text">{d.canonical_name}</span>
        </>
      )
    case 'merge_seasons':
      return <span className="text-pb-dim font-mono text-[11px]">canonical {(d.canonical_season_id || '').slice(0, 8)}… ← {(d.alias_season_id || '').slice(0, 8)}…</span>
    case 'patch_settings':
      return (
        <span className="text-pb-dim text-sm">
          Changed: {(d.changed_fields || []).join(', ') || '(no fields)'}
        </span>
      )
    case 'player_profile_import':
      return (
        <span className="text-pb-dim text-sm">
          {d.updated || 0} updated{d.created ? `, ${d.created} created` : ''}
          {d.fields_written ? ` · ${d.fields_written} field${d.fields_written === 1 ? '' : 's'} set` : ''}
          {d.filename ? ` · ${d.filename}` : ''}
        </span>
      )
    default:
      return <span className="font-mono text-[11px] text-pb-faintest">{entry.target_type} {entry.target_id?.slice(0, 8)}</span>
  }
}

export default function AdminActivityLog() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filterAction, setFilterAction] = useState('')

  useEffect(() => {
    setLoading(true)
    api.adminListActivityLog(200)
      .then(setRows)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const actions = Array.from(new Set(rows.map(r => r.action))).sort()
  const filtered = filterAction ? rows.filter(r => r.action === filterAction) : rows

  return (
    <AdminLayout>
      <div className="max-w-3xl">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-2">Activity Log</h1>
        <p className="text-pb-faint text-sm mb-6 leading-relaxed">
          Append-only record of sensitive admin actions — merges, settings changes, destructive ops.
          Useful for figuring out who did what when something looks off.
        </p>

        {actions.length > 0 && (
          <div className="mb-4 flex items-center gap-2 flex-wrap">
            <button
              onClick={() => setFilterAction('')}
              className={`font-mono text-[10px] px-2.5 py-1 rounded border pb-hairline transition ${filterAction === '' ? 'bg-pb-accent text-pb-bg' : 'text-pb-faint hover:text-pb-text'}`}
            >
              All ({rows.length})
            </button>
            {actions.map(a => (
              <button
                key={a}
                onClick={() => setFilterAction(a)}
                className={`font-mono text-[10px] px-2.5 py-1 rounded border pb-hairline transition ${filterAction === a ? 'bg-pb-accent text-pb-bg' : 'text-pb-faint hover:text-pb-text'}`}
              >
                {ACTION_LABELS[a] || a} ({rows.filter(r => r.action === a).length})
              </button>
            ))}
          </div>
        )}

        {error && (
          <div className="mb-4 font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-3 py-2">{error}</div>
        )}

        {loading && (
          <div className="pb-card p-8 text-center font-mono text-[11px] text-pb-faint">Loading…</div>
        )}

        {!loading && !filtered.length && (
          <div className="pb-card p-8 text-center font-mono text-[11px] text-pb-faint">
            No activity recorded yet.
          </div>
        )}

        {!loading && filtered.length > 0 && (
          <div className="pb-card overflow-hidden">
            {filtered.map((entry, i) => (
              <div key={entry.id} className={`flex items-start gap-3 px-5 py-3 ${i > 0 ? 'pb-hairline-t' : ''}`}>
                <span
                  className="mt-1.5 w-2 h-2 rounded-full shrink-0"
                  style={{ background: ACTION_COLOURS[entry.action] || 'var(--pb-dim)' }}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-pb-text text-sm font-medium">
                      {ACTION_LABELS[entry.action] || entry.action}
                    </span>
                    <span className="font-mono text-[10px] text-pb-faintest">{fmtTime(entry.created_at)}</span>
                  </div>
                  <p className="text-xs mt-0.5">
                    <DetailLine entry={entry} />
                  </p>
                  {entry.user_email && (
                    <p className="font-mono text-[10px] text-pb-faintest mt-0.5">by {entry.user_email}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
