# Core patches - every ARGUS edit outside `argus/`

ARGUS is a soft fork: its own code lives under `argus/` and in plugins. When a change MUST touch Hermes' tree, it
is listed here with why, so a conflict during `git merge upstream/main` is always explicable - and each one is
written the way upstream would take it (generic, no ARGUS names), so it can be offered upstream and shrink this list.

| # | Files | What | Why | Upstream? |
|---|---|---|---|---|
| 1 | `apps/shared/src/skin.ts`, `ui-tui/src/theme.ts`, `ui-tui/src/components/branding.tsx`, `ui-tui/src/app/useMainApp.ts` | Skin-driven TUI branding: new optional skin tokens `branding.icon`, `branding.tagline`, `branding.byline`; the terminal title's fallback uses the skin's agent name. Defaults reproduce stock Hermes exactly (☤, the catalog tagline, "Nous Research", "Hermes"). | The TUI hardcoded "☤ Nous Research · Messenger of the Digital Gods", "· Nous Research" after the model, and the window title "Hermes" - the skin engine already rebrands everything else (Ares/Poseidon would want this too). | Candidate: generic skin capability, no behaviour change for existing skins. |

## Merging upstream

```bash
git fetch upstream && git merge upstream/main     # on the argus branch / main of the fork
```
On a conflict in a file above, keep upstream's change and re-apply the row's intent. Then rebuild the TUI
(`HERMES_TUI_FORCE_BUILD=1 argus`) and run `argus --version` plus a TUI smoke test.
