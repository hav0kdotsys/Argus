import { describe, expect, it } from 'vitest'

import { devicesApp, statusOf } from '../sdk/apps/devices.js'
import type { WidgetInput } from '../sdk/types.js'

const key = (overrides: Partial<WidgetInput['key']> = {}, ch = ''): WidgetInput =>
  ({ ch, key: { ctrl: false, escape: false, return: false, ...overrides } }) as WidgetInput

describe('devices widget app', () => {
  it('maps liveness to a board status', () => {
    expect(statusOf({ online: false })).toBe('offline')
    expect(statusOf({ agentUp: false, online: true })).toBe('agent-down')
    expect(statusOf({ agentUp: true, online: true })).toBe('online')
  })

  it('init returns state; reduce closes on esc/q/ctrl-c and swallows the rest', () => {
    expect(devicesApp.init('')).toEqual({ v: 0 })

    const state = devicesApp.init('')!

    expect(devicesApp.reduce(state, key({ escape: true }))).toBeNull()
    expect(devicesApp.reduce(state, key({}, 'q'))).toBeNull()
    expect(devicesApp.reduce(state, key({ ctrl: true }, 'c'))).toBeNull()
    expect(devicesApp.reduce(state, key({}, 'x'))).toBe(state)
  })
})
