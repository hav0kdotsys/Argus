import { readFile } from 'node:fs/promises'
import { homedir } from 'node:os'
import { join } from 'node:path'

/**
 * Shared HvkDeck client for the TUI cockpit apps (/devices, /cockpit). The TUI runs under Node, so it
 * reads the same credentials the deck app uses (~/.config/hvkdeck/credentials.json) and talks to hvkdeckd
 * directly — the LAN URL first (fast at home), the Cloudflare Access service token as the fallback. Clients
 * that can't do this (the Electron renderer) go through the gateway's /api/estate/* routes instead.
 */

const LAN_TIMEOUT_MS = 2500
const REMOTE_TIMEOUT_MS = 12_000

export interface DeckCreds {
  cf_client_id?: string
  cf_client_secret?: string
  lan_url?: string
  remote_url?: string
  token?: string
}

export async function loadDeckCreds(): Promise<DeckCreds> {
  const path = process.env.HVKDECK_CREDENTIALS || join(homedir(), '.config', 'hvkdeck', 'credentials.json')

  return JSON.parse(await readFile(path, 'utf8')) as DeckCreds
}

async function getJson<T>(
  base: string,
  path: string,
  remote: boolean,
  creds: DeckCreds,
  timeoutMs: number
): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json', Authorization: `Bearer ${creds.token ?? ''}` }

  if (remote && creds.cf_client_id) {
    headers['CF-Access-Client-Id'] = creds.cf_client_id
    headers['CF-Access-Client-Secret'] = creds.cf_client_secret ?? ''
  }

  const res = await fetch(`${base.replace(/\/$/, '')}/api/${path}`, { headers, signal: AbortSignal.timeout(timeoutMs) })

  if (!res.ok) {
    throw new Error(`hvkdeckd answered ${res.status}`)
  }

  return (await res.json()) as T
}

/** GET hvkdeckd /api/<path>, LAN first then the Cloudflare Access route. Throws a readable Error. */
export async function fetchDeck<T>(path: string): Promise<T> {
  const creds = await loadDeckCreds()

  if (!creds.token) {
    throw new Error('no HvkDeck credentials (~/.config/hvkdeck/credentials.json)')
  }

  if (creds.lan_url) {
    try {
      return await getJson<T>(creds.lan_url, path, false, creds, LAN_TIMEOUT_MS)
    } catch {
      // fall through to the Cloudflare route
    }
  }

  if (!creds.remote_url) {
    throw new Error('debhvk is unreachable (no LAN, no remote_url)')
  }

  return getJson<T>(creds.remote_url, path, true, creds, REMOTE_TIMEOUT_MS)
}
