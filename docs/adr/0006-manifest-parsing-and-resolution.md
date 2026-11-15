# ADR-0006: Manifest parsing and path resolution

- Status: accepted (decided in slice 4 under the owner's delegation, 14 November 2026)
- Date: 14 November 2026
- Deciders: Peter (owner)

## Context

Slice 4 needs the Ludusavi manifest (about 18 MB of YAML, 53,541 entries) on the handheld, within 120 seconds and 400 MB, without bundled binaries. The build prompt suggests a vendored pure-Python YAML parser.

## Decisions

1. **Source URL.** Use `https://raw.githubusercontent.com/mtkennerly/ludusavi-manifest/refs/heads/data/data/manifest.yaml`. The manifest README says the `master` copy "will stop being updated eventually". Same host as the build prompt's URL, so the network allowlist is unchanged. **Differs from the build prompt.**
2. **Parser.** A streaming parser for the manifest's block-YAML subset (`keepsake/yamlsubset.py`) instead of a vendored general YAML library. A survey of the live file found no block scalars, anchors, aliases, tags or non-empty flow collections. Any entry using a construct outside the subset is skipped and counted, never guessed. Measured on the development laptop: all 53,541 entries parsed, zero skipped, about 9 seconds to parse, 22 seconds to build the index with memory tracing on, peak traced memory 30 MB, index 5.6 MB, index load 0.24 seconds. On-device numbers are recorded in the index (`parseSeconds`, `peakRssMb`) and shown in diagnostics.
3. **Compact index.** Only `save` and `config` tagged paths, registry keys (for slice 11), Steam IDs, install folder names and the Steam Cloud flag are kept, plus normalised titles and aliases. Games without save data keep only their Steam ID, to say "no save locations known".
4. **`when` conditions.** The OS must fit (Windows inside a Proton prefix, Linux otherwise). Store constraints are ignored, because shortcuts installed from ISO have no store, and the README allows checking paths whose constraints do not fit.
5. **Placeholders.** Mapped onto the build prompt's logical roots only. `<storeUserId>` as a whole path segment becomes a `*` wildcard (as Ludusavi does); inside a name it is skipped. `<osUserName>` is `steamuser` inside a prefix and skipped natively. The manifest quirk `<winLocalAppData>Low` maps to `winLocalAppDataLow`. `<winDir>`, bare `<root>`, bare `<home>` inside a prefix, absolute paths and `..` are skipped. Coverage on the live manifest: 96.8% of Proton save paths resolve.
6. **Case.** Inside a Proton prefix, path names match case-insensitively, as Windows does.
7. **Base root safety.** A `base` folder that is a filesystem root, too shallow, or contains the home folder, a Steam root or the prefix's `drive_c` is refused, so a badly set shortcut `StartDir` cannot open most of the disk to restores.
8. **Matching.** The user's choice, then the Steam ID for Steam apps, then normalised title and aliases. Several title matches are shown as "choose one", never guessed.
9. **Per-game settings** are stored locally (`games.json`) until slice 7 publishes them as write-once cloud config revisions.

## Consequences

- If the manifest's format changes beyond the subset, affected entries are skipped and the count shows on the Games page. An empty index is never saved over a good one.
- About 3% of Proton save paths are not used. The Games page shows each skipped path and why.
- The canonical model gains no new roots, so the cloud layout planned for slice 6 is unchanged.
