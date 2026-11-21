# R14 report: Advisor play sessions

Recorded in ADR-0069 (Peter's request of 21 November 2026).

## What changed

- **`keepsake/advisor/sessions.py`:**
  - readings: `Sensors` finds the files once per session; amdgpu hwmon, `gpu_metrics` v2, k10temp, `/proc`, battery and mains;
  - the per-second `Accumulator` and its summary;
  - frame rate from Steam's diagnostic entries (schema-less protobuf) and MangoHud's CSV logs, with 1% and 0.1% lows;
  - `SessionStore`: the last 20 per game, plus a running summary;
  - the `Recorder` thread, paused while asleep;
  - measured advice, and plain numbers for the AI.
- **App:**
  - the Advisor module records on `game_started` and keeps the summary on `game_exited`;
  - new calls `on_resume` and `advisor_perf_sample`;
  - `on_suspend` pauses sampling.
- **Advisor service:** `session_view` in the page view; the AI request carries `measured_sessions` (numbers only).
- **Frontend:**
  - `SessionCards` on the Advisor page (Last session, Recent sessions, measured advice);
  - `lifecycle.ts` forwards Steam's performance diagnostics (at most once a second while a game runs) and resume.
- **Device check:** `session-sources`, "Session stats sources".
- **Perf gate:** "100 session readings" and "an hour of session samples summarised".
- **Docs:** ADR-0069, `docs/modules/advisor.md`, the Advisor guide, T128, A211 to A213, CHANGELOG, device run part 4 step 7.

## Decisions taken under ADR-0037

- **Frame rate only from read-only sources:** Steam's overlay entries and MangoHud's own logs. The optional launch-option switch is not built: it would be an Advisor write (P16). It is revisited only if the device check shows no read-only source works.
- **gamescope's mangoapp queue is not read,** as that would take messages from Steam's overlay.
- **`gpu_metrics` version 3 (Strix Point) is not parsed yet** (A212); hwmon covers APU power and temperature.

## Tests

- `tests/test_sessions.py`, 17 tests:
  - `gpu_metrics` v2 and other versions; a full reading from a fake device; battery from current and voltage, ignoring a controller's battery; CPU times;
  - session summaries: battery, mains, mixed, throttling, no frame rate; lows from frame times;
  - Steam's diagnostic entries, and MangoHud logs from the session only;
  - the store keeping 20 and its running summary; the recorder (pause, other game, too short);
  - measured advice, and AI numbers carrying no paths or names;
  - the app's feed, pause and resume, and recording; the device check.
- **Regression:** `test_advisor.py`, `test_advisor_2.py`, `test_devicechecks.py`, `test_host.py`, `test_slice11.py` (suspend).
- **Mutation:** 28 mutants of the readings, summary, lows, sources, store, recorder, advice and app hooks. All are killed after six sharper tests were added.

## Known gaps

- Whether Steam's diagnostic entries carry the frame rate with the overlay hidden (A211), the Go 2's `gpu_metrics` (A212), and the frame cap (A213) are open until the device run.

## On-device checklist

- `docs/device-run.md` part 4, step 7.
