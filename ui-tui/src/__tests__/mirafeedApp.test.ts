import { describe, expect, it } from 'vitest'

import { miraFeedApp } from '../sdk/apps/mirafeed.js'
import type { WidgetInput } from '../sdk/types.js'

const key = (overrides: Partial<WidgetInput['key']> = {}, ch = ''): WidgetInput =>
  ({ ch, key: { ctrl: false, escape: false, return: false, ...overrides } }) as WidgetInput

describe('mira room widget app', () => {
  it('is an ambient app that closes on esc/q/ctrl-c and swallows the rest', () => {
    expect(miraFeedApp.mode).toBe('ambient')
    expect(miraFeedApp.init('')).toEqual({ v: 0 })

    const state = miraFeedApp.init('')!

    expect(miraFeedApp.reduce(state, key({ escape: true }))).toBeNull()
    expect(miraFeedApp.reduce(state, key({}, 'q'))).toBeNull()
    expect(miraFeedApp.reduce(state, key({ ctrl: true }, 'c'))).toBeNull()
    expect(miraFeedApp.reduce(state, key({}, 'z'))).toBe(state)
  })
})
