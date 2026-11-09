import { Box, Text } from '@hermes/ink'
import { useEffect, useState } from 'react'

import { Dialog } from '../../components/overlay.js'
import { fetchDeck } from '../../lib/hvkdeck.js'
import type { Theme } from '../../theme.js'
import { defineWidgetApp } from '../registry.js'
import { isCtrl } from '../types.js'

/**
 * Devices — the live estate board as an ambient panel: HavoK's machines
 * (winhvk, laphvk, debhvk), the friend-PC MiraAgent receivers (winbatata,
 * winghost, winfranci) and the phones on MIRA's device channel (mobilehvk,
 * mobileghost). It reads the same HvkDeck credentials the deck uses and polls
 * hvkdeckd's /api/devices (LAN first, the Cloudflare Access service token as
 * fallback). Green = up with its MIRA agent answering, amber = reachable but
 * the agent is down, red = offline. The fetch + timer live in the component
 * (ticker-style), so closing the panel cleans them up.
 */

const USAGE = 'usage: /devices   (toggle the estate device board — PCs + phones)'
const REFRESH_MS = 8000

export type Status = 'agent-down' | 'offline' | 'online'

export interface Service {
  name: string
  up: boolean
}

export interface Device {
  agentUp?: boolean
  error?: null | string
  host: string
  kind?: string
  label?: string
  latencyMs?: number
  online?: boolean
  owner?: string
  role?: string
  services?: Service[]
  uptimeSec?: number
}

type Phase = { at: number; devices: Device[]; kind: 'ready' } | { kind: 'error'; message: string } | { kind: 'loading' }

async function fetchBoard(): Promise<{ at: number; devices: Device[] }> {
  const data = await fetchDeck<{ at?: number; devices?: Device[] }>('devices')

  return { at: data.at ?? Date.now() / 1000, devices: data.devices ?? [] }
}

export function statusOf(d: Pick<Device, 'agentUp' | 'online'>): Status {
  if (!d.online) {
    return 'offline'
  }

  return d.agentUp ? 'online' : 'agent-down'
}

function Board({ t }: { t: Theme }) {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' })

  useEffect(() => {
    let alive = true

    const tick = () =>
      fetchBoard().then(
        ({ at, devices }) => {
          if (alive) {
            setPhase({ at, devices, kind: 'ready' })
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
    return <Text color={t.color.muted}>connecting to debhvk…</Text>
  }

  if (phase.kind === 'error') {
    return <Text color={t.color.error}>{phase.message}</Text>
  }

  const tone: Record<Status, string> = {
    'agent-down': t.color.warn,
    offline: t.color.error,
    online: t.color.ok
  }

  const glyph: Record<Status, string> = { 'agent-down': '◐', offline: '○', online: '●' }
  const online = phase.devices.filter(d => d.online).length
  const agentDown = phase.devices.filter(d => d.online && !d.agentUp).length
  const offline = phase.devices.filter(d => !d.online).length
  const width = Math.max(4, ...phase.devices.map(d => (d.label ?? d.host).length))

  return (
    <Box flexDirection="column">
      <Box columnGap={2} marginBottom={1}>
        <Text color={t.color.ok}>● {online} online</Text>
        {agentDown > 0 && <Text color={t.color.warn}>◐ {agentDown} agent</Text>}
        {offline > 0 && <Text color={t.color.error}>○ {offline} off</Text>}
      </Box>
      {phase.devices.map(d => {
        const status = statusOf(d)
        const right = status === 'offline' ? 'offline' : status === 'agent-down' ? 'agent down' : (d.owner ?? '')

        return (
          <Box columnGap={1} key={d.host}>
            <Text color={tone[status]}>{glyph[status]}</Text>
            <Text color={t.color.text}>{(d.label ?? d.host).padEnd(width)}</Text>
            <Text color={status === 'online' ? t.color.muted : tone[status]}>{right}</Text>
          </Box>
        )
      })}
    </Box>
  )
}

export interface DevicesState {
  v: 0
}

export const devicesApp = defineWidgetApp<DevicesState>({
  id: 'devices',
  help: 'live estate device board — PCs and phones, online / agent / offline',
  mode: 'ambient',
  usage: USAGE,

  init() {
    return { v: 0 }
  },

  reduce(state, { ch, key }) {
    return key.escape || ch === 'q' || isCtrl(key, ch, 'c') ? null : state
  },

  render({ t }) {
    return (
      <Dialog title="Estate" width={34}>
        <Board t={t} />
      </Dialog>
    )
  }
})
