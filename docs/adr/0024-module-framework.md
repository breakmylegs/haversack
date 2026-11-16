# ADR-0024: Module framework implementation

- Status: accepted (slice 13, decided under Peter's delegation; ADR-0012 to ADR-0019 taken as approved per the C0 recommendations)
- Date: 16 November 2026
- Deciders: Peter (owner)
- Sources: `docs/build-prompt-v2.md` sections 4, 7 and 12 (slice 13); ADR-0012, ADR-0015

## Decision

1. **Registry** (`keepsake/modules.py`). Each module has a flag in the `moduleFlags` setting (defaults: Saves, Advisor and Installer on; Replication and Desktop off), a "writes" text, optional start, stop and health, and its lifecycle listeners. A disabled or failed module has no listeners and runs nothing. A start, stop or health failure marks the module failed and stops it; the others carry on, and the Modules page offers "Try again". Advisor, Replication, Installer and Desktop are registered as not available until their slices.
2. **Saves as a module.** Saves keeps its v1 code where it is. Its flag gates game events, the idle loop and sleep snapshots; its health is the slice 9 health checks.
3. **Lifecycle bus** (`keepsake/bus.py`). Core publishes `game_started` (launch check begins), `game_frozen`, `game_released` (after the freeze or strict gate ends) and `game_exited` (the game's processes are gone), each with `gameKey` and app ID. A failing handler is logged and isolated.
4. **Per-game lock** (`keepsake/locks.py`). Every Saves write path (launch check, exit save, pull, push, conflict resolution, restore, undo and the idle pass) holds the game's lock with owner `saves`. Other modules will take the same lock; Saves jobs pre-empt Replication by being queued first.
5. **State database** (`keepsake/statedb.py`). One SQLite file, `keepsake.db`, in the runtime folder (mode 0600), WAL mode. Each module owns tables prefixed with its name and a list of forward migrations, each run in one transaction and recorded in `_migrations`. A failed migration leaves that module at its previous version; a database newer than the build refuses to migrate that module. Saves stays on its JSON files. Without `sqlite3`, modules needing state stay off and Saves is unaffected.
6. **Steam Operations Executor** (`keepsake/steamops.py`, `src/steamops.ts`). A `core_steam_ops` queue of `probe`, `set-launch-options`, `set-shortcut-name`, `set-shortcut-exe`, `set-shortcut-start-dir` and `set-compat-tool`. The frontend claims operations on an event and every minute, stores the original value, applies the change, waits 600 ms, reads the field back from `AppDetails` and reports success only if it matches. A claim not finished within two minutes is offered again. In slice 13 only the Diagnostics "Probe Steam APIs" button creates operations, and a probe writes nothing; write operations wait for Replication and Installer, which create them only after a user action (P15).
7. **Discovery amendment** (v2 section 10, slice 3). Shortcuts now carry exe, start dir, launch options and icon from `shortcuts.vdf`, the compatibility tool from `config/config.vdf` (`CompatToolMapping`), and the custom artwork file names in `userdata/<id>/config/grid`. Device-local only (principle 10).

## Consequences

- The per-game lock adds no waiting today because Saves is the only writer.
- Write operations through the executor are untested on a device (A70 to A76, A127).
