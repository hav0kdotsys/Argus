/**
 * MIRA client for the TUI: reads the live cross-client conversation feed from mira-api (the same `viFeed` the
 * laphvk VI tails). Credentials come from the ARGUS env the `mira` provider already uses — `MIRA_API_KEY`
 * (operator token) and `MIRA_BASE_URL` (default: debhvk on the home LAN). The feed holds the last ~30 exchanges
 * across every client (voice, discord, api, argus, …): tailing it = watching MIRA's room live.
 */

const DEFAULT_BASE = 'http://192.168.1.222:5000/v1'

function miraRoot(): string {
  const base = process.env.MIRA_BASE_URL || DEFAULT_BASE

  return base.replace(/\/v1\/?$/, '')
}

export interface MiraExchange {
  at?: string
  client?: string
  kind?: string
  latencyMs?: null | number
  provider?: string
  reply?: string
  user?: string
}

export async function fetchMiraFeed(timeoutMs = 4000): Promise<MiraExchange[]> {
  const token = process.env.MIRA_API_KEY ?? ''
  const headers: Record<string, string> = { Accept: 'application/json' }

  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  const res = await fetch(`${miraRoot()}/v1/hvksys-jarvis/vi/feed`, { headers, signal: AbortSignal.timeout(timeoutMs) })

  if (res.status === 401 || res.status === 403) {
    throw new Error('MIRA feed: not authorized (set MIRA_API_KEY in ~/.argus/.env)')
  }

  if (!res.ok) {
    throw new Error(`MIRA feed answered ${res.status}`)
  }

  const data = (await res.json()) as { feed?: MiraExchange[] }

  return data.feed ?? []
}
