import { Box, Text } from '@hermes/ink'
import { useEffect, useState } from 'react'

import { Dialog } from '../../components/overlay.js'
import { fetchMiraFeed, type MiraExchange } from '../../lib/mira.js'
import type { Theme } from '../../theme.js'
import { defineWidgetApp } from '../registry.js'
import { isCtrl } from '../types.js'

/**
 * MIRA room — tails MIRA's live cross-client conversation (mira-api's feed), so the running ARGUS is "attached"
 * to the same room Mira Desktop, Discord and the laphvk VI share: every exchange, whoever asked, appears here as
 * it happens. Chime in by chatting with the `mira` model (that exchange lands in this feed too). Ambient, so the
 * composer stays live. Poll-based (near-live); the fetch + timer clean up on close.
 */

const USAGE = 'usage: /mira   (tail MIRA’s live room — every client’s exchanges)'
const REFRESH_MS = 2500
const SHOWN = 6

type Phase = { exchanges: MiraExchange[]; kind: 'ready' } | { kind: 'error'; message: string } | { kind: 'loading' }

function clip(s: string | undefined, n: number): string {
  const t = String(s ?? '')
    .replace(/\s+/g, ' ')
    .trim()

  return t.length > n ? `${t.slice(0, n - 1)}…` : t
}

function Room({ t }: { t: Theme }) {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' })

  useEffect(() => {
    let alive = true

    const tick = () =>
      fetchMiraFeed().then(
        exchanges => {
          if (alive) {
            setPhase({ exchanges, kind: 'ready' })
          }
        },
        (error: unknown) => {
          if (alive) {
            setPhase({ kind: 'error', message: error instanceof Error ? error.message : String(error) })
          }
        }
      )

    void tick()
    const id = setInterval(() => void tick(), REFRESH_MS)

    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  if (phase.kind === 'loading') {
    return <Text color={t.color.muted}>joining MIRA’s room…</Text>
  }

  if (phase.kind === 'error') {
    return <Text color={t.color.error}>{phase.message}</Text>
  }

  const recent = phase.exchanges.slice(-SHOWN)

  if (recent.length === 0) {
    return <Text color={t.color.muted}>the room is quiet</Text>
  }

  return (
    <Box flexDirection="column">
      {recent.map((e, i) => (
        <Box flexDirection="column" key={`${e.at ?? ''}-${i}`} marginBottom={i === recent.length - 1 ? 0 : 1}>
          <Text>
            <Text color={t.color.primary}>{e.client ?? 'api'}</Text>
            <Text color={t.color.muted}> {clip(e.user, 46)}</Text>
          </Text>
          <Text color={t.color.text}>
            <Text color={t.color.ok}>MIRA </Text>
            {clip(e.reply, 52)}
          </Text>
        </Box>
      ))}
    </Box>
  )
}

export interface MiraFeedState {
  v: 0
}

export const miraFeedApp = defineWidgetApp<MiraFeedState>({
  id: 'mira',
  help: 'tail MIRA’s live room — every client’s exchanges as they happen',
  mode: 'ambient',
  usage: USAGE,

  init() {
    return { v: 0 }
  },

  reduce(state, { ch, key }) {
    return key.escape || ch === 'q' || isCtrl(key, ch, 'c') ? null : state
  },

  render({ cols, t }) {
    return (
      <Dialog title="MIRA · room" width={Math.min(60, cols - 4)}>
        <Room t={t} />
      </Dialog>
    )
  }
})
