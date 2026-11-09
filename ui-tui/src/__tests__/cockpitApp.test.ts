import { describe, expect, it } from 'vitest'

import { cockpitApp } from '../sdk/apps/cockpit.js'
import type { WidgetInput } from '../sdk/types.js'

const key = (overrides: Partial<WidgetInput['key']> = {}, ch = ''): WidgetInput =>
  ({
    ch,
    key: { ctrl: false, escape: false, leftArrow: false, return: false, rightArrow: false, ...overrides }
  }) as WidgetInput

describe('cockpit widget app', () => {
  it('init picks the tab from the argument', () => {
    expect(cockpitApp.init('')).toEqual({ tab: 0 })
    expect(cockpitApp.init('overview')).toEqual({ tab: 1 })
    expect(cockpitApp.init('health')).toEqual({ tab: 2 })
    expect(cockpitApp.init('phones')).toEqual({ tab: 3 })
    expect(cockpitApp.init('nonsense')).toEqual({ tab: 0 })
  })

  it('arrows and digits switch tabs; Esc/q/ctrl-c close', () => {
    expect(cockpitApp.reduce({ tab: 0 }, key({ rightArrow: true }))).toEqual({ tab: 1 })
    expect(cockpitApp.reduce({ tab: 3 }, key({ rightArrow: true }))).toEqual({ tab: 0 })
    expect(cockpitApp.reduce({ tab: 0 }, key({ leftArrow: true }))).toEqual({ tab: 3 })
    expect(cockpitApp.reduce({ tab: 0 }, key({}, '4'))).toEqual({ tab: 3 })
    expect(cockpitApp.reduce({ tab: 1 }, key({ escape: true }))).toBeNull()
    expect(cockpitApp.reduce({ tab: 1 }, key({}, 'q'))).toBeNull()
    expect(cockpitApp.reduce({ tab: 1 }, key({ ctrl: true }, 'c'))).toBeNull()

    const same = { tab: 1 }

    expect(cockpitApp.reduce(same, key({}, 'z'))).toBe(same)
  })
})
