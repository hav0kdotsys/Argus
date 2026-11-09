import { Box, Text } from '@hermes/ink'
import { useEffect, useState } from 'react'

import { Dialog } from '../../components/overlay.js'
import { fetchDeck } from '../../lib/hvkdeck.js'
import type { Theme } from '../../theme.js'
import { defineWidgetApp } from '../registry.js'
import { isCtrl } from '../types.js'

import { type Device, statusOf } from './devices.js'

/**
 * Cockpit — the full estate pane for the TUI: a modal with tabs for the device board, debhvk's
 * vitals, and the service health checks, each polling hvkdeckd through the shared client. Named
 * `cockpit` (not `estate`) so it never shadows the gateway's `/estate` text command. ←/→ or 1·2·3
 * switch tabs; Esc/q close.
 */

const USAGE = 'usage: /cockpit   (the estate cockpit: devices · vitals · health)'
const REFRESH_MS = 8000
const TABS = ['Devices', 'Overview', 'Health', 'Phones'] as const
const WIDTH = 60

export interface CockpitState {
  tab: number
}

type Load<T> = { data: T; kind: 'ready' } | { kind: 'error'; message: string } | { kind: 'loading' }

function useDeck<T>(path: string): Load<T> {
  const [load, setLoad] = useState<Load<T>>({ kind: 'loading' })

  useEffect(() => {
    let alive = true

    const tick = () =>
      fetchDeck<T>(path).then(
        data => {
          if (alive) {
            setLoad({ data, kind: 'ready' })
          }
        },
        (error: unknown) => {
          if (alive) {
            setLoad({ kind: 'error', message: error instanceof Error ? error.message : String(error) })
          }
        }
      )

    void tick()
    const id = setInterval(() => void tick(), REFRESH_MS)

    return () => {
      alive = false
      clearInterval(id)
    }
  }, [path])

  return load
}

function bar(pct: number, width = 16): string {
  const n = Math.max(0, Math.min(width, Math.round((pct / 100) * width)))

  return '█'.repeat(n) + '░'.repeat(width - n)
}

function gb(bytes: number): string {
  return `${(bytes / 1e9).toFixed(1)}G`
}

function Loading({ t }: { t: Theme }) {
  return <Text color={t.color.muted}>connecting to debhvk…</Text>
}

function Fail({ message, t }: { message: string; t: Theme }) {
  return <Text color={t.color.error}>{message}</Text>
}

function DevicesTab({ t }: { t: Theme }) {
  const load = useDeck<{ devices?: Device[] }>('devices')

  if (load.kind === 'loading') {
    return <Loading t={t} />
  }

  if (load.kind === 'error') {
    return <Fail message={load.message} t={t} />
  }

  const devices = load.data.devices ?? []
  const tone: Record<string, string> = { 'agent-down': t.color.warn, offline: t.color.error, online: t.color.ok }
  const glyph: Record<string, string> = { 'agent-down': '◐', offline: '○', online: '●' }
  const width = Math.max(4, ...devices.map(d => (d.label ?? d.host).length))

  return (
    <Box flexDirection="column">
      {devices.map(d => {
        const status = statusOf(d)

        const detail =
          status === 'offline'
            ? 'offline'
            : status === 'agent-down'
              ? 'agent down'
              : d.uptimeSec
                ? `up ${Math.round(d.uptimeSec / 3600)}h`
                : (d.owner ?? '')

        return (
          <Box columnGap={1} key={d.host}>
            <Text color={tone[status]}>{glyph[status]}</Text>
            <Text color={t.color.text}>{(d.label ?? d.host).padEnd(width)}</Text>
            <Text color={t.color.muted}>{(d.role ?? d.owner ?? '').padEnd(14)}</Text>
            <Text color={status === 'online' ? t.color.muted : tone[status]}>{detail}</Text>
          </Box>
        )
      })}
    </Box>
  )
}

interface Overview {
  containers?: { running?: number; stopped?: string[]; total?: number; unhealthy?: string[] }
  cpu?: number
  disks?: { avail?: number; mount?: string; pct?: number; size?: number }[]
  failed_units?: string[]
  health?: { name?: string; ok?: boolean }[]
  host?: string
  load?: number[]
  mem?: { swap_used?: number; total?: number; used?: number }
  uptime?: number
}

function OverviewTab({ t }: { t: Theme }) {
  const load = useDeck<Overview>('overview')

  if (load.kind === 'loading') {
    return <Loading t={t} />
  }

  if (load.kind === 'error') {
    return <Fail message={load.message} t={t} />
  }

  const o = load.data
  const cpuPct = Math.round((o.cpu ?? 0) * 100)
  const mem = o.mem ?? {}
  const memPct = mem.total ? Math.round((100 * (mem.used ?? 0)) / mem.total) : 0
  const c = o.containers ?? {}
  const failing = (o.health ?? []).filter(h => !h.ok).map(h => h.name)

  return (
    <Box flexDirection="column">
      <Text color={t.color.label}>
        {o.host ?? 'debhvk'} <Text color={t.color.muted}>up {Math.round((o.uptime ?? 0) / 3600)}h</Text>
      </Text>
      <Text color={t.color.text}>
        cpu <Text color={t.color.primary}>{bar(cpuPct)}</Text> {cpuPct}%{'  '}
        <Text color={t.color.muted}>load {(o.load ?? []).map(l => l.toFixed(2)).join(' ')}</Text>
      </Text>
      <Text color={t.color.text}>
        mem <Text color={t.color.primary}>{bar(memPct)}</Text> {gb(mem.used ?? 0)}/{gb(mem.total ?? 0)}
        {mem.swap_used ? <Text color={t.color.muted}> swap {gb(mem.swap_used)}</Text> : null}
      </Text>
      {(o.disks ?? []).slice(0, 3).map(d => (
        <Text color={t.color.text} key={d.mount}>
          disk <Text color={t.color.primary}>{bar(d.pct ?? 0)}</Text> {d.pct ?? 0}% {d.mount}{' '}
          <Text color={t.color.muted}>({gb(d.avail ?? 0)} free)</Text>
        </Text>
      ))}
      <Text color={t.color.text}>
        containers{' '}
        <Text color={t.color.ok}>
          {c.running ?? 0}/{c.total ?? 0}
        </Text>{' '}
        running
        {c.unhealthy?.length ? <Text color={t.color.error}> · unhealthy {c.unhealthy.join(', ')}</Text> : null}
        {c.stopped?.length ? <Text color={t.color.warn}> · stopped {c.stopped.length}</Text> : null}
      </Text>
      {o.failed_units?.length ? <Text color={t.color.error}>failed units: {o.failed_units.join(', ')}</Text> : null}
      {failing.length ? (
        <Text color={t.color.error}>health failing: {failing.join(', ')}</Text>
      ) : (
        <Text color={t.color.muted}>all health checks ok</Text>
      )}
    </Box>
  )
}

interface Check {
  code?: number
  error?: null | string
  ms?: number
  name?: string
  ok?: boolean
}

function HealthTab({ t }: { t: Theme }) {
  const load = useDeck<{ checks?: Check[] }>('health')

  if (load.kind === 'loading') {
    return <Loading t={t} />
  }

  if (load.kind === 'error') {
    return <Fail message={load.message} t={t} />
  }

  const checks = load.data.checks ?? []
  const width = Math.max(4, ...checks.map(c => (c.name ?? '').length))

  return (
    <Box flexDirection="column">
      {checks.map(c => (
        <Box columnGap={1} key={c.name}>
          <Text color={c.ok ? t.color.ok : t.color.error}>{c.ok ? '✔' : '✖'}</Text>
          <Text color={t.color.text}>{(c.name ?? '').padEnd(width)}</Text>
          <Text color={c.ok ? t.color.muted : t.color.error}>
            {c.ok ? `${c.ms ?? 0} ms` : c.code ? `HTTP ${c.code}` : (c.error ?? 'down')}
          </Text>
        </Box>
      ))}
      {checks.length === 0 && <Text color={t.color.muted}>no health checks reported</Text>}
    </Box>
  )
}

interface Phone {
  battery?: null | number
  charging?: boolean
  connected?: boolean
  label?: string
  network?: null | string
  online?: boolean
  owner?: string
  uptimeDays?: null | number
}

function PhonesTab({ t }: { t: Theme }) {
  const load = useDeck<{ phones?: Phone[] }>('phones')

  if (load.kind === 'loading') {
    return <Loading t={t} />
  }

  if (load.kind === 'error') {
    return <Fail message={load.message} t={t} />
  }

  const phones = load.data.phones ?? []
  const width = Math.max(4, ...phones.map(p => (p.label ?? '').length))

  return (
    <Box flexDirection="column">
      {phones.map(p => {
        const bits: string[] = []

        if (p.battery != null) {
          bits.push(`${p.battery}%${p.charging ? '⚡' : ''}`)
        }

        if (p.network) {
          bits.push(p.network)
        }

        if (p.uptimeDays != null) {
          bits.push(`up ${p.uptimeDays}d`)
        }

        if (p.online && !p.connected) {
          bits.push('no live channel')
        }

        return (
          <Box columnGap={1} key={p.label}>
            <Text color={p.online ? t.color.ok : t.color.error}>{p.online ? '●' : '○'}</Text>
            <Text color={t.color.text}>{(p.label ?? '').padEnd(width)}</Text>
            <Text color={t.color.muted}>{(p.owner ?? '').padEnd(8)}</Text>
            <Text color={t.color.muted}>{bits.join(' · ')}</Text>
          </Box>
        )
      })}
      {phones.length === 0 && <Text color={t.color.muted}>no phones on the channel</Text>}
    </Box>
  )
}

export const cockpitApp = defineWidgetApp<CockpitState>({
  id: 'cockpit',
  help: 'the estate cockpit — devices, vitals and health in one pane',
  usage: USAGE,

  init(arg) {
    const want = TABS.findIndex(name => name.toLowerCase().startsWith(arg.trim().toLowerCase()))

    return { tab: arg.trim() && want >= 0 ? want : 0 }
  },

  reduce(state, { ch, key }) {
    if (key.escape || ch === 'q' || isCtrl(key, ch, 'c')) {
      return null
    }

    if (key.rightArrow || ch === 'l') {
      return { tab: (state.tab + 1) % TABS.length }
    }

    if (key.leftArrow || ch === 'h') {
      return { tab: (state.tab + TABS.length - 1) % TABS.length }
    }

    const digit = Number(ch)

    if (ch >= '1' && ch <= String(TABS.length)) {
      return { tab: digit - 1 }
    }

    return state
  },

  render({ state, t }) {
    const Tab = [DevicesTab, OverviewTab, HealthTab, PhonesTab][state.tab] ?? DevicesTab

    return (
      <Dialog hint="←/→ or 1·2·3 · Esc" title="Estate cockpit" width={WIDTH}>
        <Box flexDirection="column" gap={1}>
          <Box columnGap={2}>
            {TABS.map((name, i) => (
              <Text bold={i === state.tab} color={i === state.tab ? t.color.primary : t.color.muted} key={name}>
                {i + 1} {name}
              </Text>
            ))}
          </Box>
          <Tab t={t} />
        </Box>
      </Dialog>
    )
  }
})
