import {
  Button,
  type EstateDevice,
  host,
  Popover,
  PopoverContent,
  PopoverTrigger,
  STATUSBAR_AREAS
} from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

/**
 * Estate — the MIRA device board in the Desktop status bar. A compact indicator (● online · ◐ agent
 * down · ○ offline) that opens a popover listing every estate device: HavoK's machines, the friend-PC
 * MiraAgent receivers, and the phones on MIRA's channel. Data comes from the gateway's /api/estate
 * route (host.estate), so the deck credentials stay in the core. Status colours are fixed (green =
 * up with its agent, amber = agent down, red = offline) so they read the same in any theme.
 */

type Status = 'agent-down' | 'offline' | 'online'

const TONE: Record<Status, string> = { 'agent-down': '#ffb347', offline: '#ff6b81', online: '#6fdc8c' }
const GLYPH: Record<Status, string> = { 'agent-down': '◐', offline: '○', online: '●' }
const REFRESH_MS = 8000

function statusOf(d: EstateDevice): Status {
  if (!d.online) {
    return 'offline'
  }

  return d.agentUp ? 'online' : 'agent-down'
}

function useEstate(): { devices: EstateDevice[]; error: null | string } {
  const [devices, setDevices] = useState<EstateDevice[]>([])
  const [error, setError] = useState<null | string>(null)

  useEffect(() => {
    let alive = true

    const tick = () =>
      host.estate().then(
        res => {
          if (alive) {
            setDevices(res.devices ?? [])
            setError(null)
          }
        },
        (e: unknown) => {
          if (alive) {
            setError(e instanceof Error ? e.message : String(e))
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

  return { devices, error }
}

function Row({ device }: { device: EstateDevice }) {
  const status = statusOf(device)

  const detail =
    status === 'offline'
      ? 'offline'
      : status === 'agent-down'
        ? 'agent down'
        : device.uptimeSec
          ? `up ${Math.round(device.uptimeSec / 3600)}h`
          : (device.owner ?? '')

  return (
    <div style={{ alignItems: 'center', display: 'flex', fontSize: 12, gap: 8, padding: '2px 0' }}>
      <span style={{ color: TONE[status], width: 10 }}>{GLYPH[status]}</span>
      <span style={{ flex: 1, fontWeight: 500 }}>{device.label ?? device.host}</span>
      <span style={{ color: status === 'online' ? 'var(--muted, #888)' : TONE[status] }}>{detail}</span>
    </div>
  )
}

function EstateBar() {
  const { devices, error } = useEstate()
  const online = devices.filter(d => d.online).length
  const agentDown = devices.filter(d => d.online && !d.agentUp).length
  const offline = devices.filter(d => !d.online).length

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button aria-label="Estate devices" size="micro" variant="ghost">
          <span style={{ alignItems: 'center', display: 'flex', gap: 6, fontFamily: 'var(--mono, monospace)' }}>
            <span style={{ color: TONE.online }}>● {online}</span>
            {agentDown > 0 && <span style={{ color: TONE['agent-down'] }}>◐ {agentDown}</span>}
            {offline > 0 && <span style={{ color: TONE.offline }}>○ {offline}</span>}
          </span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" aria-label="Estate devices" side="top">
        <div style={{ minWidth: 220, padding: 4 }}>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 1, opacity: 0.7, paddingBottom: 6 }}>ESTATE</div>
          {error && devices.length === 0 ? (
            <div style={{ color: TONE.offline, fontSize: 12 }}>{error}</div>
          ) : (
            devices.map(d => <Row device={d} key={d.host} />)
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}

export default {
  defaultEnabled: true,
  description: 'The MIRA estate device board (PCs + phones) in the status bar.',
  id: 'estate',
  name: 'Estate',
  register(ctx: { onDispose: (fn: () => void) => void; register: (c: unknown) => () => void }) {
    ctx.register({ area: STATUSBAR_AREAS.right, id: 'board', order: 20, render: () => <EstateBar /> })
  }
}
