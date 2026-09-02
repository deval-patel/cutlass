import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { jsonFetch } from '../../lib/api'
import { useRedraft } from './queries'
import type { Asset } from '../../types'

interface StylePanelProps {
  asset: Asset
  disabled?: boolean
}

interface PresetCard {
  preset_id: string
  name: string
  description: string
  pacing: string
}

/** Style picker + free-form brief + re-draft control. */
export default function StylePanel({ asset, disabled }: StylePanelProps) {
  const redraft = useRedraft(asset.project_id)
  const presets = useQuery({
    queryKey: ['styles'],
    queryFn: () => jsonFetch<PresetCard[]>('/api/v1/styles'),
    staleTime: Infinity,
  })
  const [presetId, setPresetId] = useState(asset.style_preset)
  const [brief, setBrief] = useState(asset.user_brief)
  const [error, setError] = useState<string | null>(null)

  const redrafting = asset.status === 'redrafting'
  const busy = redrafting || disabled || redraft.isPending
  const unchanged = presetId === asset.style_preset && brief === asset.user_brief

  async function requestRedraft() {
    setError(null)
    try {
      await redraft.mutateAsync({ assetId: asset.id, presetId, userBrief: brief })
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Re-draft failed')
    }
  }

  return (
    <div className="style-panel">
      <div className="style-row">
        <label>
          Style{' '}
          <select value={presetId} onChange={(e) => setPresetId(e.target.value)} disabled={busy}>
            {(presets.data ?? []).map((p) => (
              <option key={p.preset_id} value={p.preset_id}>
                {p.name} — {p.pacing}
              </option>
            ))}
          </select>
        </label>
        <button onClick={requestRedraft} disabled={busy || unchanged}>
          {redrafting ? 'Re-drafting…' : 'Re-draft'}
        </button>
      </div>
      <textarea
        value={brief}
        placeholder="Describe the style you want in plain words (optional) — e.g. “fast cuts on the drone shots, keep the food close-ups”"
        onChange={(e) => setBrief(e.target.value)}
        disabled={busy}
        rows={2}
      />
      {presets.data && (
        <p className="muted">{presets.data.find((p) => p.preset_id === presetId)?.description}</p>
      )}
      {asset.user_brief && <p className="muted">Brief: “{asset.user_brief}”</p>}
      {error && <p style={{ color: '#ff8f8f' }}>{error}</p>}
    </div>
  )
}
