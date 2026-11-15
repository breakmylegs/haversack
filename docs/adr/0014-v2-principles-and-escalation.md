# ADR-0014: v2 principle amendments, escalation additions and v1 conflicts

- Status: proposed (slice C0, awaiting Peter's approval)
- Date: 15 November 2026
- Deciders: Peter (owner)
- Sources: `docs/build-prompt-v2.md` sections 0, 4, 5, 6 and 10

## Context

The v2 spec extends the v1 build prompt. Where they conflict, v2 wins and each conflict is recorded in an ADR (spec section 0). Where either conflicts with the Decky Loader source, the `@decky/ui` or `@decky/api` types or the template, the source wins and the difference goes in `docs/assumptions.md`. These amendments loosen v1 principles 7 and 9, which is itself an escalation item, so they take effect only when Peter approves this ADR and C0 merges.

## Decision

### Amended principles

| v1 | v2 |
|---|---|
| P7 Gaming Mode only | **Gaming Mode first.** Every feature is fully operable from Gaming Mode with the controller alone. Desktop Mode surfaces (ADR-0017) are additional and never required. Still no terminal or separately installed app |
| P9 No bundled binaries by default | **No bundled binaries.** Stdlib first, vendored pure Python second. System binaries already on SteamOS and Bazzite may be called only if listed in the System Binary Register (ADR-0018), verified on both, and handled when missing. Never bundle, download or install a binary without escalation |
| P10 Canonical paths (cloud data) | Also applies to every Replication manifest and peer message |

### New principles

- **P13 Module isolation**, **P14 Saves owns save data** and **P19 One lock per game**: ADR-0012.
- **P15 Steam writes through the Steam client only**: ADR-0015.
- **P16 Advisor is read-only**: ADR-0019 and `docs/modules/advisor.md`.
- **P17 LAN exposure is opt-in**: ADR-0016.
- **P18 AI is opt-in and minimal**: ADR-0019.

### Escalation additions

Stop and ask Peter, with an ADR, before: enabling the Replication listener by default or binding it beyond the selected LAN interfaces; changing the Replication manifest or peer protocol after slice 18 merges; any Steam write outside P15 or any direct VDF write; any Advisor capability that writes; adding a system binary or relying on one that failed verification; any endpoint outside spec section 6.2; sending AI providers more than P18 allows; any write outside the amended write allowlist (spec section 6.3); any Replication write against a Saves-managed path; network share mounting that needs root or a bundled binary; porting `decky-plugins` code before ADR-0013 is signed off; copying code from CapyDeploy (AGPL-3.0) or any GPL project.

### Conflicts between v1 and v2, resolved in favour of v2

| # | v1 says | v2 says | Resolution |
|---|---|---|---|
| C1 | P7: no feature may need Desktop Mode, and nothing beyond Gaming Mode is in scope | Desktop interface and tray for every module | P7 amended as above. Desktop is extra, never required |
| C2 | P9: no binaries | System binaries from a register | P9 amended. ADR-0018 |
| C3 | Escalation: never edit `shortcuts.vdf`, launch options or any Steam setting, except the opt-in launch wrapper | Replication and Installer create and edit shortcuts, launch options, compatibility tools and artwork | Allowed only through `SteamClient` APIs from the frontend after an explicit user action, with originals stored and every field read back (P15, ADR-0015). Direct VDF writes stay forbidden |
| C4 | Network allowlist (Microsoft, Google, GitHub, user WebDAV and S3) | Adds LAN peers, mDNS, Advisor data sources, AI providers, SteamGridDB, loopback | Added per module and condition (spec section 6.2). Each endpoint is called only when its module and feature are on |
| C5 | Write allowlist (build prompt section 8) | Adds library roots, managed compatdata, grid artwork, `compatibilitytools.d`, staging, `dosdevices` links, two desktop entries | Added per module and condition (spec section 6.3). Every write still passes the central path validator |
| C6 | Threat IDs T16 onwards are already used by v1 (T16 to T41) | New threats numbered T16 to T29 | v2 threats are numbered **T42 to T55** in `docs/threat-model.md`, with a mapping to the spec's numbers |
| C7 | Research section 2.1 proposes the ProtonDB summaries endpoint on `www.protondb.com` | Tuning Advisor checked it and left it out (undocumented, no published terms) and uses the ODbL monthly dumps | Open question for Peter (c0-report Q4). Recommended: dumps only, no `www.protondb.com` call |
| C8 | v1 slice 10 imports Ludusavi backups | Importing from elsewhere in OneDrive needs a scope beyond `Files.ReadWrite.AppFolder` | Unchanged: any extra scope stays an escalation item (spec section 10) |

## Consequences

- `CLAUDE.md` summarises these principles and rules and links here and to `docs/build-prompt-v2.md`.
- v1 principles 1 to 6, 8, 11 and 12 are unchanged.
- The amendments apply to v1 slices not yet merged (spec section 10) and to every v2 slice.
