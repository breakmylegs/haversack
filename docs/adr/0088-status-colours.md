# ADR-0088: Status colours distinct for colour blindness

- Status: accepted (R27, Peter's request of 22 November 2026 for colour-blind-safe status colours; decided under ADR-0037)
- Date: 22 November 2026
- Deciders: Peter (owner)

## Context

**The old colours could not be told apart by many players.**
- Success was a green (#59bf40) and failure a red (#e04f4f), of similar lightness. That is the pair deuteranopes and protanopes, about one in twelve men, cannot tell apart.
- The colours were written separately in several screens, so they drifted: the library badge used a third green and a third red.

## Decision

1. **Use the Okabe-Ito palette,** designed to stay distinct for the common kinds of colour blindness:

   | Status | Colour |
   |---|---|
   | Success | bluish green #009E73 |
   | Warning | orange #E69F00 |
   | Failure | vermilion #D55E00 |
   | Information | sky blue #56B4E9 |
   | Neutral | grey #8a8fa3 |

2. **Gaming Mode defines them once,** as `STATUS` in `src/format.ts`. Every screen and the library badge use it.

3. **The desktop app keeps its CSS variables, with new values in both modes:**
   - light mode: shades darkened for contrast on white (`--ok` #00785a, `--warn` #a66a00, `--fail` #b34700);
   - dark mode: the brighter originals, which it did not set before.

   Its charts use Okabe-Ito blue, orange, bluish green and reddish purple.

4. **Colour is never the only sign.** Each status keeps its own icon shape (a tick, a clock, a branch, a triangle) or its words.

5. **A test keeps it that way** (`tests/test_status_colours.py`). It checks:
   - the palette's values;
   - that no screen keeps an old red or green;
   - that pages do not write their own status colours;
   - that the desktop sets the colours in both modes.

## Consequences

- **Every status looks different:** green becomes bluish green, red becomes vermilion, and the warning orange is a little more saturated.
- **No threat model change:** this is presentation only.
