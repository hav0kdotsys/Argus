/** Reference apps. Importing this module registers them (defineWidgetApp
 *  runs at module load) — appLayout imports it once at startup. User widgets
 *  from $HERMES_HOME/tui-widgets ride the same import (async, non-fatal). */
import { loadUserWidgets, watchUserWidgets } from '../userWidgets.js'

void loadUserWidgets()
watchUserWidgets()

export { cockpitApp, type CockpitState } from './cockpit.js'
export { devicesApp, type DevicesState } from './devices.js'
export { dialogTestApp } from './dialogTest.js'
export { gridTestApp } from './gridTest.js'
export { GRID_STREAM_COUNT, type GridTestState } from './gridTestState.js'
export { miraFeedApp, type MiraFeedState } from './mirafeed.js'
export { tickerApp, type TickerState } from './ticker.js'
export { weatherApp, type WeatherState } from './weather.js'
