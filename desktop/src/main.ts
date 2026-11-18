// Keepsake's desktop interface for PCs and Desktop Mode (ADR-0038, ADR-0040).
// Plain TypeScript and the DOM: no framework, no third-party code, nothing from another origin.

import { ApiError, call, hasToken, initialPage, onEvents } from "./api.js";
import { h, replace, size, when } from "./dom.js";
import type {
  CloudStatus,
  ConflictDetails,
  ConflictEntry,
  GameMatch,
  ImportAllStatus,
  LudusaviGame,
  HealthCheck,
  HistoryItem,
  ModuleStatus,
  PcResult,
  PcUpdateStatus,
  QamSummary,
  Settings,
  UpdateCheck,
} from "./types.js";

type Page = { id: string; title: string; render: (main: HTMLElement) => Promise<void> };

const storeNames: Record<string, string> = { local: "Test store on this device", onedrive: "OneDrive", gdrive: "Google Drive", webdav: "WebDAV", s3: "S3" };

const statusText: Record<string, string> = { ok: "All good", info: "Note", warn: "Needs attention", fail: "Problem" };

function toast(text: string): void {
  const box = document.getElementById("toasts");
  if (!box) return;
  const item = h("div", { class: "toast", role: "status" }, text);
  box.append(item);
  setTimeout(() => item.remove(), 6000);
}

async function act(button: HTMLButtonElement, work: () => Promise<void>): Promise<void> {
  button.disabled = true;
  try {
    await work();
  } catch (error) {
    toast(error instanceof ApiError ? error.message : "Something went wrong");
  } finally {
    button.disabled = false;
  }
}

function button(label: string, onClick: (self: HTMLButtonElement) => Promise<void>, kind = ""): HTMLButtonElement {
  const element = h("button", { type: "button", class: kind }, label) as HTMLButtonElement;
  element.addEventListener("click", () => void act(element, () => onClick(element)));
  return element;
}

// Overview

async function overview(main: HTMLElement): Promise<void> {
  const summary = await call<QamSummary>("qam_summary");
  const rows: [string, string][] = [
    ["This device", summary.deviceName || "Not named yet"],
    ["Cloud", `${storeNames[summary.store] ?? summary.store}${summary.signedIn ? ", signed in" : summary.store === "local" ? "" : ", not signed in"}`],
    ["Games synced", String(summary.enabledGames)],
    ["Last sync", when(summary.lastSync)],
    ["Conflicts", summary.conflicts ? `${summary.conflicts} to resolve` : "None"],
  ];
  replace(
    main,
    h("h1", {}, "Overview"),
    h("p", { class: `health ${summary.health}` }, statusText[summary.health] ?? summary.health),
    summary.problems.length ? h("ul", { class: "problems" }, ...summary.problems.map((p) => h("li", {}, p))) : null,
    h("dl", { class: "facts" }, ...rows.flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)])),
    summary.currentGame ? h("p", {}, `Playing ${summary.currentGame.name} (${summary.currentGame.status})`) : null,
    summary.busy ? h("p", { class: "busy" }, `Working: ${summary.busy}`) : null,
    h(
      "div",
      { class: "actions" },
      button(
        "Sync now",
        async () => {
          const result = await call<{ ok: boolean; reason?: string; games?: number }>("sync_now");
          toast(result.ok ? `Synced ${result.games ?? 0} games.` : `Not synced: ${result.reason ?? "unknown reason"}`);
          await overview(main);
        },
        "primary",
      ),
    ),
  );
}

// Conflicts

async function conflicts(main: HTMLElement): Promise<void> {
  const entries = await call<ConflictEntry[]>("list_conflicts");
  replace(
    main,
    h("h1", {}, "Conflicts"),
    h("p", {}, "These games changed both here and on another device. Nothing is overwritten until you choose."),
    entries.length
      ? h("ul", { class: "list" }, ...entries.map((entry) => h("li", {}, conflictCard(entry, main))))
      : h("p", { class: "empty" }, "No conflicts."),
  );
}

function conflictCard(entry: ConflictEntry, main: HTMLElement): HTMLElement {
  const details = h("div", { class: "details" });
  const versions = entry.conflict.heads.length;
  const card = h(
    "div",
    {},
    h("h2", {}, entry.name),
    h("p", {}, `${versions === 1 ? "1 version" : `${versions} versions`} from your other devices, ${entry.conflict.localFiles} files here.`),
    button("Compare and choose", async () => {
      const info = await call<ConflictDetails>("conflict_details", entry.key);
      replace(details, ...choices(info, main));
    }),
    details,
  );
  return card;
}

function choices(info: ConflictDetails, main: HTMLElement): HTMLElement[] {
  const armed = new Set<string>();
  // Choosing replaces files, so each choice needs a second, explicit press (as in Gaming Mode).
  const choose = (label: string, id: string, run: () => Promise<unknown>) => {
    const element = button(label, async (self) => {
      if (!armed.has(id)) {
        armed.add(id);
        self.textContent = `${label}: press again to confirm`;
        return;
      }
      await run();
      toast("Conflict resolved. The other version is kept, pinned, in History.");
      await conflicts(main);
    });
    return element;
  };
  const sides = info.sides ?? [];
  return [
    h(
      "table",
      { class: "sides" },
      h("tr", {}, h("th", {}, "Version"), h("th", {}, "Device"), h("th", {}, "Saved"), h("th", {}, "Files"), h("th", {}, "Size")),
      ...sides.map((s) =>
        h(
          "tr",
          {},
          h("td", {}, s.side === "local" ? "This device" : "Cloud"),
          h("td", {}, s.device ?? ""),
          h("td", {}, s.created ? new Date(s.created).toLocaleString() : "now"),
          h("td", {}, `${s.files} (${s.changedFiles} changed)`),
          h("td", {}, size(s.bytes)),
        ),
      ),
    ),
    h(
      "div",
      { class: "actions" },
      choose("Keep this device's save", "local", () => call("resolve_conflict", info.key, "use-local", null)),
      ...sides
        .filter((s) => s.side === "cloud" && s.snapId)
        .map((s) =>
          choose(`Use the save from ${s.device ?? "the cloud"}`, `cloud:${s.snapId}`, () =>
            call("resolve_conflict", info.key, "use-cloud", s.snapId),
          ),
        ),
      button("Decide later", async () => {
        await call("resolve_conflict", info.key, "decide-later", null);
        toast("Left for later.");
      }),
    ),
  ];
}

// History

async function history(main: HTMLElement): Promise<void> {
  const result = await call<{ snapshots: HistoryItem[]; errors: string[] }>("recent_history", 50);
  replace(
    main,
    h("h1", {}, "History"),
    result.errors.length ? h("p", { class: "warn" }, `Some games could not be read: ${result.errors.join("; ")}`) : null,
    result.snapshots.length
      ? h(
          "table",
          { class: "history" },
          h("tr", {}, h("th", {}, "Game"), h("th", {}, "Saved"), h("th", {}, "Device"), h("th", {}, "Files"), h("th", {}, "Size")),
          ...result.snapshots.map((s) =>
            h(
              "tr",
              { class: s.quarantined ? "quarantined" : "" },
              h("td", {}, s.name),
              h("td", {}, new Date(s.created).toLocaleString()),
              h("td", {}, s.device ?? ""),
              h("td", {}, String(s.files)),
              h("td", {}, size(s.bytes)),
            ),
          ),
        )
      : h("p", { class: "empty" }, "No snapshots yet."),
  );
}

// Health and modules

async function health(main: HTMLElement): Promise<void> {
  const result = await call<{ checks: HealthCheck[]; summary: string }>("health_checks", true);
  replace(
    main,
    h("h1", {}, "Health"),
    h(
      "ul",
      { class: "list" },
      ...result.checks.map((c) =>
        h(
          "li",
          { class: `check ${c.status}` },
          h("strong", {}, `${c.label}: ${statusText[c.status] ?? c.status}`),
          h("p", {}, c.detail),
          c.items.length ? h("ul", {}, ...c.items.map((i) => h("li", {}, i))) : null,
        ),
      ),
    ),
  );
}

async function modules(main: HTMLElement): Promise<void> {
  const result = await call<{ modules: ModuleStatus[] }>("modules_status");
  replace(
    main,
    h("h1", {}, "Modules"),
    h(
      "ul",
      { class: "list" },
      ...result.modules.map((m) =>
        h(
          "li",
          { class: "card" },
          h("h2", {}, m.title),
          h("p", {}, m.description),
          h("p", { class: "small" }, `Writes: ${m.writes}`),
          !m.available
            ? h("p", { class: "warn" }, m.unavailableReason ?? "Not available yet.")
            : h(
                "label",
                { class: "switch" },
                toggle(m, main),
                m.failed ? ` On, but stopped: ${m.failed}` : m.flag ? " On" : " Off",
              ),
        ),
      ),
    ),
  );
}

function toggle(m: ModuleStatus, main: HTMLElement): HTMLInputElement {
  const input = h("input", { type: "checkbox", checked: m.flag, "aria-label": `${m.title} on or off` }) as HTMLInputElement;
  input.addEventListener("change", () => {
    input.disabled = true;
    call("set_module_enabled", m.name, input.checked)
      .then(() => modules(main))
      .catch((error: unknown) => {
        toast(error instanceof ApiError ? error.message : "Could not change the module");
        input.checked = !input.checked;
        input.disabled = false;
      });
  });
  return input;
}

// Games: which games sync, and which save data each one is (the same choices as in Gaming Mode)

const syncText: Record<string, string> = {
  off: "Not synced",
  "not-synced": "Not synced yet",
  synced: "Synced",
  pending: "Waiting to sync",
  conflict: "Conflict",
  quarantined: "Held back for checking",
};

const matchText: Record<string, string> = {
  manual: "chosen by you",
  "manual-key": "linked by you",
  "steam-id": "matched by Steam ID",
  title: "matched by title",
  ambiguous: "several possible matches",
  none: "no save data found",
  "no-save-data": "no save data in the manifest",
  "no-manifest": "save database not downloaded yet",
};

async function games(main: HTMLElement, filter = ""): Promise<void> {
  const all = await call<GameMatch[]>("match_games");
  const shown = all.filter((g) => g.name.toLowerCase().includes(filter.toLowerCase()));
  const search = h("input", { type: "search", placeholder: "Find a game", value: filter, "aria-label": "Find a game" }) as HTMLInputElement;
  search.addEventListener("change", () => void games(main, search.value));
  replace(
    main,
    h("h1", {}, "Games"),
    h("p", {}, "Turn sync on for the games whose saves should follow you. Keepsake finds each game's saves from the Ludusavi manifest."),
    h("div", { class: "actions" }, search),
    shown.length
      ? h("ul", { class: "list" }, ...shown.map((g) => h("li", {}, gameCard(g, main, filter))))
      : h("p", { class: "empty" }, filter ? "No game matches that name." : "No games found yet."),
  );
}

function gameCard(g: GameMatch, main: HTMLElement, filter: string): HTMLElement {
  const toggle = h("input", { type: "checkbox", checked: g.enabled, "aria-label": `Sync ${g.name}` }) as HTMLInputElement;
  toggle.addEventListener("change", () => {
    toggle.disabled = true;
    call("update_game_config", g.key, { enabled: toggle.checked })
      .then(() => toast(toggle.checked ? `${g.name} now syncs.` : `${g.name} no longer syncs.`))
      .catch((error: unknown) => {
        toggle.checked = !toggle.checked;
        toast(error instanceof ApiError ? error.message : "Could not change the game");
      })
      .finally(() => (toggle.disabled = false));
  });
  const proposal = g.proposal?.candidate;
  return h(
    "div",
    {},
    h("h2", {}, g.name),
    h(
      "p",
      { class: "small" },
      `${g.kind === "steam" ? "Steam game" : "Non-Steam game"}. ${syncText[g.sync] ?? g.sync}. Save data: ${
        g.title ? `${g.title}, ` : ""
      }${matchText[g.method] ?? g.method}.`,
    ),
    h("label", { class: "switch" }, toggle, " Sync this game"),
    proposal
      ? h(
          "div",
          { class: "actions" },
          h("span", {}, `Another device has this as ${proposal.title ?? proposal.gameKey}.`),
          button("Same game", async () => {
            await call("approve_match", g.key);
            await games(main, filter);
          }),
          button("A different game", async () => {
            await call("reject_match", g.key);
            await games(main, filter);
          }),
        )
      : null,
    g.method === "ambiguous" || g.method === "none" ? titlePicker(g, main, filter) : null,
  );
}

function titlePicker(g: GameMatch, main: HTMLElement, filter: string): HTMLElement {
  const input = h("input", { type: "search", placeholder: "Search the save database", "aria-label": `Save data for ${g.name}` }) as HTMLInputElement;
  const results = h("div", { class: "actions" });
  const pick = (title: string) =>
    button(title, async () => {
      await call("update_game_config", g.key, { matchTitle: title });
      toast(`${g.name} uses the save data of ${title}.`);
      await games(main, filter);
    });
  const searchButton = button("Search", async () => {
    const titles = await call<string[]>("search_titles", input.value);
    replace(results, ...(titles.length ? titles.slice(0, 8).map(pick) : [h("span", { class: "small" }, "Nothing found.")]));
  });
  return h(
    "div",
    {},
    h("div", { class: "actions" }, ...g.candidates.slice(0, 5).map(pick), input, searchButton),
    results,
  );
}

// Settings

async function settingsPage(main: HTMLElement): Promise<void> {
  const s = await call<Settings>("get_settings");
  const save = async (key: string, value: unknown, done: string) => {
    await call("set_setting", key, value);
    toast(done);
    await settingsPage(main);
  };
  const name = h("input", { type: "text", value: s.deviceName, maxlength: "40", "aria-label": "Device name" }) as HTMLInputElement;
  const idle = h("input", { type: "number", min: "10", max: "240", value: String(s.idleSyncMinutes), "aria-label": "Minutes between syncs" }) as HTMLInputElement;
  const channel = h(
    "select",
    { "aria-label": "Update channel" },
    h("option", { value: "stable", selected: s.updateChannel === "stable" }, "Stable releases"),
    h("option", { value: "prerelease", selected: s.updateChannel === "prerelease" }, "Test releases too"),
  ) as HTMLSelectElement;
  const toasts = h("input", { type: "checkbox", checked: s.toastOnSync, "aria-label": "Notify after each sync" }) as HTMLInputElement;
  toasts.addEventListener("change", () => void save("toastOnSync", toasts.checked, "Saved.").catch(fail));
  channel.addEventListener("change", () => void save("updateChannel", channel.value, "Saved.").catch(fail));
  replace(
    main,
    h("h1", {}, "Settings"),
    s.readOnly ? h("p", { class: "warn" }, "A newer Keepsake wrote these settings, so they are read-only here. Update Keepsake.") : null,
    h(
      "div",
      { class: "card" },
      h("h2", {}, "This device"),
      h("p", { class: "small" }, "Shown on your other devices, in History and in conflicts."),
      h(
        "div",
        { class: "actions" },
        name,
        button("Save name", async () => save("deviceName", name.value, "Device name saved.")),
      ),
    ),
    h(
      "div",
      { class: "card" },
      h("h2", {}, "Syncing"),
      h("p", { class: "small" }, "While no game runs, Keepsake checks for saves from your other devices this often (10 to 240 minutes)."),
      h(
        "div",
        { class: "actions" },
        idle,
        button("Save", async () => save("idleSyncMinutes", Number(idle.value), "Saved.")),
      ),
      h("label", { class: "switch" }, toasts, " Notify after each sync"),
    ),
    h(
      "div",
      { class: "card" },
      h("h2", {}, "Updates"),
      h("label", {}, "Channel ", channel),
    ),
    h(
      "div",
      { class: "card" },
      h("h2", {}, "Safety checks"),
      h(
        "p",
        { class: "small" },
        `A sync stops and asks you when it would remove more than ${s.gateMaxRemovedPercent}% of a game's save files, or shrink them by more than ${s.gateMaxSizeDropPercent}%. These limits can only be made stricter, in Gaming Mode's Settings.`,
      ),
    ),
  );
}

function fail(error: unknown): void {
  toast(error instanceof ApiError ? error.message : "Something went wrong");
}

// Import from Ludusavi

let importTimer: number | undefined;

async function importPage(main: HTMLElement): Promise<void> {
  window.clearTimeout(importTimer);
  const status = await call<ImportAllStatus>("ludusavi_import_status");
  const root = h("input", { type: "text", value: "~/ludusavi-backup", "aria-label": "Ludusavi backup folder", size: "40" }) as HTMLInputElement;
  const found = h("div", {});
  replace(
    main,
    h("h1", {}, "Import from Ludusavi"),
    h("p", {}, "Brings your Ludusavi backups into Keepsake's history, so nothing from before is lost. Your Ludusavi backups are only read, never changed."),
    status.running || status.total ? importProgress(status, main) : null,
    h(
      "div",
      { class: "actions" },
      root,
      button("Find backups", async () => {
        const result = await call<{ root: string; games: LudusaviGame[] }>("ludusavi_scan", root.value);
        replace(
          found,
          h("p", {}, `${result.games.length} games with backups in ${result.root}.`),
          result.games.length
            ? h(
                "table",
                {},
                h("tr", {}, h("th", {}, "Game"), h("th", {}, "Backups"), h("th", {}, "Note")),
                ...result.games.map((g) =>
                  h("tr", {}, h("td", {}, g.name), h("td", {}, String(g.backups.length)), h("td", {}, g.error ?? (g.inManifest ? "" : "not in the save database"))),
                ),
              )
            : null,
          result.games.length
            ? h(
                "div",
                { class: "actions" },
                button(
                  "Import the latest backup of each game",
                  async () => {
                    await call("ludusavi_import_all", result.root, "latest");
                    await importPage(main);
                  },
                  "primary",
                ),
                button("Import every backup", async () => {
                  await call("ludusavi_import_all", result.root, "all");
                  await importPage(main);
                }),
              )
            : null,
        );
      }),
    ),
    found,
  );
  if (status.running) {
    importTimer = window.setTimeout(() => {
      if (document.getElementById("nav-import")?.getAttribute("aria-current") === "true") void importPage(main);
    }, 2000);
  }
}

function importProgress(status: ImportAllStatus, main: HTMLElement): HTMLElement {
  const summary = Object.entries(status.summary)
    .map(([verdict, count]) => `${count} ${verdict}`)
    .join(", ");
  return h(
    "div",
    { class: "card" },
    h("h2", {}, status.running ? "Importing" : status.cancelled ? "Import stopped" : "Import finished"),
    h("p", {}, `${status.done} of ${status.total} games${status.current ? `, now ${status.current}` : ""}.`),
    summary ? h("p", { class: "small" }, summary) : null,
    status.running
      ? button("Stop importing", async () => {
          await call("ludusavi_import_cancel");
          await importPage(main);
        })
      : null,
  );
}

// Cloud sign-in: one button, the browser, done (ADR-0044)

const PROVIDERS: { id: "onedrive" | "gdrive"; label: string; page: string }[] = [
  { id: "onedrive", label: "OneDrive", page: "Microsoft" },
  { id: "gdrive", label: "Google Drive", page: "Google" },
];

async function cloud(main: HTMLElement): Promise<void> {
  const status = await call<CloudStatus>("cloud_status");
  const signedIn = { onedrive: status.onedriveSignedIn, gdrive: status.googleSignedIn };
  replace(
    main,
    h("h1", {}, "Cloud"),
    h("p", {}, `Snapshots go to ${status.name}.`),
    status.problem ? h("p", { class: "warn" }, `Needs attention: ${status.problem}`) : null,
    h(
      "ul",
      { class: "list" },
      ...PROVIDERS.map((p) =>
        h(
          "li",
          { class: "card" },
          h("h2", {}, p.label),
          h(
            "p",
            {},
            signedIn[p.id]
              ? "Signed in."
              : status.methods?.[p.id]?.browser
                ? `Not signed in. A ${p.page} page opens in a new tab: sign in and allow access for Keepsake.`
                : "Not signed in.",
          ),
          h(
            "div",
            { class: "actions" },
            signedIn[p.id]
              ? button("Sign out", async () => {
                  await call("sign_out", p.id);
                  await cloud(main);
                })
              : status.methods?.[p.id]?.browser
                ? signInButton(p.id, p.label, main)
                : h("span", { class: "small" }, "Sign-in for this service is not set up in this version."),
            signedIn[p.id] && status.store !== p.id
              ? button(`Use ${p.label} for snapshots`, async () => {
                  const checked = await call<{ ok: boolean; error?: string }>("test_cloud", p.id);
                  if (!checked.ok) {
                    toast(`${p.label} did not pass the check: ${checked.error ?? "unknown reason"}`);
                    return;
                  }
                  await call("set_setting", "snapshotStore", p.id);
                  await cloud(main);
                })
              : null,
          ),
        ),
      ),
    ),
  );
}

function signInButton(id: "onedrive" | "gdrive", label: string, main: HTMLElement): HTMLButtonElement {
  const element = h("button", { type: "button", class: "primary" }, `Sign in with ${label}`) as HTMLButtonElement;
  element.addEventListener("click", () => {
    // Opened now, while the click still counts, so the browser does not block it; filled in below.
    const tab = window.open("", "_blank");
    void act(element, async () => {
      try {
        const shown = await call<{ method?: string; authUrl?: string }>("start_signin", id, "browser");
        if (!shown.authUrl || !/^https:\/\/(login\.microsoftonline\.com|accounts\.google\.com)\//.test(shown.authUrl)) {
          throw new ApiError("The sign-in page is not a Microsoft or Google address.");
        }
        if (tab) {
          tab.opener = null; // the sign-in page can never reach this one
          tab.location.href = shown.authUrl;
        } else {
          window.open(shown.authUrl, "_blank", "noopener");
        }
        replace(main, h("h1", {}, "Cloud"), h("p", {}, "Finish signing in in the new tab. This page updates when you are done."));
      } catch (error) {
        tab?.close();
        throw error;
      }
    });
  });
  return element;
}

// Updates (the PC host updates itself, ADR-0043)

const updateRefusals: Record<string, string> = {
  "not-installed": "Keepsake is running from a folder, not installed, so it cannot update itself here.",
  "no-pc-package": "This release has no PC package.",
  "unsigned-release": "This release is not signed, so it is refused.",
  "bad-signature": "This release's signature is not valid, so it is refused.",
  "sums-missing-zip": "This release's checksums do not list the PC package.",
  offline: "GitHub could not be reached.",
  busy: "Keepsake is busy. Try again when it has finished.",
};

function refusal(result: PcResult): string {
  return result.detail ?? updateRefusals[result.reason ?? ""] ?? `Refused: ${result.reason ?? "unknown reason"}`;
}

function restartButton(): HTMLButtonElement {
  return button(
    "Restart Keepsake now",
    async () => {
      const result = await call<PcResult>("pc_restart");
      if (!result.ok) {
        toast(refusal(result));
        return;
      }
      replace(document.getElementById("main") as HTMLElement, h("h1", {}, "Restarting"), h("p", {}, "Keepsake opens again in a new tab in a few seconds. You can close this one."));
    },
    "primary",
  );
}

async function updates(main: HTMLElement, check?: UpdateCheck, installed?: string): Promise<void> {
  const status = await call<PcUpdateStatus>("pc_update_status");
  const latest = check?.latest;
  const offer = check?.updateAvailable && latest?.desktop_url ? latest : null;
  replace(
    main,
    h("h1", {}, "Updates"),
    h(
      "dl",
      { class: "facts" },
      h("dt", {}, "Running"),
      h("dd", {}, status.running),
      h("dt", {}, "Installed"),
      h("dd", {}, status.installed ? (status.current ?? "") : "Not installed (running from a folder)"),
      h("dt", {}, "Previous version"),
      h("dd", {}, status.previous ?? "None kept"),
    ),
    h("p", { class: "small" }, "Every update is checked against Keepsake's release signature before anything is installed. Your settings and saves are never touched."),
    check?.error ? h("p", { class: "warn" }, `Could not check: ${check.error}`) : null,
    check && !check.error && !offer ? h("p", {}, latest && check.updateAvailable ? `Keepsake ${latest.version} has no PC package yet.` : "Keepsake is up to date.") : null,
    installed ? h("p", {}, `Keepsake ${installed} is installed. It starts when Keepsake restarts.`) : null,
    h(
      "div",
      { class: "actions" },
      button("Check for updates", async () => updates(main, await call<UpdateCheck>("check_for_updates", true))),
      offer && status.installed
        ? button(
            `Install ${offer.version}`,
            async () => {
              const result = await call<PcResult>("pc_update_apply", offer.tag);
              if (!result.ok) {
                toast(refusal(result));
                return;
              }
              await updates(main, undefined, result.version);
            },
            "primary",
          )
        : null,
      installed || (status.installed && status.current !== status.running) ? restartButton() : null,
      status.installed && status.previous
        ? button(`Go back to ${status.previous}`, async () => {
            const result = await call<PcResult>("pc_rollback");
            if (!result.ok) {
              toast(refusal(result));
              return;
            }
            await updates(main, undefined, result.version);
          })
        : null,
    ),
  );
}

// The shell

const PAGES: Page[] = [
  { id: "overview", title: "Overview", render: overview },
  { id: "conflicts", title: "Conflicts", render: conflicts },
  { id: "games", title: "Games", render: (main) => games(main) },
  { id: "cloud", title: "Cloud", render: cloud },
  { id: "import", title: "Import", render: importPage },
  { id: "history", title: "History", render: history },
  { id: "health", title: "Health", render: health },
  { id: "modules", title: "Modules", render: modules },
  { id: "updates", title: "Updates", render: (main) => updates(main) },
  { id: "settings", title: "Settings", render: settingsPage },
];

async function show(id: string): Promise<void> {
  const page = PAGES.find((p) => p.id === id) ?? PAGES[0];
  const main = document.getElementById("main") as HTMLElement;
  document.querySelectorAll("nav button").forEach((b) => b.setAttribute("aria-current", String(b.id === `nav-${page.id}`)));
  replace(main, h("p", { class: "loading" }, "Loading"));
  try {
    await page.render(main);
  } catch (error) {
    replace(main, h("h1", {}, page.title), h("p", { class: "warn" }, error instanceof ApiError ? error.message : "Keepsake could not be reached."));
  }
}

function start(): void {
  const nav = document.getElementById("nav") as HTMLElement;
  if (!hasToken()) {
    replace(
      document.getElementById("main") as HTMLElement,
      h("h1", {}, "Open Keepsake from its launcher"),
      h("p", {}, "For your safety this page only works when Keepsake opens it, with its own one-time link."),
    );
    return;
  }
  replace(
    nav,
    ...PAGES.map((p) => {
      const item = h("button", { type: "button", id: `nav-${p.id}` }, p.title);
      item.addEventListener("click", () => void show(p.id));
      return item;
    }),
  );
  onEvents((event, args) => {
    if (event === "keepsake_toast" && typeof args[0] === "string") toast(args[0]);
    if (event === "keepsake_signin") {
      const result = args[0] as { status?: string; reason?: string } | undefined;
      toast(result?.status === "signed-in" ? "Signed in." : `Sign-in did not complete: ${result?.reason ?? "unknown reason"}`);
      if (document.getElementById("nav-cloud")?.getAttribute("aria-current") === "true") void show("cloud");
    }
  }, ["keepsake_toast", "keepsake_signin"]);
  void show(initialPage() ?? "overview");
}

start();
