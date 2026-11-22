# Status colours for colour blindness (R27 part, v0.50.0)

## What changed

- **One palette for Gaming Mode:** `STATUS` in `src/format.ts` (Okabe-Ito). It replaces the old red and green in Games, Activity, Advisor, game transfers and the library badge.
- **The desktop app's colours:** darker shades for light mode, the brighter originals added for dark mode, and Okabe-Ito chart series.
- **Docs:** ADR-0088, CHANGELOG and plan.

## Tests

- `tests/test_status_colours.py`: 4 passed. It caught two old colours left in the Advisor page's confidence colours, which are now fixed.
- Mutation: putting back any old colour, or writing a status colour on a page, fails the test.
- Threat model: no change (presentation only).

## On-device checklist

None beyond a look: statuses on Games and Health should show bluish green, orange and vermilion.
