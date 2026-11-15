# ADR-0012: Module model

- Status: proposed (slice C0, awaiting Peter's approval)
- Date: 15 November 2026
- Deciders: Peter (owner)
- Sources: `docs/build-prompt-v2.md` sections 1, 4 (P13, P14, P19), 7 and 12

## Context

Keepsake v2 grows from one feature (save sync) to five: Saves, Advisor, Replication, Installer and Desktop. Peter decided that Keepsake is the host repository and the plugin keeps its name, so all five ship as one Decky plugin with one release pipeline and one updater (ADR-0002, ADR-0004). Without a structure, a fault in a new feature (a LAN listener, a scraper, a desktop server) could take save sync down with it, and features could start writing each other's files.

## Decision

1. **Core and modules.** The existing packages in `py_modules/keepsake` (discovery, manifest, roots, state, health, log, lifecycle, update, store, auth, snapshot, sync, importers) become **Core**. They are not moved for cosmetic reasons. New code goes in `py_modules/keepsake/advisor`, `replication`, `installer` and `desktop`, with `py_modules/keepsake/modules.py` as the registry. Saves is the v1 sync logic, which stays where it is. Frontend module routes live in `src/modules/<module>/`; shared components stay in `src/components`.
2. **Dependency rule (P13).** A module may import Core and its own package only. Modules never import each other. Cross-module needs go through Core services: discovery and identity (`gameKey`), the lifecycle bus, the per-game lock, the path validator, state, health and logging, the updater and the Steam Operations Executor (ADR-0015). A test in slice 13 enforces the import rule.
3. **Registry and flags.** Each module registers a name, a feature flag, a settings namespace, health checks, a migration namespace in the one SQLite database, a job queue and a short "what it writes" text for the Modules page. Defaults: Saves on, Advisor on, Replication off, Installer on, Desktop off. A disabled module registers no listeners, opens no ports, runs no jobs and writes nothing.
4. **Failure isolation.** A module whose start-up, health check or job raises an unhandled error disables itself, records the reason, shows it on the Modules page and leaves the others running. Saves is never disabled by another module's failure.
5. **Lifecycle bus.** Core publishes `game_started`, `game_frozen`, `game_released` and `game_exited` with `gameKey` and app ID, from the existing slice 8 lifecycle code. Modules subscribe; none adds its own launch wrapper or app lifetime listener.
6. **One lock per game (P19).** A per-`gameKey` lock in Core spans all modules. No module writes game files, prefixes or saves for a game while another holds its lock or while the game runs. Saves jobs pre-empt Replication jobs for the same game.
7. **Saves owns save data (P14).** After the initial replication copy, only Saves writes save files. Every path Saves resolves, and every manifest path tagged `save`, is off-limits to the other modules. The path validator enforces this, not only the callers.
8. **Job scheduling.** Saves keeps its own queue and priority. Replication runs one transfer at a time (configurable to two). Installer runs one job at a time. Every job takes the per-game lock and checks the game is not running.

## Consequences

- The lifecycle bus and per-game lock are delivered as amendments to v1 slice 8 work if slice 8 is still open, otherwise in slice 13 (`docs/plan.md`).
- The Modules page appears in Settings as a placeholder in slice 9 and becomes live in slice 13.
- One database means migrations must be namespaced and reversible per module. A module rolled back by an update must not break another's tables.
- The import rule and the "disabled writes nothing" rule become tests, so a regression fails `pnpm run check` or the named tests rather than a review.

## Alternatives considered

- **Separate plugins per feature.** Rejected by Peter: one install, one updater, shared discovery and identity.
- **A standalone daemon** (research section 4.1, option B). Superseded by spec section 11: modules run in the Keepsake backend. The cost is that Replication stops when Decky stops, which the job journal and resume handle.
