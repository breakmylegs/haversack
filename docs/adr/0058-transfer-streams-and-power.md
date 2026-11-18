# ADR-0058: Streams, sources, sleep, the battery rule and the protocol freeze (slice 18b)

- Status: accepted (decided under ADR-0037)
- Date: 18 November 2026
- Deciders: Peter (owner)

## Context

ADR-0057 built the transfer engine (18a). The rest of slice 18 is:
- the speed design of ADR-0054: suit fast and slow links, and pull from several of the user's devices at once (Peter, 18 November 2026: "less point to point");
- the sleep inhibitor and the battery rule (ADR-0045 rule 5);
- progress, with pause, resume and "Stop and remove";
- freezing the protocol, as the plan requires at the end of slice 18.

ADR-0045 left one decision open: a logind D-Bus lock or `systemd-inhibit`.

## Decision

1. **Streams that adapt.**
   - **Starting and growing:**
     - a pull starts with one stream;
     - every 3 seconds it measures the rate, and adds a stream only if the last window was at least 10 percent faster than the one before;
     - once a stream does not help, it stops growing.
   - **Limits:** at most 4 streams. Each stream is its own connection with one request in flight, so a slow or relayed link is never crowded.
2. **Several sources.**
   - **Spreading the work:** a job may name several paired devices that offer the same root hash. Streams are spread over them in turn.
   - **A source that fails is dropped.** Its chunk goes back on the queue and the other sources finish. The job waits and retries (ADR-0057) only when no source is left.
   - **Nothing is trusted from a source:** every chunk is still checked against the manifest's hash.
3. **The journal with several streams.**
   - **Who commits:** the stream that fills a batch of 16 chunks commits it, under a lock. The controller commits every 2 seconds.
   - **What a commit records:** the chunk list as it was when the commit began, after its files are flushed. A chunk another stream writes during the flush waits for the next commit.
4. **The sleep inhibitor: logind over D-Bus, not `systemd-inhibit`.**
   - **The client:** a minimal pure-stdlib D-Bus client. It uses EXTERNAL auth, negotiates descriptor passing, calls `Hello`, then `org.freedesktop.login1.Manager.Inhibit`.
   - **The locks:**
     - `idle` in block mode, so an idle timer cannot sleep the device mid-copy;
     - `sleep` in delay mode, so a sleep the user asks for waits up to logind's `InhibitDelayMaxSec` (5 seconds by default), long enough for the journal's 2-second commit.
   - **Releasing:** a lock is the descriptor logind passes back; closing it releases the lock.
   - **Why not `systemd-inhibit`:** it would need a System Binary Register entry (ADR-0018) and a child process held open. D-Bus needs neither.
   - **Windows:** `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)` on the event loop's thread.
   - **Failure:** a lock that cannot be taken is reported in the transfers view and is never fatal. The copy resumes after sleep.
   - **The user's power button still works:** Keepsake never blocks sleep the user asks for, only delays it a few seconds.
5. **When transfers wait** (they resume by themselves):
   - while a game runs on this device, from the lifecycle bus's `game_started` and `game_exited` (P6; the game also keeps the bandwidth and disk);
   - below 30 percent battery when not on mains power. Battery and charger come from `/sys/class/power_supply` on Linux (a plugged-in charger wins over the battery's status) and `GetSystemPowerStatus` on Windows. A charge it cannot read never holds a copy.

   A held job is paused with `held` set. It is checked again every minute and when a game exits.
6. **The transfers manager** (`replication/jobs.py`).
   - **The registry:** `replication-jobs.json` in the runtime folder lists each job's staging folder, up to 32.
   - **At startup:** every job is recovered (ADR-0057), and a job the user did not pause resumes by itself.
   - **Pause** keeps everything and waits for **Resume**. **"Stop and remove"** is confirmed in the interface first.
   - **The Windows delete race:** a write already handed to a worker thread can finish after the task is cancelled, and an open file blocks a delete on Windows. So the removal retries briefly, then sweeps once more.
   - **The sleep guard** is held while any job runs.
7. **Progress.** Each job shows:
   - bytes received of the total, with the percentage;
   - MB/s, smoothed;
   - time left, while it runs;
   - the number of streams;
   - the reason it waits or paused.

   It appears in a **Transfers** section on the Devices page in Gaming Mode and on the desktop. The section is empty until slice 19 makes the first offer.
8. **The protocol is frozen** at version 1 (`docs/protocol.md`).
   - `tests/test_replication_protocol.py` pins the transport constants, the pairing key, a comparison-code vector, the manifest format and a root hash, the frame layout, the request names and the discovery query.
   - A change needs a new version and an ADR (CLAUDE.md escalation rules).

## Consequences

- No new endpoint, binary or permission: D-Bus is a local socket, and logind's inhibit is allowed to an active session by polkit's defaults (A193).
- **T116, A193 and A194:**
  - T116: the sleep and power paths;
  - A193: logind's inhibit for `deck`, and whether Steam's own suspend respects inhibitors;
  - A194: battery readings on both handhelds.

## Sources

- logind's [Inhibitor Locks](https://systemd.io/INHIBITOR_LOCKS/) and [org.freedesktop.login1](https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.login1.html): `Inhibit(what, who, why, mode)` returns a file descriptor; "delay" and "block" modes; `InhibitDelayMaxSec`.
- [D-Bus Specification](https://dbus.freedesktop.org/doc/dbus-specification.html): message format, header fields (`UNIX_FDS` is field 9), EXTERNAL authentication and `NEGOTIATE_UNIX_FD`.
- Microsoft, [SetThreadExecutionState](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate) and [GetSystemPowerStatus](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getsystempowerstatus).
- Linux [power supply class](https://www.kernel.org/doc/html/latest/power/power_supply_class.html): `type`, `capacity`, `status`, `online`, `scope`.
