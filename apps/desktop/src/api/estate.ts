import { hermesApi, profileScoped } from './client'

/**
 * The MIRA estate (HvkDeck) for the Desktop, served by the gateway's ``/api/estate/*`` routes
 * (``hermes_cli/web_routers/estate.py``). The renderer can't read the HvkDeck token or reach hvkdeckd
 * directly, so the core proxies it; this is the client the estate plugin (and any future pane) calls.
 * Read-only.
 */

export interface EstateService {
  name: string
  up: boolean
}

export interface EstateDevice {
  agentUp?: boolean
  error?: null | string
  host: string
  kind?: string
  label?: string
  latencyMs?: number
  online?: boolean
  owner?: string
  role?: string
  services?: EstateService[]
  uptimeSec?: number
}

export interface EstateDevicesResponse {
  at?: number
  devices?: EstateDevice[]
}

/** The whole estate's liveness: HavoK's machines, the friend PCs, and the phones on MIRA's channel. */
export function getEstateDevices(): Promise<EstateDevicesResponse> {
  return hermesApi<EstateDevicesResponse>({ ...profileScoped(), path: '/api/estate/devices' })
}
