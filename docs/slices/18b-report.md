# Slice 18b report: streams, sources, sleep and the battery

The second part of slice 18, recorded in ADR-0058. Slice 18 is now complete, and the protocol is frozen at version 1 (`docs/protocol.md`).

## What changed

- **`replication/transfer.py`:** the pull is a pool of streams.
  - **Streams:** it starts with one, adds another every 3 seconds only while the rate rose by 10 percent, and goes up to 4.
  - **Sources:** streams are spread over several sources. A failing source is dropped and its chunk goes back on the queue.
  - **Journal:** the stream that fills a batch commits it, under a lock. A commit records the chunk list as it was before the flush.
  - **Holds:** a hook pauses the job as held.
  - **Progress:** smoothed MB/s, time left and the number of streams.
- **`replication/sleepguard.py`:**
  - Linux: a minimal stdlib D-Bus client takes logind's `idle` block lock and `sleep` delay lock (descriptors passed over the socket).
  - Windows: `SetThreadExecutionState`.
  - A lock that cannot be taken is reported, never fatal.
- **`power.py`:** `battery_state`, giving charge and mains power on Linux (a plugged-in charger wins) and Windows.
- **`replication/jobs.py`:** the transfers manager.
  - It keeps a registry of staging folders. At startup it recovers each job and resumes the ones the user did not pause.
  - Pause, Resume, and "Stop and remove", which retries briefly for Windows' delete race.
  - It holds while a game runs, or below 30 percent battery off mains, and resumes once that clears, checking every minute and when a game exits.
  - The sleep guard is held while any job runs.
- **App:**
  - the module listens for `game_started` and `game_exited`;
  - 4 new calls (`replication_transfers`, `_pause`, `_resume`, `_stop`).
- **Pages:** a **Transfers** section on Devices, in Gaming Mode and on the desktop. "Stop and remove" is confirmed first.
- **Docs:** ADR-0058, `docs/protocol.md` (frozen), T116, A193, A194, the module document, the plan and the changelog.

## Test results

- `tests/test_replication_transfers.py`: 27 passed and 1 skipped on Windows (the descriptor-passing D-Bus test is POSIX-only). It covers:
  - battery and hold rules;
  - D-Bus messages;
  - several sources and growing streams;
  - stopping growth, a source that fails, and holds;
  - progress;
  - the manager: run, pause, resume, stop, restart, holds and limits;
  - the app's game-running hold.
- `tests/test_replication_protocol.py` (5 new): the frozen values.
- The covering tests pass: `test_replication_transfer.py` (its spies now take the commit's snapshot), `test_replication_devices.py`, `test_replication_link.py`, `test_replication_rules.py`, `test_host.py`, `test_hosts.py` and `test_modules.py`.
- Mutation checks: 25 mutations across the stream pool, the manager, the hold rule, battery reading, D-Bus parsing and the app's game tracking. All killed after five tests were added and two were tightened.
- `python scripts/check.py`: all checks passed.

## Known gaps

- Nothing starts a transfer yet: slice 19 adds sending a game.
- logind's inhibit for `deck`, Steam's suspend and the battery paths are unverified on the devices (A193, A194).

## On-device checklist

1. Run `python scripts/test_on_device.py tests/test_replication_transfers.py tests/test_replication_transfer.py tests/test_replication_protocol.py`. Everything should pass, including the D-Bus descriptor test.
2. After slice 19, while a game is being sent:
   - **Sleep locks:** run `systemd-inhibit --list` and check that Keepsake holds `idle` (block) and `sleep` (delay).
   - **Sleep and resume:** press the power button. The device should sleep within a few seconds, and the transfer should carry on after it wakes.
   - **Battery:** unplug below 30 percent. The transfer should wait, then carry on once you plug in.
   - **Game:** start a game. The transfer should wait, then carry on when you quit.
