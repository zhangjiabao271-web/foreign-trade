# Shared UI

Button is a locally owned adaptation of the official shadcn/ui new-york-v4
Button source retrieved on 2026-09-08. It retains the native button, CVA variant
selection, data-slot/data-variant markers and native React props/ref forwarding.
The existing workbench CSS classes replace upstream utility styles, preserving
the navy/cyan/orange identity, 44px targets, focus outline and disabled states.
The web app supplies those styles; this package is not a standalone styled theme.

Only native buttons and the three existing variants are supported. Unused
asChild/Slot polymorphism and size presets are deliberately not imported; links
remain links. The default type is button to prevent accidental form submission;
form actions must explicitly use type="submit". Permission checks, queries,
pending state and business commands remain with the caller. No Radix runtime or
shadcn CLI is needed for this native-only source component.

Real consumers are CursorPageControls and FundingEstimate. Existing native
controls outside this slice are unchanged; this is an incremental baseline,
not a claim that every component has been converted or visually reaccepted.
Source and dependency provenance is in THIRD_PARTY_NOTICES.md. Run workspace
typecheck plus web lint, Vitest, build and Playwright after changes.
