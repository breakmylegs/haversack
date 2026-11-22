// Keepsake's desktop interface for PCs and Desktop Mode (ADR-0038, ADR-0040).
// Plain TypeScript and the DOM: no framework, no third-party code, nothing from another origin.

import { ApiError, call, hasToken, initialPage, onEvents } from "./api.js";
import { lineChart } from "./charts.js";
import { h, replace, size, when } from "./dom.js";
import { sortableTable } from "./table.js";
import type {
  ActivityEntry,
  CloudStatus,
  ConflictDetails,
  ConflictEntry,
  ConflictSide,
  AdvisorDesk,
  AdvisorSessionDesk,
  DeviceCheckDesk,
  DeviceCheckResultDesk,
  DeviceReadingsDesk,
  PerformanceDesk,
  ChargeLimitDesk,
  ControllersDesk,
  ControllerSettingsDesk,
  EmulatorSetupDesk,
  ReconnectDesk,
  FansDesk,
  QamShortcutsDesk,
  ReconnectDeviceDesk,
  ExtrasDesk,
  DeviceStatusDesk,
  FoundDevice,
  GameTransfer,
  LogRecordDesk,
  GameMatch,
  ImportAllStatus,
  LinkCheck,
  LudusaviGame,
  HealthCheck,
  HistoryItem,
  ModuleStatus,
  PairedDevice,
  Pairing,
  PcResult,
  PcUpdateStatus,
  QamSummary,
  ReplicationStatus,
  Settings,
  TransferJob,
  TransfersStatus,
  IncomingOffer,
  OffersStatus,
  GameLink,
  UpdateCheck,
} from "./types.js";

type Page = { id: string; title: string; group: string; render: (main: HTMLElement) => Promise<void> };

const storeNames: Record<string, string> = {
  local: "Test store on this device",
  onedrive: "OneDrive",
  gdrive: "Google Drive",
  webdav: "WebDAV",
  s3: "S3",
  direct: "Directly between my devices",
};

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

// "Newer save from <device>, 10 minutes ago" (ADR-0049).
function newerText(newer: { device: string | null; created: string | null }): string {
  const when = newer.created ? new Date(newer.created).toLocaleString() : "";
  return `Newer save from ${newer.device ?? "another device"}${when ? ` (${when})` : ""}`;
}
const getItText = "Get it now from Games.";

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
    ...(summary.newer ?? []).map((n) => h("p", { class: "newer" }, `${n.name}: ${newerText(n)}. ${getItText}`)),
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

function choices(info: ConflictDetails, main: HTMLElement): (HTMLElement | null)[] {
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
      h("tr", {}, h("th", {}, "Version"), h("th", {}, "Device"), h("th", {}, "Last changed"), h("th", {}, "Files"), h("th", {}, "Size")),
      ...sides.map((s) =>
        h(
          "tr",
          {},
          h("td", {}, s.side === "local" ? "This device" : "Cloud"),
          h("td", {}, s.device ?? ""),
          h("td", {}, s.created ? new Date(s.created).toLocaleString() : "unknown"),
          h("td", {}, `${s.files} (${s.changedFiles} changed)`),
          h("td", {}, size(s.bytes)),
        ),
      ),
    ),
    ...sides.map((s) => changeList(s)),
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

const changeWords: Record<string, string> = { added: "new", removed: "gone", changed: "changed" };

// The files each side added, removed or changed since the last shared save (ADR-0048). Shown, never picked.
function changeList(side: ConflictSide): HTMLElement | null {
  const changes = side.changes ?? [];
  if (!changes.length) return null;
  const title = side.side === "local" ? `On ${side.device ?? "this device"}` : `From ${side.device ?? "the cloud"}`;
  return h(
    "details",
    {},
    h("summary", {}, `${title}: ${changes.length}${changes.length === 200 ? " or more" : ""} files differ`),
    h("ul", { class: "changes" }, ...changes.map((c) => h("li", {}, `${changeWords[c.change] ?? c.change}: ${c.path.split("/").slice(1).join("/")}`))),
  );
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

// Activity: what Keepsake did, in plain words (ADR-0048)

async function activityPage(main: HTMLElement): Promise<void> {
  const entries = await call<ActivityEntry[]>("activity", 100);
  replace(
    main,
    h("h1", {}, "Activity"),
    entries.length
      ? h(
          "ul",
          { class: "list" },
          ...entries.map((e) =>
            h(
              "li",
              { class: e.level === "warn" ? "check warn" : "" },
              h("strong", {}, e.level === "warn" ? `Needs attention: ${e.text}` : e.text),
              h("p", { class: "small" }, e.time ? new Date(e.time).toLocaleString() : ""),
            ),
          ),
        )
      : h("p", { class: "empty" }, "Nothing yet. Syncs, restores and checkpoints appear here."),
  );
}

// Health and modules

async function health(main: HTMLElement): Promise<void> {
  const result = await call<{ checks: HealthCheck[]; summary: string }>("health_checks", true);
  replace(
    main,
    h("h1", {}, "Health"),
    h(
      "div",
      { class: "actions" },
      button("Check cloud integrity now", async () => {
        const report = await call<{ games: Record<string, { bad: string[]; missing: string[] }> }>("scrub_cloud", true);
        const damaged = Object.values(report.games).reduce((n, g) => n + g.bad.length + g.missing.length, 0);
        toast(damaged ? `${damaged} snapshots are damaged or missing. See Cloud integrity below.` : "Every snapshot is intact.");
        await health(main);
      }),
    ),
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

const kindText: Record<string, string> = {
  steam: "Steam game",
  shortcut: "Non-Steam game",
  heroic: "Heroic game",
  lutris: "Lutris game",
  bottles: "Bottles program",
  emulator: "Emulator",
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

// Games shown with their full card under the table row (layout v3, ADR-0073).
const openGames = new Set<string>();
let gameState = "all";

const GAME_STATES: Record<string, (g: GameMatch) => boolean> = {
  all: () => true,
  syncing: (g) => g.enabled,
  off: (g) => !g.enabled,
  choice: (g) => Boolean(g.proposal) || g.method === "ambiguous" || g.method === "none",
  newer: (g) => Boolean(g.newer),
};

async function games(main: HTMLElement, filter = ""): Promise<void> {
  const all = await call<GameMatch[]>("match_games");
  // Paired devices, for "Send to" on non-Steam games (ADR-0059). None while Replication is off.
  const peers = await call<ReplicationStatus>("replication_status").then((s) => s.peers, () => [] as PairedDevice[]);
  const shown = all.filter((g) => g.name.toLowerCase().includes(filter.toLowerCase()) && (GAME_STATES[gameState] ?? GAME_STATES.all)(g));
  const search = h("input", { type: "search", placeholder: "Find a game", value: filter, "aria-label": "Find a game" }) as HTMLInputElement;
  search.addEventListener("input", () => void games(main, search.value).then(() => {
    const again = document.querySelector<HTMLInputElement>('input[aria-label="Find a game"]');
    again?.focus();
    again?.setSelectionRange(again.value.length, again.value.length);
  }));
  const state = h("select", { "aria-label": "Show" }) as HTMLSelectElement;
  for (const [value, label] of [["all", "All games"], ["syncing", "Syncing"], ["off", "Not syncing"], ["choice", "Needs a choice"], ["newer", "Newer save elsewhere"]]) {
    const option = h("option", { value }, label) as HTMLOptionElement;
    option.selected = value === gameState;
    state.append(option);
  }
  state.addEventListener("change", () => {
    gameState = state.value;
    void games(main, filter);
  });
  // Bulk actions (ADR-0048): only shown games whose save data is known.
  const syncable = shown.filter((g) => !g.proposal && ["manual", "manual-key", "steam-id", "title"].includes(g.method));
  const bulk = (on: boolean) =>
    button(on ? "Sync all shown" : "Stop syncing all shown", async (self) => {
      const targets = syncable.filter((g) => g.enabled !== on);
      if (!targets.length) {
        toast(on ? "Every shown game already syncs." : "None of the shown games sync.");
        return;
      }
      const label = on ? `Sync ${targets.length} games: press again` : `Stop ${targets.length} games: press again`;
      if (self.textContent !== label) {
        self.textContent = label; // a second, explicit press, as for other choices that change many games
        return;
      }
      for (const g of targets) await call("update_game_config", g.key, { enabled: on });
      toast(on ? `${targets.length} games now sync.` : `${targets.length} games no longer sync.`);
      await games(main, filter);
    });
  replace(
    main,
    h("h1", {}, "Games"),
    h("p", {}, "Turn sync on for the games whose saves should follow you. Keepsake finds each game's saves from the Ludusavi manifest."),
    h("div", { class: "actions" }, search, state, syncable.length ? bulk(true) : null, syncable.length ? bulk(false) : null),
    shown.length
      ? sortableTable(
          "games",
          [
            { title: "Game", value: (g) => g.name, cell: (g) => h("strong", {}, g.name) },
            { title: "Kind", value: (g) => kindText[g.kind] ?? g.kind, cell: (g) => kindText[g.kind] ?? "Game" },
            { title: "Sync", value: (g) => (g.enabled ? 1 : 0), cell: (g) => (g.enabled ? "On" : "Off") },
            { title: "State", value: (g) => syncText[g.sync] ?? g.sync, cell: (g) => (g.newer ? `${syncText[g.sync] ?? g.sync}; newer elsewhere` : (syncText[g.sync] ?? g.sync)) },
            { title: "Save data", value: (g) => matchText[g.method] ?? g.method, cell: (g) => (g.proposal ? "Needs a choice" : (matchText[g.method] ?? g.method)) },
            {
              title: "",
              cell: (g) =>
                button(openGames.has(g.key) ? "Close" : "Details", async () => {
                  if (openGames.has(g.key)) openGames.delete(g.key);
                  else openGames.add(g.key);
                  await games(main, filter);
                }),
            },
          ],
          shown,
          (g) => (openGames.has(g.key) ? gameCard(g, main, filter, peers) : null),
        )
      : h("p", { class: "empty" }, filter || gameState !== "all" ? "No game matches." : "No games found yet."),
  );
}

function sendButtons(g: GameMatch, peers: PairedDevice[]): HTMLElement | null {
  if (g.kind !== "shortcut" || !peers.length) return null;
  return h(
    "div",
    { class: "actions" },
    ...peers.map((peer) =>
      button(`Send to ${peer.name}`, async () => {
        const ok = window.confirm(
          `Send ${g.name} to ${peer.name}? Keepsake checks it has space, then copies the game, its prefix, its compatibility tool and its artwork there and adds it to Steam. It starts by itself; either device can stop and remove it.`,
        );
        if (!ok) return;
        const r = await call<{ title: string; droppedOptions: string[] }>("replication_send", g.key, peer.id);
        const dropped = r.droppedOptions.length ? ` These launch options stay here: ${r.droppedOptions.join(" ")}.` : "";
        toast(`Preparing ${r.title} for ${peer.name}.${dropped}`);
      }),
    ),
  );
}

function gameCard(g: GameMatch, main: HTMLElement, filter: string, peers: PairedDevice[] = []): HTMLElement {
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
      `${kindText[g.kind] ?? "Game"}. ${syncText[g.sync] ?? g.sync}. Save data: ${
        g.title ? `${g.title}, ` : ""
      }${matchText[g.method] ?? g.method}.`,
    ),
    h("label", { class: "switch" }, toggle, " Sync this game"),
    sendButtons(g, peers),
    g.newer
      ? h(
          "div",
          { class: "actions" },
          h("span", { class: "newer" }, `${newerText(g.newer)}.`),
          button("Get it now", async () => {
            const r = await call<{ action: string; pending?: boolean }>("bring_newer", g.key);
            toast(
              r.action === "restored"
                ? `${g.name}: the newer save is in place. The one it replaced is kept in History.`
                : r.action === "conflict"
                  ? `${g.name} changed here too, so nothing was replaced. Open Conflicts to choose.`
                  : r.action === "offline"
                    ? "The cloud could not be reached. Try again later."
                    : r.pending
                      ? `Quit ${g.name} first, then try again.`
                      : `${g.name} is already up to date.`,
            );
            await games(main, filter);
          }),
        )
      : null,
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
  // "When saves differ" (ADR-0080): ask, or take the newest when it can be sure.
  const differ = h(
    "select",
    { "aria-label": "When saves differ" },
    h("option", { value: "ask", selected: (s.conflictPolicy ?? "ask") === "ask" }, "Ask me"),
    h("option", { value: "newest", selected: s.conflictPolicy === "newest" }, "Take the newest"),
  ) as HTMLSelectElement;
  differ.addEventListener("change", () => void save("conflictPolicy", differ.value, "Saved.").catch(fail));
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
      h("label", {}, "When saves differ ", differ),
      h("p", { class: "small" }, "Take the newest: when exactly two versions differ, their times are far enough apart and no clock looks wrong, Keepsake keeps the newer one and pins the other in History, with Undo."),
    ),
    h(
      "div",
      { class: "card" },
      h("h2", {}, "Updates"),
      h("label", {}, "Channel ", channel),
    ),
    exportCard(),
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

// Export (ADR-0050): plain zips to a folder you choose, so you are never locked in.
function exportCard(): HTMLElement {
  const folder = h("input", { type: "text", placeholder: "Folder, for example E:\\Backups", "aria-label": "Export folder", size: "40" }) as HTMLInputElement;
  const run = (scope: "latest" | "all", label: string) =>
    button(label, async () => {
      const result = await call<{ folder: string; games: number; snapshots: number }>("export_snapshots", folder.value, scope);
      toast(`Exported ${result.snapshots} snapshots of ${result.games} games to ${result.folder}.`);
    });
  return h(
    "div",
    { class: "card" },
    h("h2", {}, "Export snapshots"),
    h("p", { class: "small" }, "Copy your saves out as plain zip files, with a list of what is in each. Nothing in the folder is overwritten."),
    h("div", { class: "actions" }, folder, run("latest", "Export the latest of each game"), run("all", "Export every snapshot")),
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
    directCard(status, main),
  );
}

// Direct save sync between paired devices, with no cloud account (ADR-0061).
function directCard(status: CloudStatus, main: HTMLElement): HTMLElement {
  const inUse = status.store === "direct";
  const last = status.direct;
  return h(
    "section",
    { class: "card" },
    h("h2", {}, "Directly between my devices"),
    h(
      "p",
      {},
      "No account and no cloud: each device keeps its own copy of your saves' history, and paired devices fetch what they lack from each other. There is no copy away from your devices.",
    ),
    status.directReady ? null : h("p", { class: "warn" }, "Switch on Replication in Modules and pair your other device in Devices first."),
    inUse && last ? h("p", { class: "small" }, `Last sync: ${when(last.at)}, ${last.copied} new from ${last.peers} device(s).`) : null,
    h(
      "div",
      { class: "actions" },
      !inUse && status.directReady
        ? button("Use direct sync for snapshots", async () => {
            await call("set_setting", "snapshotStore", "direct");
            await cloud(main);
          })
        : null,
      inUse
        ? button("Sync now", async () => {
            const r = await call<{ copied: number; peers: number; unreachable: string[] }>("direct_sync_now");
            toast(`Fetched ${r.copied} new from ${r.peers} device(s).${r.unreachable.length ? ` Not reachable: ${r.unreachable.join(", ")}.` : ""}`);
            await cloud(main);
          })
        : null,
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

// Devices: Replication's links and pairing (ADR-0054, ADR-0056)

function pairingActive(p: Pairing): boolean {
  return ["connecting", "waiting-accept", "enter-code", "request", "show-code", "checking"].includes(p.state);
}

async function devices(main: HTMLElement, found: FoundDevice[] | null = null): Promise<void> {
  const status = await call<ReplicationStatus>("replication_status");
  const transfers = await call<TransfersStatus>("replication_transfers");
  const offered = await call<OffersStatus>("replication_offers");
  const linked = await call<GameLink[]>("replication_games");
  const again = (list: FoundDevice[] | null = found) => devices(main, list);
  if (!status.available) {
    replace(main, h("h1", {}, "Devices"), h("p", { class: "warn" }, "This device's Python cannot make Replication's encrypted link, so Replication stays off."));
    return;
  }
  const listener = status.listener;
  const address = h("input", { type: "text", "aria-label": "Device address", placeholder: "192.168.1.20" }) as HTMLInputElement;
  // Pairing by code (ADR-0070): the receiver accepts and shows a code; the requester types it.
  const pairingCards = status.pairings
    .filter((p) => pairingActive(p) || p.state === "failed" || p.state === "declined")
    .map((p) => {
      const who = p.peerName ?? p.address;
      const cancel = button("Cancel", async () => (await call("replication_cancel", p.id), await again()));
      if (p.state === "failed") return h("li", { class: "check warn" }, h("strong", {}, `Pairing with ${who} did not finish`), h("p", {}, p.reason ?? ""));
      if (p.state === "declined") return h("li", { class: "check warn" }, h("strong", {}, `Not paired with ${who}`), h("p", {}, p.reason ?? "Declined."));
      if (p.state === "request")
        return h(
          "li",
          { class: "check info" },
          h("strong", {}, `${who} wants to pair`),
          h("p", {}, `From ${p.address}. Accept only if you are pairing your own device right now.`),
          h(
            "div",
            { class: "actions" },
            button("Accept", async () => (await call("replication_answer", p.id, true), await again())),
            button("Decline", async () => (await call("replication_answer", p.id, false), await again())),
          ),
        );
      if (p.state === "show-code")
        return h("li", { class: "check info" }, h("strong", {}, `Code: ${p.code ?? ""}`), h("p", {}, `Type this code on ${who}.`), cancel);
      if (p.state === "enter-code") {
        const code = h("input", { type: "text", inputmode: "numeric", maxlength: "6", "aria-label": "Code" }) as HTMLInputElement;
        return h(
          "li",
          { class: "check info" },
          h("strong", {}, `${who} accepted. Enter the code shown on it.`),
          h("div", { class: "actions" }, code, button("Pair", async () => (await call("replication_enter_code", p.id, code.value), await again())), cancel),
        );
      }
      const text = p.state === "waiting-accept" ? `Waiting for ${who} to accept` : p.state === "checking" ? `Checking the code with ${who}` : `Connecting to ${who}`;
      return h("li", { class: "check info" }, h("strong", {}, text), p.state === "checking" ? null : cancel);
    });
  const choice = h("select", { "aria-label": "Listen on" }) as HTMLSelectElement;
  for (const option of [{ address: "", kind: "all" }, ...status.addressesAvailable]) {
    const label = option.address ? `${option.address}${option.kind === "overlay" ? " (VPN)" : ""}` : "All home network and VPN addresses";
    const item = h("option", { value: option.address }, label) as HTMLOptionElement;
    item.selected = option.address === status.addressChoice;
    choice.append(item);
  }
  choice.addEventListener("change", () => void call("replication_set_address", choice.value).then(() => again(), fail));
  replace(
    main,
    h("h1", {}, "Devices"),
    h("p", {}, "Keepsake links your own devices directly, on your home network or your own VPN. Nothing goes through the cloud. Pair each device once by checking that both screens show the same code."),
    transfersDashboard(offered.activity ?? [], main),
    offersCard(offered, main),
    linked.length ? linksCard(linked, main) : null,
    transfers.jobs.length ? transfersCard(transfers, main) : null,
    pairingCards.length ? h("ul", { class: "list" }, ...pairingCards) : null,
    h(
      "section",
      { class: "card" },
      h("h2", {}, "This device"),
      h(
        "p",
        {},
        listener.on
          ? `Listening on ${listener.addresses.join(", ") || "no address"}, port ${listener.port}. Only paired devices get in.`
          : "Other devices cannot reach this one. Switch it on to pair or to receive games.",
      ),
      status.discovery.problem ? h("p", { class: "warn" }, status.discovery.problem) : null,
      h(
        "div",
        { class: "actions" },
        button(listener.on ? "Stop listening" : "Let other devices reach this one", async () => {
          await call("replication_set_listener", !listener.on);
          await again();
        }),
      ),
      status.addressesAvailable.length > 1 ? h("label", {}, "Listen on ", choice) : null,
    ),
    h(
      "section",
      { class: "card" },
      h("h2", {}, "Pair a device"),
      h("div", { class: "actions" }, button("Find devices", async () => again(await call<FoundDevice[]>("replication_find")))),
      found && !found.length ? h("p", {}, "No devices answered. On the other device, let other devices reach it, or type its address below.") : null,
      found?.length
        ? h(
            "ul",
            { class: "list" },
            ...found.map((d) =>
              h(
                "li",
                {},
                h("strong", {}, d.name),
                ` ${d.address}${d.paired ? ", already paired" : ""} `,
                button("Pair", async () => {
                  await call("replication_pair", `${d.address.includes(":") ? `[${d.address}]` : d.address}:${d.port}`);
                  await again(null);
                }),
              ),
            ),
          )
        : null,
      h("label", {}, "Address ", address),
      h(
        "div",
        { class: "actions" },
        button("Pair by address", async () => {
          await call("replication_pair", address.value.trim());
          await again();
        }),
      ),
    ),
    h(
      "section",
      { class: "card" },
      h("h2", {}, "Paired devices"),
      status.peers.length ? h("ul", { class: "list" }, ...status.peers.map((peer) => peerItem(peer, main))) : h("p", {}, "None yet."),
    ),
  );
  const moving =
    transfers.jobs.some((j) => ["running", "verifying", "waiting"].includes(j.state)) ||
    (offered.activity ?? []).some((t) => MOVING_STAGES.includes(t.stage));
  if (status.pairings.some(pairingActive) || moving) {
    setTimeout(() => {
      if (document.getElementById("nav-devices")?.getAttribute("aria-current") === "true") void again().catch(() => undefined);
    }, 1000);
  }
}

const offerStateText: Record<string, string> = {
  offered: "waiting for your answer",
  transferring: "copying",
  registering: "adding it to Steam",
  done: "ready in your library",
  failed: "stopped with a problem",
};

async function applyUpdate(offer: IncomingOffer, main: HTMLElement): Promise<void> {
  try {
    await call("replication_apply_update", offer.id, false);
    toast(`Taking the update to ${offer.title}. Your saves and settings stay as they are.`);
  } catch (error) {
    const text = error instanceof ApiError ? error.message : "";
    if (!text.includes("changed on this device too")) throw error;
    const take = window.confirm(
      `${offer.title} changed on both devices. OK takes ${offer.from}'s copy of the game; Cancel keeps this device's copy and writes nothing. Your saves and settings stay either way.`,
    );
    if (take) await call("replication_apply_update", offer.id, true);
    else await call("replication_keep_mine", offer.id);
  }
  await devices(main);
}

const linkStateText: Record<string, string> = {
  "in-sync": "in step",
  "changed-here": "changed on this device",
  "update-available": "an update is waiting above",
  "both-changed": "changed on both devices: choose above",
  updating: "taking an update",
};

function linksCard(linked: GameLink[], main: HTMLElement): HTMLElement {
  return h(
    "section",
    { class: "card" },
    h("h2", {}, "Games kept in step"),
    h("p", {}, "Your saves and settings on each device are never replaced by an update."),
    h(
      "ul",
      { class: "list" },
      ...linked.map((link) => {
        const policy = h("select", { "aria-label": `Updates for ${link.title}` }) as HTMLSelectElement;
        for (const [value, label] of [["manual", "Ask me"], ["auto", "Take them by themselves"], ["off", "Off"]]) {
          const option = h("option", { value }, label) as HTMLOptionElement;
          option.selected = value === link.policy;
          policy.append(option);
        }
        policy.addEventListener("change", () => void call("replication_set_policy", link.id, policy.value).then(() => devices(main), fail));
        return h(
          "li",
          {},
          h("strong", {}, `${link.title}: ${linkStateText[link.state] ?? link.state}`),
          h(
            "div",
            { class: "actions" },
            h("label", {}, "Updates ", policy),
            button("Check now", async () => (await call("replication_check_game", link.id), toast("Checked."), await devices(main))),
            link.state === "changed-here"
              ? button("Send update", async () => (await call("replication_send_update", link.id), toast("The update is offered."), await devices(main)))
              : null,
          ),
        );
      }),
    ),
  );
}

const STAGE_TEXT: Record<GameTransfer["stage"], string> = {
  "checking-space": "Checking space",
  preparing: "Preparing",
  copying: "Copying",
  verifying: "Verifying",
  adding: "Adding to Steam",
  done: "Done",
  failed: "Failed",
  paused: "Paused",
  waiting: "Waiting",
};
const MOVING_STAGES = ["checking-space", "preparing", "copying", "verifying", "adding", "waiting"];

function gibText(bytes: number): string {
  return `${(bytes / 2 ** 30).toFixed(1)} GiB`;
}

function leftText(seconds: number | null): string {
  if (seconds === null) return "";
  if (seconds < 60) return "under a minute";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${Math.floor(seconds / 3600)} h ${Math.round((seconds % 3600) / 60)} min`;
}

// The transfer dashboard (ADR-0072): every game moving, either way, with its bar and Stop and remove.
function transfersDashboard(items: GameTransfer[], main: HTMLElement): HTMLElement | null {
  if (!items.length) return null;
  const again = () => devices(main);
  const actionsFor = (t: GameTransfer) =>
    h(
      "div",
      { class: "actions" },
      t.canStop
        ? button("Stop and remove", async () => {
            const where = t.direction === "receiving" ? "Everything this copy made on this device is deleted." : `${t.peer} is asked to delete everything this copy made there. The game here is not touched.`;
            if (!window.confirm(`Stop and remove ${t.title}? ${where}`)) return;
            await call("replication_stop_game", t.id);
            await again();
          })
        : null,
      t.canClear ? button("Clear", async () => (await call("replication_clear_game", t.id), await again())) : null,
    );
  return h(
    "section",
    { class: "card" },
    h("h2", {}, "Games moving between devices"),
    sortableTable(
      "transfers",
      [
        { title: "Game", value: (t) => t.title, cell: (t) => h("div", {}, h("strong", {}, t.title), t.reason ? h("div", { class: t.stage === "failed" ? "warn" : "" }, t.reason) : null) },
        { title: "Device", value: (t) => t.peer, cell: (t) => (t.direction === "sending" ? `To ${t.peer}` : `From ${t.peer}`) },
        { title: "Stage", value: (t) => STAGE_TEXT[t.stage], cell: (t) => STAGE_TEXT[t.stage] },
        { title: "Progress", value: (t) => t.percent, cell: (t) => h("span", {}, h("progress", { max: "100", value: String(t.percent), "aria-label": `${t.title} ${t.percent}%` }), ` ${t.percent}%`) },
        { title: "Done", value: (t) => t.done, cell: (t) => (t.total ? `${gibText(t.done)} of ${gibText(t.total)}` : "") },
        { title: "Speed", value: (t) => t.bytesPerSecond, cell: (t) => (t.stage === "copying" && t.bytesPerSecond ? `${(t.bytesPerSecond / 1e6).toFixed(0)} MB/s` : "") },
        { title: "Time left", value: (t) => t.secondsLeft ?? Number.MAX_SAFE_INTEGER, cell: (t) => (t.stage === "copying" ? leftText(t.secondsLeft) : "") },
        { title: "", cell: (t) => actionsFor(t) },
      ],
      items,
    ),
  );
}

// "Games on <device>", kept across the page's refreshes while a copy runs.
const peerGames: Record<string, { id: string; title: string }[]> = {};

function peerGamesList(peer: PairedDevice, main: HTMLElement): HTMLElement | null {
  const games = peerGames[peer.id];
  if (!games) return null;
  if (!games.length) return h("p", {}, `No non-Steam games on ${peer.name}.`);
  return h(
    "table",
    {},
    h("thead", {}, h("tr", {}, h("th", {}, `Games on ${peer.name}`), h("th", {}, ""))),
    h(
      "tbody",
      {},
      ...games.map((g) =>
        h(
          "tr",
          {},
          h("td", {}, g.title),
          h(
            "td",
            {},
            button("Get this game", async () => {
              if (!window.confirm(`Get ${g.title} from ${peer.name}? Keepsake checks there is space here first. Nothing here is replaced.`)) return;
              await call("replication_get_game", peer.id, g.id, g.title);
              toast(`${g.title} is coming from ${peer.name}.`);
              await devices(main);
            }),
          ),
        ),
      ),
    ),
  );
}

// Updates waiting for a choice. New games start copying by themselves (ADR-0072).
function offersCard(offered: OffersStatus, main: HTMLElement): HTMLElement | null {
  const waiting = offered.incoming.filter((o) => o.update && o.state === "offered");
  if (!waiting.length) return null;
  const again = () => devices(main);
  return h(
    "section",
    { class: "card" },
    h("h2", {}, "Updates from your other devices"),
    h(
      "ul",
      { class: "list" },
      ...waiting.map((offer) =>
        h(
          "li",
          {},
          h("strong", {}, `${offer.title} from ${offer.from}: ${offerStateText[offer.state] ?? offer.state}`),
          h(
            "p",
            {},
            [size(offer.bytes), offer.compatTool ? `uses ${offer.compatTool}` : "", offer.droppedOptions.length ? `launch options left on the other device: ${offer.droppedOptions.join(" ")}` : "", offer.reason ?? ""]
              .filter(Boolean)
              .join(". "),
          ),
          h(
            "div",
            { class: "actions" },
            offer.state === "offered" && offer.update ? button("Apply update", () => applyUpdate(offer, main), "primary") : null,
            offer.state === "offered" && offer.update
              ? button("Keep mine", async () => (await call("replication_keep_mine", offer.id), await again()))
              : null,
          ),
        ),
      ),
    ),
  );
}

function transferText(job: TransferJob): string {
  const percent = job.total ? Math.floor((job.received / job.total) * 100) : 0;
  const parts = [`${size(job.received)} of ${size(job.total)} (${percent}%)`];
  if (job.state === "running" && job.megabytesPerSecond) {
    parts.push(`${job.megabytesPerSecond} MB/s`);
    if (job.secondsLeft !== null) parts.push(`about ${Math.max(1, Math.round(job.secondsLeft / 60))} min left`);
  }
  if (job.reason) parts.push(job.reason);
  return parts.join(", ");
}

function transfersCard(transfers: TransfersStatus, main: HTMLElement): HTMLElement {
  const note = [transfers.waitingFor, transfers.sleepProblem].filter(Boolean).join(" ");
  return h(
    "section",
    { class: "card" },
    h("h2", {}, "Transfers"),
    note ? h("p", {}, note) : null,
    h(
      "ul",
      { class: "list" },
      ...transfers.jobs.map((job) =>
        h(
          "li",
          {},
          h("strong", {}, `${job.target}: ${job.state}`),
          h("p", {}, transferText(job)),
          h(
            "div",
            { class: "actions" },
            job.state === "running" || job.state === "waiting"
              ? button("Pause", async () => (await call("replication_pause", job.id), await devices(main)))
              : job.state === "paused" || job.state === "failed"
                ? button("Resume", async () => (await call("replication_resume", job.id), await devices(main)))
                : null,
            button("Stop and remove", async () => {
              const ok = window.confirm(
                "Stop and remove this transfer? Everything it copied so far is deleted. The game already on this device, if any, is not touched.",
              );
              if (!ok) return;
              await call("replication_stop", job.id);
              await devices(main);
            }),
          ),
        ),
      ),
    ),
  );
}

function peerItem(peer: PairedDevice, main: HTMLElement): HTMLElement {
  const note = h("p", {}, `Last seen ${when(peer.lastSeen)}${peer.address ? ` at ${peer.address}` : ""}`);
  return h(
    "li",
    {},
    h("strong", {}, peer.name),
    note,
    h(
      "div",
      { class: "actions" },
      button(`Games on ${peer.name}`, async () => {
        peerGames[peer.id] = await call<{ id: string; title: string }[]>("replication_peer_games", peer.id);
        await devices(main);
      }),
      button("Check", async () => {
        const r = await call<LinkCheck>("replication_check", peer.id);
        const slow = r.slow ? (r.overlay ? " Slow: your VPN may be relaying this link." : " Slow.") : "";
        note.textContent = r.ok ? `Reachable at ${r.address ?? ""}, ${r.rttMs ?? 0} ms.${slow}` : (r.reason ?? "Not reachable.");
      }),
      peer.canWake
        ? button("Wake", async () => {
            await call("replication_wake", peer.id);
            toast("Wake signal sent. A device asleep on Wi-Fi may not wake.");
          })
        : null,
      button(
        "Remove",
        async () => {
          if (!window.confirm(`Remove ${peer.name}? Its link key is deleted here, and it can no longer connect. Pair again to link it back.`)) return;
          await call("replication_remove", peer.id);
          toast("Device removed.");
          await devices(main);
        },
      ),
    ),
    peerGamesList(peer, main),
  );
}

// The shell

// Layout v3 (ADR-0073, docs/design/layout-v3.md): the seven sections of Gaming Mode, in the same
// order, each a group of pages. Install stays in Gaming Mode for now.
const PAGES: Page[] = [
  { id: "overview", title: "Overview", group: "", render: overview },
  { id: "advisor", title: "Advisor", group: "Play", render: advisorPage },
  { id: "games", title: "Games", group: "Saves", render: (main) => games(main) },
  { id: "conflicts", title: "Conflicts", group: "Saves", render: conflicts },
  { id: "history", title: "History", group: "Saves", render: history },
  { id: "activity", title: "Activity", group: "Saves", render: activityPage },
  { id: "import", title: "Import", group: "Saves", render: importPage },
  { id: "devices", title: "Moving games and devices", group: "Games and devices", render: (main) => devices(main) },
  { id: "emulators", title: "Emulators", group: "Games and devices", render: emulatorsPage },
  { id: "device", title: "Status", group: "Device", render: deviceStatusPage },
  { id: "power", title: "Power", group: "Device", render: powerPage },
  { id: "battery", title: "Battery", group: "Device", render: batteryPage },
  { id: "fans", title: "Fans", group: "Device", render: fansPage },
  { id: "controllers", title: "Controllers", group: "Device", render: controllersPage },
  { id: "reconnect", title: "Reconnect help", group: "Device", render: reconnectPage },
  { id: "other", title: "Other", group: "Device", render: extrasPage },
  { id: "settings", title: "General and sync", group: "Settings", render: settingsPage },
  { id: "cloud", title: "Cloud", group: "Settings", render: cloud },
  { id: "modules", title: "Modules", group: "Settings", render: modules },
  { id: "quick-menu", title: "Quick menu", group: "Settings", render: quickMenuPage },
  { id: "updates", title: "Updates", group: "Settings", render: (main) => updates(main) },
  { id: "health", title: "Health", group: "Diagnostics", render: health },
  { id: "checks", title: "Device checks", group: "Diagnostics", render: deviceChecksPage },
  { id: "logs", title: "Logs", group: "Diagnostics", render: logsPage },
];

// The settings search: every setting's label and the page it is on. Choosing one opens that
// page and highlights the setting.
const SETTINGS_INDEX: { label: string; page: string }[] = [
  ["Device name", "settings"], ["Background sync", "settings"], ["Show a message after each save", "settings"],
  ["Safety gates", "settings"], ["Refuse if more than", "settings"], ["Refuse if the total size", "settings"],
  ["Launch check timeout", "settings"], ["Steam games", "settings"], ["Registry keys", "settings"],
  ["Detect Steam Cloud", "settings"], ["Snapshot when the device sleeps", "settings"], ["Other launchers", "settings"],
  ["Save locations", "cloud"], ["OneDrive", "cloud"], ["Google Drive", "cloud"], ["WebDAV", "cloud"], ["S3", "cloud"],
  ["Sign in", "cloud"], ["Modules", "modules"], ["Replication", "modules"], ["Advisor", "modules"], ["Installer", "modules"],
  ["Pre-releases", "updates"], ["Check for updates", "updates"], ["Roll back", "updates"],
  ["Let other devices reach this one", "devices"], ["Pair a device", "devices"], ["Listen on", "devices"],
].map(([label, page]) => ({ label, page }));

function settingsSearch(): HTMLElement {
  const input = h("input", { type: "search", placeholder: "Search settings", "aria-label": "Search settings", list: "settings-index" }) as HTMLInputElement;
  const options = h("datalist", { id: "settings-index" }, ...SETTINGS_INDEX.map((s) => h("option", { value: s.label })));
  const go = async () => {
    const wanted = input.value.trim().toLowerCase();
    const hit = SETTINGS_INDEX.find((s) => s.label.toLowerCase() === wanted) ?? SETTINGS_INDEX.find((s) => s.label.toLowerCase().includes(wanted));
    if (!wanted || !hit) {
      if (wanted) toast("No setting by that name.");
      return;
    }
    await show(hit.page);
    const main = document.getElementById("main") as HTMLElement;
    const target = [...main.querySelectorAll("label, h2, h3, strong, th, button")].find((e) => e.textContent?.toLowerCase().includes(hit.label.toLowerCase()));
    if (target) {
      target.scrollIntoView({ block: "center" });
      target.classList.add("found");
      setTimeout(() => target.classList.remove("found"), 2500);
    }
  };
  input.addEventListener("change", () => void go());
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") void go();
  });
  return h("div", { class: "search" }, input, options);
}

// Play: Advisor, with the last sessions as charts (layout v3)
async function advisorPage(main: HTMLElement): Promise<void> {
  const view = await call<AdvisorDesk>("advisor_view");
  if (!view.running) {
    replace(main, h("h1", {}, "Advisor"), h("p", {}, "Switch on Advisor in Modules to see recommendations and session history here."));
    return;
  }
  const recent = [...(view.sessions?.recent ?? [])].reverse(); // oldest first, left to right
  const labels = recent.map((s) => new Date(s.start * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short" }));
  const pick = (f: (s: AdvisorSessionDesk) => number | null | undefined) => recent.map((s) => {
    const v = f(s);
    return typeof v === "number" ? Math.round(v * 10) / 10 : null;
  });
  const top = view.recommendations?.[0];
  const lines = top ? [...top.lines.power, ...top.lines.display, ...top.lines.scaling] : [];
  replace(
    main,
    h("h1", {}, "Advisor"),
    h("p", {}, view.game ? `For ${view.game.name}. Advisor only reads and suggests; it never changes a setting.` : "Start a game for advice about it. Advisor only reads and suggests."),
    lines.length ? h("section", { class: "card" }, h("h2", {}, "Suggested"), h("ul", {}, ...lines.map((l) => h("li", {}, l)))) : null,
    (view.sessions?.advice ?? []).length
      ? h("section", { class: "card" }, h("h2", {}, "From your sessions"), h("ul", {}, ...(view.sessions?.advice ?? []).map((a) => h("li", {}, a.text))))
      : null,
    h(
      "section",
      { class: "card charts" },
      h("h2", {}, `Last ${recent.length} sessions`),
      lineChart("Power", "W", labels, [
        { label: "Average", className: "series-1", points: pick((s) => s.watts?.socketAvg) },
        { label: "Peak", className: "series-2", points: pick((s) => s.watts?.socketPeak) },
      ]),
      lineChart("Temperature", "°C", labels, [
        { label: "CPU peak", className: "series-3", points: pick((s) => s.cpu?.tempPeak) },
        { label: "GPU peak", className: "series-4", points: pick((s) => s.gpu?.tempPeak) },
      ]),
      lineChart("Frame rate", "fps", labels, [
        { label: "Average", className: "series-1", points: pick((s) => s.fps?.avg) },
        { label: "1% low", className: "series-2", points: pick((s) => s.fps?.low1) },
      ]),
      lineChart("Battery", "% an hour", labels, [{ label: "Used", className: "series-3", points: pick((s) => s.battery?.percentPerHour) }]),
    ),
  );
}

// Device: Status (layout v3; the controls arrive with R21)
async function deviceStatusPage(main: HTMLElement): Promise<void> {
  const s = await call<DeviceStatusDesk>("device_status");
  const r = await call<DeviceReadingsDesk>("device_readings");
  const sensorRows = r.chips.flatMap((c) => [
    ...c.temps.map((t) => h("tr", {}, h("td", {}, c.name), h("td", {}, t.label), h("td", {}, `${t.value.toFixed(1)} °C`))),
    ...c.fans.map((f) => h("tr", {}, h("td", {}, c.name), h("td", {}, f.label), h("td", {}, `${f.value.toFixed(0)} RPM`))),
    ...c.power.map((p) => h("tr", {}, h("td", {}, c.name), h("td", {}, p.label), h("td", {}, `${p.value.toFixed(1)} W`))),
  ]);
  const battery = !s.battery.present ? "No battery: mains power." : `${s.battery.percent ?? "Unknown"}%${s.battery.mains ? ", on mains power" : ", on battery"}`;
  replace(
    main,
    h("h1", {}, `${s.vendor ? `${s.vendor} ` : ""}${s.model}`),
    h(
      "table",
      {},
      h("tbody", {},
        h("tr", {}, h("th", {}, "Profile"), h("td", {}, s.how === "generic" ? "Generic (no profile for this model)" : s.profile)),
        h("tr", {}, h("th", {}, "Processor"), h("td", {}, s.apu || "Unknown")),
        h("tr", {}, h("th", {}, "Power range"), h("td", {}, s.tdp.min != null && s.tdp.max != null ? `${s.tdp.min} to ${s.tdp.max} W` : "Unknown")),
        h("tr", {}, h("th", {}, "Battery"), h("td", {}, battery)),
      ),
    ),
    h("h2", {}, "Readings"),
    h(
      "table",
      {},
      h("tbody", {},
        h("tr", {}, h("th", {}, "Performance mode"), h("td", {}, r.profile ? `${r.profile.words} (${r.profile.current}); available: ${r.profile.choices.join(", ")}` : "Not exposed")),
        h("tr", {}, h("th", {}, "BIOS"), h("td", {}, r.bios.version ? `${r.bios.version}${r.bios.date ? `, ${r.bios.date}` : ""}` : "Unknown")),
        h("tr", {}, h("th", {}, "Processor"), h("td", {}, [r.cpu.online ? `${r.cpu.online} threads` : "", r.cpu.smt ? `SMT ${r.cpu.smt}` : "", r.cpu.boost == null ? "" : `boost ${r.cpu.boost ? "on" : "off"}`].filter(Boolean).join(", "))),
        h("tr", {}, h("th", {}, "Battery power"), h("td", {}, r.battery.watts != null ? `${r.battery.watts} W` : "Unknown")),
      ),
    ),
    sensorRows.length ? h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Chip"), h("th", {}, "Sensor"), h("th", {}, "Value"))), h("tbody", {}, ...sensorRows)) : h("p", { class: "small" }, "No sensors readable."),
    h("p", { class: "small" }, "Power, fan, battery, controller and display controls arrive here in the next releases."),
  );
  setTimeout(() => {
    if (document.getElementById("nav-device")?.getAttribute("aria-current") === "true") void deviceStatusPage(main).catch(() => undefined);
  }, 2000);
}

// Device: Power (R21 stage 2, ADR-0076): mode, TDP and CPU boost through steamos-manager
const MODE_TEXT: Record<string, string> = { "low-power": "Quiet", balanced: "Balanced", "balanced-performance": "Balanced plus", performance: "Performance", custom: "Custom" };

async function powerPage(main: HTMLElement): Promise<void> {
  const s = await call<PerformanceDesk>("device_performance");
  if (s.off || !s.available || !s.current) {
    replace(main, h("h1", {}, "Power"), h("p", {}, s.problem ?? "Not available on this device."));
    return;
  }
  const c = s.current;
  const locked = s.tools.length > 0;
  const apply = async (values: Record<string, unknown>) => {
    await call("device_apply", values, s.game);
    await powerPage(main);
  };
  const mode = h("select", { "aria-label": "Mode", disabled: locked }) as HTMLSelectElement;
  for (const m of c.profile?.available ?? []) {
    const option = h("option", { value: m }, MODE_TEXT[m] ?? m) as HTMLOptionElement;
    option.selected = m === c.profile?.current;
    mode.append(option);
  }
  mode.addEventListener("change", () => void apply({ mode: mode.value }).catch(fail));
  const low = Math.max(c.tdp?.min ?? 0, s.limits.min ?? 0);
  const high = Math.min(c.tdp?.max ?? 0, s.limits.max ?? 999);
  const tdp = h("input", { type: "range", min: String(low), max: String(high), step: "1", value: String(c.tdp?.value ?? low), "aria-label": "TDP", disabled: locked || !c.tdp }) as HTMLInputElement;
  const tdpText = h("span", {}, `${c.tdp?.value ?? ""} W`);
  tdp.addEventListener("input", () => (tdpText.textContent = `${tdp.value} W`));
  tdp.addEventListener("change", () => void apply({ tdp: Number(tdp.value) }).catch(fail));
  const boost = h("input", { type: "checkbox", checked: Boolean(c.boost), disabled: locked || c.boost === null, "aria-label": "CPU boost" }) as HTMLInputElement;
  boost.addEventListener("change", () => void apply({ boost: boost.checked }).catch(fail));
  replace(
    main,
    h("h1", {}, "Power"),
    h(
      "p",
      { class: locked ? "warn" : "" },
      locked
        ? `${s.tools.join(", ")} manages performance on this device, so Keepsake only shows it.`
        : s.game
          ? "Changes are kept for the game you are playing and applied each time it starts."
          : "Start a game to keep settings for it.",
    ),
    s.stopped ? h("p", { class: "warn" }, s.stopped) : null,
    h(
      "table",
      {},
      h("tbody", {},
        c.profile ? h("tr", {}, h("th", {}, "Mode"), h("td", {}, mode)) : null,
        c.tdp ? h("tr", {}, h("th", {}, "TDP"), h("td", {}, tdp, " ", tdpText)) : null,
        c.boost !== null ? h("tr", {}, h("th", {}, "CPU boost"), h("td", {}, h("label", { class: "switch" }, boost, " On"))) : null,
      ),
    ),
    s.game && s.profile ? h("div", { class: "actions" }, button("Forget this game's profile", async () => (await call("device_forget", s.game), await powerPage(main)))) : null,
    limitsSection(s, locked, apply),
  );
}

// Separate SPL, SPPT and FPPT (ADR-0084), through the Keepsake Helper.
function limitsSection(s: PerformanceDesk, locked: boolean, apply: (values: Record<string, unknown>) => Promise<void>): HTMLElement | null {
  const p = s.powerLimits;
  if (!p?.available || !p.ranges) return null;
  const r = p.ranges;
  if (!p.ready) {
    return h("p", { class: "small" }, `Power limits now: SPL ${r.spl.current} W, SPPT ${r.sppt.current} W, FPPT ${r.fppt.current} W. Changing them separately needs the Keepsake Helper (install it from Gaming Mode: Device, Reconnect help).`);
  }
  const words = { spl: "SPL, sustained", sppt: "SPPT, slow boost", fppt: "FPPT, fast boost" } as const;
  const inputs = (Object.keys(words) as (keyof typeof words)[]).map((key) => {
    const input = h("input", { type: "number", min: String(r[key].min), max: String(r[key].max), step: String(r[key].step), value: String(r[key].current), "aria-label": words[key], disabled: locked }) as HTMLInputElement;
    return [key, input] as const;
  });
  return h(
    "section",
    {},
    h("h2", {}, "Separate power limits"),
    h("p", { class: "small" }, "Each within the firmware's own range, rising from SPL to FPPT. Applying sets Custom mode; with a game running they are kept for that game."),
    h("table", {}, h("tbody", {}, ...inputs.map(([key, input]) => h("tr", {}, h("th", {}, words[key]), h("td", {}, input, " W"))))),
    h("div", { class: "actions" }, button("Apply the limits", async () => apply({ limits: Object.fromEntries(inputs.map(([key, input]) => [key, Number(input.value)])) }))),
  );
}

// Device: Battery (R21 stage 4, ADR-0077): the 80 percent charge limit
async function batteryPage(main: HTMLElement): Promise<void> {
  const s = await call<ChargeLimitDesk>("device_battery");
  const state = s.limited == null ? "unknown" : s.limited ? "on" : "off";
  const box = h("input", { type: "checkbox", checked: Boolean(s.limited), "aria-label": "Stop charging at 80%" }) as HTMLInputElement;
  box.addEventListener("change", () => void call("device_set_charge_limit", box.checked).then(() => batteryPage(main), fail));
  replace(
    main,
    h("h1", {}, "Battery"),
    h("p", {}, "Stopping at 80% keeps the battery healthier if the device is plugged in for long spells. It is Lenovo's only charge limit on the Legion Go and Go 2."),
    s.control === "steamos-manager"
      ? h("label", { class: "switch" }, box, " Stop charging at 80%")
      : h("p", { class: "warn" }, `Charge limit: ${state}. This device's steamos-manager does not let Keepsake change it. ${s.where ?? ""}`),
    s.firmware.chargeTypes ? h("p", { class: "small" }, `Firmware charge types: ${s.firmware.chargeTypes}`) : null,
  );
}

// Settings: Quick menu (ADR-0073 addendum). Drag the chosen shortcuts into order, or use the arrows;
// tick to add or remove. Saved at once; the Gaming Mode panel follows straight away.
const KIND_TEXT = { page: "Opens a page", action: "Runs here", status: "Status line" } as const;

async function quickMenuPage(main: HTMLElement): Promise<void> {
  const data = await call<QamShortcutsDesk>("qam_shortcuts");
  const offered = new Map(data.available.map((s) => [s.id, s]));
  const chosen = data.chosen.filter((id) => offered.has(id));
  const hidden = data.chosen.filter((id) => !offered.has(id)); // kept for another module or version
  const save = async (next: string[]) => {
    await call("set_setting", "qamShortcuts", [...next, ...hidden]);
    await quickMenuPage(main);
  };
  let dragged: number | null = null;
  const list = h("ol", { class: "shortcut-list" });
  chosen.forEach((id, index) => {
    const s = offered.get(id);
    if (!s) return;
    const item = h(
      "li",
      { draggable: "true", class: "shortcut" },
      h("span", { class: "drag-handle", "aria-hidden": "true" }, "⋮⋮ "),
      h("strong", {}, s.label),
      h("span", { class: "small" }, ` ${KIND_TEXT[s.kind]} `),
      button("Up", async () => {
        if (index > 0) await save(move(chosen, index, index - 1));
      }, "small"),
      button("Down", async () => {
        if (index < chosen.length - 1) await save(move(chosen, index, index + 1));
      }, "small"),
      button("Remove", async () => save(chosen.filter((c) => c !== id)), "small"),
    );
    item.addEventListener("dragstart", () => (dragged = index));
    item.addEventListener("dragover", (event) => event.preventDefault());
    item.addEventListener("drop", (event) => {
      event.preventDefault();
      if (dragged !== null && dragged !== index) void save(move(chosen, dragged, index)).catch(fail);
      dragged = null;
    });
    list.append(item);
  });
  const others = data.available.filter((s) => !chosen.includes(s.id));
  replace(
    main,
    h("h1", {}, "Quick menu"),
    h("p", {}, "What Keepsake's panel in the quick access menu shows, in order. Open Keepsake is always there, last."),
    chosen.length ? list : h("p", { class: "small" }, "No shortcuts chosen."),
    others.length ? h("h2", {}, "Add") : null,
    others.length
      ? h("ul", {}, ...others.map((s) => h("li", {}, button(`Add ${s.label}`, async () => save([...chosen, s.id]), "small"), h("span", { class: "small" }, ` ${KIND_TEXT[s.kind]}`))))
      : null,
    h("div", { class: "actions" }, button("Use the defaults", async () => save(data.defaults))),
  );
}

function move(list: string[], from: number, to: number): string[] {
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

// Device: Fans (R24, ADR-0085). The curve is an SVG whose points can be dragged with the mouse, or
// set in the table under it; Save sends it through the same checks as Gaming Mode.
const SVG = "http://www.w3.org/2000/svg";

function svg(tag: string, attrs: Record<string, string | number>): SVGElement {
  const element = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) element.setAttribute(k, String(v));
  return element;
}

async function fansPage(main: HTMLElement): Promise<void> {
  const s = await call<FansDesk>("fans_status");
  const again = () => fansPage(main);
  if (s.off) {
    replace(main, h("h1", {}, "Fans"), h("p", {}, s.problem ?? "Device controls are off."));
    return;
  }
  const d = s.device ?? {};
  const go2 = d.model === "go2" || d.model === "go2-beta";
  const others = [...(d.conflicts ?? []), ...(s.tools ?? [])];
  const now = h(
    "p",
    {},
    [
      s.temperature != null ? `${s.temperature.toFixed(0)} °C` : "no temperature",
      d.rpm != null ? `fan ${d.rpm} RPM` : "fan speed unknown",
      s.active ? `profile ${s.active}${s.target ? `, asking ${s.target} RPM` : ""}` : "firmware in control",
    ].join(", "),
  );
  const parts: (HTMLElement | null)[] = [h("h1", {}, "Fans"), now];
  if (!s.helper.ready) parts.push(h("p", { class: "small" }, "Changing the fan needs the Keepsake Helper (install it from Gaming Mode: Device, Reconnect help)."));
  if (others.length) parts.push(h("p", { class: "warn" }, `${others.join(", ")} controls the fan here; Keepsake only shows the readings.`));
  if (s.problem) parts.push(h("p", { class: "warn" }, s.problem));
  if (s.helper.ready && go2 && !d.validated) {
    parts.push(
      h("p", {}, `BIOS ${d.firmware?.bios ?? "?"} with EC ${d.firmware?.ec ?? "?"} is not on the checked list. The fan test asks for one speed for up to 15 seconds, checks the fan gets there and gives it back.`),
      h("div", { class: "actions" }, button("Run the fan test", async () => {
        const r = await call<{ passed: boolean }>("fans_selftest");
        toast(r.passed ? "The fan test passed." : "The fan test did not pass: Keepsake will not control this fan.");
        await again();
      })),
    );
  }
  if (s.helper.ready && go2 && d.validated && !others.length) {
    const enabled = h("input", { type: "checkbox", checked: s.settings.enabled, "aria-label": "Keepsake controls the fan" }) as HTMLInputElement;
    enabled.addEventListener("change", () => void call("fans_set_options", { enabled: enabled.checked }).then(again, fail));
    const smooth = h("input", { type: "checkbox", checked: s.settings.smooth, "aria-label": "Smooth curve" }) as HTMLInputElement;
    smooth.addEventListener("change", () => void call("fans_set_options", { smooth: smooth.checked }).then(again, fail));
    const select = h("select", { "aria-label": "Profile" }) as HTMLSelectElement;
    for (const name of Object.keys(s.settings.profiles)) {
      const option = h("option", { value: name }, name === s.settings.default ? `${name} (default)` : name) as HTMLOptionElement;
      option.selected = name === s.settings.default;
      select.append(option);
    }
    let points = (s.settings.profiles[select.value] ?? []).map((p) => [...p] as [number, number]);
    const width = 480, height = 240, pad = 30;
    const x = (t: number) => pad + ((t - 20) / 80) * (width - 2 * pad);
    const y = (r: number) => height - pad - ((r - s.limits.min) / (s.limits.max - s.limits.min)) * (height - 2 * pad);
    const chart = svg("svg", { viewBox: `0 0 ${width} ${height}`, width, height, class: "fan-curve", role: "img", "aria-label": "Fan curve" }) as SVGSVGElement;
    const table = h("tbody", {});
    const draw = () => {
      chart.replaceChildren(
        svg("rect", { x: pad, y: pad, width: width - 2 * pad, height: height - 2 * pad, fill: "none", stroke: "currentColor", "stroke-opacity": 0.3 }),
        svg("polyline", { points: points.map(([t, r]) => `${x(t)},${y(r)}`).join(" "), fill: "none", stroke: "currentColor", "stroke-width": 2 }),
        ...points.map(([t, r], i) => {
          const dot = svg("circle", { cx: x(t), cy: y(r), r: 7, fill: "currentColor", tabindex: 0, "aria-label": `Point ${i + 1}: ${t} °C, ${r} RPM` });
          dot.addEventListener("pointerdown", (event) => {
            const box = chart.getBoundingClientRect();
            const move = (e: PointerEvent) => {
              const t2 = Math.round(20 + ((e.clientX - box.left) * (width / box.width) - pad) / (width - 2 * pad) * 80);
              const r2 = Math.round((s.limits.min + ((height - pad - (e.clientY - box.top) * (height / box.height)) / (height - 2 * pad)) * (s.limits.max - s.limits.min)) / 100) * 100;
              const low = i > 0 ? points[i - 1] : [20, s.limits.min];
              const high = i < points.length - 1 ? points[i + 1] : [100, s.limits.max];
              points[i] = [Math.max(low[0] + (i > 0 ? 1 : 0), Math.min(high[0] - (i < points.length - 1 ? 1 : 0), t2)), Math.max(low[1], Math.min(high[1], r2))];
              draw();
            };
            const up = () => {
              chart.removeEventListener("pointermove", move);
              chart.removeEventListener("pointerup", up);
            };
            chart.setPointerCapture((event as PointerEvent).pointerId);
            chart.addEventListener("pointermove", move);
            chart.addEventListener("pointerup", up);
          });
          return dot;
        }),
      );
      table.replaceChildren(
        ...points.map(([t, r], i) => {
          const temp = h("input", { type: "number", min: "20", max: "100", value: String(t), "aria-label": `Point ${i + 1} temperature` }) as HTMLInputElement;
          const rpm = h("input", { type: "number", min: String(s.limits.min), max: String(s.limits.max), step: "100", value: String(r), "aria-label": `Point ${i + 1} speed` }) as HTMLInputElement;
          const update = () => {
            points[i] = [Number(temp.value), Number(rpm.value)];
            draw();
          };
          temp.addEventListener("change", update);
          rpm.addEventListener("change", update);
          return h("tr", {}, h("td", {}, `Point ${i + 1}`), h("td", {}, temp, " °C"), h("td", {}, rpm, " RPM"));
        }),
      );
    };
    select.addEventListener("change", () => {
      points = (s.settings.profiles[select.value] ?? []).map((p) => [...p] as [number, number]);
      draw();
    });
    draw();
    parts.push(
      h("label", { class: "switch" }, enabled, " Keepsake controls the fan (back to the firmware within seconds if Keepsake stops; full speed at 101 °C)"),
      h("label", { class: "switch" }, smooth, " Smooth curve (off: stepped)"),
      h("h2", {}, "Curve"),
      h("div", { class: "actions" }, h("label", {}, "Profile ", select)),
      chart as unknown as HTMLElement,
      h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Point"), h("th", {}, "Temperature"), h("th", {}, "Speed"))), table),
      h(
        "div",
        { class: "actions" },
        button("Save", async () => (await call("fans_save_profile", select.value, points, false), toast(`${select.value} saved.`), await again())),
        button("Make it the default", async () => (await call("fans_assign", "default", "", select.value), await again())),
        s.mode ? button(`Use in ${s.mode} mode`, async () => (await call("fans_assign", "mode", s.mode, select.value), await again())) : null,
        s.game != null ? button("Use for this game", async () => (await call("fans_assign", "game", String(s.game), select.value), await again())) : null,
      ),
    );
    const confirmBox = h("input", { type: "text", placeholder: "Type: I understand", "aria-label": "Confirm wider limits" }) as HTMLInputElement;
    parts.push(
      h("h2", {}, "Wider limits"),
      h("p", { class: "small" }, `Lets curves reach 5200 RPM, beyond Lenovo's own maximum: louder and more wear. The ${s.limits.min} RPM floor and the 101 °C failsafe always stay.`),
      s.settings.unlocked
        ? h("div", { class: "actions" }, button("Lock the limits again", async () => (await call("fans_set_options", { unlocked: false }), await again())))
        : h("div", { class: "actions" }, confirmBox, button("Unlock", async () => (await call("fans_set_options", { unlocked: true, confirm: confirmBox.value.trim() }), await again()))),
    );
  }
  if (s.helper.ready && d.model === "go1" && !others.length) {
    const full = h("input", { type: "checkbox", checked: s.settings.fullSpeed, disabled: !d.fullSpeedAttribute, "aria-label": "Full fan speed" }) as HTMLInputElement;
    full.addEventListener("change", () => void call("fans_set_options", { fullSpeed: full.checked }).then(again, fail));
    parts.push(
      h("label", { class: "switch" }, full, d.fullSpeedAttribute ? " Full fan speed (switches off by itself if Keepsake stops)" : " Full fan speed (needs kernel 7.2)"),
      h("p", { class: "small" }, "The Legion Go's own fan table can only be changed through acpi_call, a kernel module SteamOS does not include and Keepsake will not install."),
    );
  }
  if (s.helper.ready && (d.controlling || s.settings.enabled || s.settings.fullSpeed)) {
    parts.push(h("div", { class: "actions" }, button("Give the fan back to the firmware", async () => (await call("fans_hand_back"), await again()))));
  }
  replace(main, ...parts);
}

// Device: Controllers (R21 stage 5, ADR-0078): read-only
async function controllersPage(main: HTMLElement): Promise<void> {
  const s = await call<ControllersDesk>("device_controllers");
  const rows = (values: Record<string, string>, where: string) => Object.entries(values).map(([k, v]) => h("tr", {}, h("td", {}, where), h("td", {}, k), h("td", {}, v)));
  const settingRows = s.controllers.flatMap((c) => [...rows(c.settings, "controller"), ...rows(c.left, "left"), ...rows(c.right, "right"), ...rows(c.touchpad, "touchpad")]);
  replace(
    main,
    h("h1", {}, "Controllers"),
    h("h2", {}, "Batteries"),
    s.batteries.length
      ? h("table", {}, h("tbody", {}, ...s.batteries.map((b) => h("tr", {}, h("th", {}, b.name), h("td", {}, b.percent != null ? `${b.percent}%` : (b.level ?? "unknown")), h("td", {}, b.status ?? "")))))
      : h("p", { class: "small" }, "This system does not show them yet (the Legion controller driver arrives in kernel 7.1)."),
    settingRows.length ? h("h2", {}, "Settings the controllers report") : null,
    settingRows.length ? h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Part"), h("th", {}, "Setting"), h("th", {}, "Value"))), h("tbody", {}, ...settingRows)) : null,
    s.rings ? h("h2", {}, "Stick lights") : null,
    s.rings ? h("table", {}, h("tbody", {}, ...Object.entries(s.rings).map(([k, v]) => h("tr", {}, h("th", {}, k), h("td", {}, v))))) : null,
    s.tools.length ? h("p", {}, `Managed by ${s.tools.join(", ")}.`) : null,
    h("p", { class: "small" }, "Remap buttons, dead zones and gyro in Steam's controller settings."),
  );
  main.append(await controllerSettingsSection(() => controllersPage(main)));
}

// Games and devices: Emulators (R26 stage 1, ADR-0087), read-only. Key and firmware files are counted only.
async function emulatorsPage(main: HTMLElement): Promise<void> {
  const s = await call<EmulatorSetupDesk>("emulator_setup");
  const peers = (await call<{ peers: { id: string; name: string }[] }>("replication_status").catch(() => ({ peers: [] }))).peers;
  const peerSelect = h("select", { "aria-label": "Send to" }) as HTMLSelectElement;
  for (const p of peers) peerSelect.append(h("option", { value: p.id }, p.name));
  const keys = h("input", { type: "checkbox", "aria-label": "Also send firmware and keys" }) as HTMLInputElement;
  if (s.off) {
    replace(main, h("h1", {}, "Emulators"), h("p", {}, s.problem ?? "Replication is off."));
    return;
  }
  replace(
    main,
    h("h1", {}, "Emulators"),
    h("p", {}, s.setups.length ? `Set up with ${s.setups.join(" and ")}.` : "No EmuDeck or RetroDECK found."),
    s.emulators.length
      ? h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Emulator"), h("th", {}, "Type"), h("th", {}, "System"))), h("tbody", {}, ...s.emulators.map((e) => h("tr", {}, h("td", {}, e.name), h("td", {}, e.type), h("td", {}, e.system)))))
      : h("p", { class: "small" }, "No standalone emulators found."),
    s.games.length
      ? h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "System"), h("th", {}, "Game"), h("th", {}, "Files"), h("th", {}, "Size"), h("th", {}, ""))), h("tbody", {}, ...s.games.slice(0, 500).map((g) => h("tr", {}, h("td", {}, g.system), h("td", {}, g.name), h("td", {}, String(g.files)), h("td", {}, size(g.size)), h("td", {}, peers.length ? button("Send", async () => {
          const r = await call<{ parts: string[] }>("emulator_send", peerSelect.value, g.system, g.name, keys.checked);
          toast(`Getting ${g.name} ready to send (${r.parts.join(", ")}).`);
        }, "small") : "")))))
      : h("p", { class: "small" }, "No games found."),
    Object.keys(s.secrets).length
      ? h("p", {}, `Firmware, BIOS and keys: ${Object.entries(s.secrets).map(([k, n]) => `${n} for ${k}`).join(", ")}. Counted only; never read.`)
      : null,
    peers.length
      ? h("div", { class: "actions" }, h("label", {}, "Send to ", peerSelect), h("label", { class: "switch" }, keys, " Also send firmware and keys (only straight to your own paired device, stored there for your user only; never to the cloud)"))
      : h("p", { class: "small" }, "Pair your other handheld to send games to it."),
  );
}

// Changing the controllers and the stick lights (ADR-0086), through the Keepsake Helper.
const CONTROLLER_CHOICES: Record<string, [string, string[]]> = {
  mode: ["Controller mode", ["xinput", "dinput"]],
  os_mode: ["Button chords for", ["linux", "windows"]],
  rumble_intensity: ["Rumble", ["off", "low", "medium", "high"]],
  fps_mode_dpi: ["FPS mode mouse DPI", ["500", "800", "1200", "1800"]],
  "left_handle/rumble_mode": ["Left rumble style", ["standard", "fps", "racing", "spg", "rpg"]],
  "right_handle/rumble_mode": ["Right rumble style", ["standard", "fps", "racing", "spg", "rpg"]],
  "left_handle/auto_sleep_time": ["Left controller sleeps after (minutes, 0 never)", ["0", "5", "10", "15", "30", "60"]],
  "right_handle/auto_sleep_time": ["Right controller sleeps after (minutes, 0 never)", ["0", "5", "10", "15", "30", "60"]],
  "left_handle/imu_enabled": ["Left controller gyro", ["true", "false"]],
  "touchpad/enabled": ["Touchpad", ["true", "false"]],
  "touchpad/vibration_enabled": ["Touchpad haptics", ["true", "false"]],
  "touchpad/vibration_intensity": ["Touchpad haptic strength", ["off", "low", "medium", "high"]],
  "led/enabled": ["Stick lights", ["true", "false"]],
  "led/effect": ["Light effect", ["monocolor", "breathe", "chroma", "rainbow"]],
};

async function controllerSettingsSection(again: () => Promise<void>): Promise<HTMLElement> {
  const s = await call<ControllerSettingsDesk>("controller_settings_status");
  const box = h("section", {}, h("h2", {}, "Change the controllers"));
  if (s.off || !s.present) {
    box.append(h("p", { class: "small" }, "Needs the Legion controllers on the kernel's hid-lenovo-go driver (kernel 7.1 and later)."));
    return box;
  }
  if (!s.helper.ready) {
    box.append(h("p", { class: "small" }, "Needs the Keepsake Helper (install it from Gaming Mode: Device, Reconnect help)."));
    return box;
  }
  if (s.tools.hhd) {
    box.append(h("p", { class: "warn" }, "Handheld Daemon manages the controllers here, so Keepsake only shows their settings."));
    return box;
  }
  const keep = h("input", { type: "checkbox", checked: true, "aria-label": "Keep my changes" }) as HTMLInputElement;
  const set = (values: Record<string, unknown>) => call("controller_settings_set", values, keep.checked).then(again, fail);
  const current = s.current ?? {};
  const rows = Object.entries(CONTROLLER_CHOICES)
    .filter(([key]) => s.allowed.includes(key) && current[key] !== undefined)
    .map(([key, [label, options]]) => {
      const select = h("select", { "aria-label": label }) as HTMLSelectElement;
      for (const o of options) {
        const option = h("option", { value: o }, o) as HTMLOptionElement;
        option.selected = o === current[key];
        select.append(option);
      }
      select.addEventListener("change", () => void set(key.startsWith("led/") ? { "led/mode": "custom", [key]: select.value } : { [key]: select.value }));
      return h("tr", {}, h("th", {}, label), h("td", {}, select));
    });
  const sliders = (["led/brightness", "led/speed"] as const)
    .filter((key) => current[key] !== undefined)
    .map((key) => {
      const input = h("input", { type: "range", min: "0", max: "100", step: "5", value: current[key], "aria-label": key }) as HTMLInputElement;
      input.addEventListener("change", () => void set({ [key]: Number(input.value) }));
      return h("tr", {}, h("th", {}, key === "led/brightness" ? "Light brightness" : "Light speed"), h("td", {}, input));
    });
  const colour = (current["led/multi_intensity"] ?? "").split(" ").map(Number);
  const colourInputs = ["Red", "Green", "Blue"].map(
    (name, i) => h("input", { type: "number", min: "0", max: "100", value: String(colour[i] ?? 0), "aria-label": name }) as HTMLInputElement,
  );
  box.append(
    s.tools.inputplumber ? h("p", { class: "small" }, "InputPlumber manages the button chords and touchpad haptics here, so those are left to it.") : h("span", {}),
    h("label", { class: "switch" }, keep, " Keep my changes (applied again when the controller reconnects or the device wakes)"),
    h("table", {}, h("tbody", {}, ...rows, ...sliders)),
    current["led/multi_intensity"] !== undefined
      ? h("div", { class: "actions" }, ...colourInputs, button("Apply colour", async () => set({ "led/mode": "custom", "led/multi_intensity": colourInputs.map((x) => Number(x.value)) })))
      : h("span", {}),
    Object.keys(s.kept).length ? h("div", { class: "actions" }, button("Forget kept settings", async () => (await call("controller_settings_forget"), await again()))) : h("span", {}),
  );
  return box;
}

// Device: Reconnect help (ADR-0082, ADR-0083). The same calls as Gaming Mode; installing the
// helper needs Decky's installer, so it stays in Gaming Mode.
async function reconnectPage(main: HTMLElement): Promise<void> {
  const s = await call<ReconnectDesk>("reconnect_status");
  const again = () => reconnectPage(main);
  if (!s.available) {
    replace(main, h("h1", {}, "Reconnect help"), h("p", {}, s.problem ?? "Bluetooth could not be read."));
    return;
  }
  const ready = Boolean(s.helper?.ready);
  const twice = (label: string, confirmLabel: string, work: () => Promise<unknown>) => {
    let armed = false;
    return button(label, async (self) => {
      if (!armed) {
        armed = true;
        self.textContent = confirmLabel;
        return;
      }
      await work();
      await again();
    });
  };
  const deviceRow = (d: ReconnectDeviceDesk) => {
    const help = h("input", { type: "checkbox", checked: d.help, disabled: d.transport === "le", "aria-label": `Reconnect help for ${d.name}` }) as HTMLInputElement;
    help.addEventListener("change", () => void call("reconnect_set_help", d.adapter, d.mac, help.checked, d.name).then(again, fail));
    const notes = [
      d.transport === "le" ? "Bluetooth LE (not supported yet)" : "",
      d.unregisteredPrefix ? "address not from a registered manufacturer (information only)" : "",
      d.suggest && !d.help ? `may need help: ${d.suggest.reason}` : "",
      d.last ? `last diagnosis: ${d.last.title}` : "",
    ].filter(Boolean);
    return h(
      "tr",
      {},
      h("td", {}, h("label", { class: "switch" }, help, ` ${d.name}`)),
      h("td", {}, [d.class, d.modalias].filter(Boolean).join(", ")),
      h("td", {}, d.adapterName),
      h("td", {}, d.connected ? "connected" : "not connected"),
      h("td", { class: "small" }, notes.join("; ")),
    );
  };
  const actions = (d: ReconnectDeviceDesk) => {
    const commit = h("input", { type: "checkbox", checked: d.commit, "aria-label": "Pair and commit" }) as HTMLInputElement;
    commit.addEventListener("change", () => void call("reconnect_set_option", d.adapter, d.mac, "commit", commit.checked).then(again, fail));
    let reversed = false;
    const order = h("input", { type: "checkbox", "aria-label": "Reversed key order" }) as HTMLInputElement;
    order.addEventListener("change", () => (reversed = order.checked));
    return h(
      "section",
      {},
      h("h2", {}, d.name),
      h("label", { class: "switch" }, commit, " Pair and commit (connect at once after pairing, so the controller saves it)"),
      h("p", { class: "small" }, "Reconnect: put the controller in pairing mode first (on a DualShock 4, hold Share and PS until the light flashes quickly). Diagnose: turn it off, wait 10 seconds, select Diagnose, then press its button once."),
      h(
        "div",
        { class: "actions" },
        button("Reconnect", async () => {
          const r = await call<{ message: string }>("reconnect_assist", d.adapter, d.mac);
          toast(r.message);
          await again();
        }),
        button("Diagnose", async () => {
          const r = await call<{ title: string; advice: string }>("reconnect_diagnose", d.adapter, d.mac);
          toast(`${r.title}. ${r.advice}`);
          await again();
        }),
        s.cableReady ? button("Read stored host over USB", async () => {
          const r = await call<{ read: { ok: boolean; message?: string; storesThisHandheld?: boolean } }>("reconnect_read_usb", d.adapter, d.mac);
          toast(r.read.ok ? (r.read.storesThisHandheld ? "The controller stores this handheld." : "The controller stores a different host.") : (r.read.message ?? "Not read."));
          await again();
        }) : null,
        d.captured ? button("Export report bundle", async () => {
          const r = await call<{ where: string }>("reconnect_export", d.adapter, d.mac, true);
          toast(`Saved: ${r.where}`);
        }) : null,
      ),
      d.last ? h("p", {}, `${d.last.title}. ${d.last.advice} Seen: ${d.last.evidence.join("; ") || "nothing"}.`) : null,
      ready
        ? h(
            "div",
            {},
            d.stored ? h("p", { class: "small" }, `This handheld: ${d.stored.linkKey ? `a key is stored (type ${d.stored.keyType ?? "unknown"})` : "no key"}, ${d.stored.trusted ? "trusted" : "not trusted"}, ${d.stored.services ? "services known" : "services not known yet"}${d.stored.backups ? `, ${d.stored.backups} backup(s)` : ""}.`) : null,
            h("label", { class: "switch" }, order, " Reversed key order (advanced, one controlled experiment)"),
            h(
              "div",
              { class: "actions" },
              s.cableReady
                ? twice("Cable pair", "Confirm: restart Bluetooth", async () => {
                    const r = await call<{ message: string }>("reconnect_cable_pair", d.adapter, d.mac, reversed ? "reversed" : "same");
                    toast(r.message);
                  })
                : h("span", { class: "small" }, "Connect the controller with a USB data cable for cable pairing."),
              d.stored?.backups ? twice("Restore backup", "Confirm: restart Bluetooth", () => call("reconnect_cable_restore", d.adapter, d.mac)) : null,
            ),
          )
        : null,
    );
  };
  const dry = h("input", { type: "checkbox", checked: Boolean(s.dryRun), "aria-label": "Dry run" }) as HTMLInputElement;
  dry.addEventListener("change", () => void call("reconnect_set_dry_run", dry.checked).then(again, fail));
  const devices = s.devices ?? [];
  const gate = s.sspGate;
  const showGate = ready && (gate?.on || devices.some((d) => d.help && d.last?.outcome === "O3"));
  const confirmBox = h("input", { type: "text", placeholder: "Type: I understand", "aria-label": "Confirm the SSP gate warning" }) as HTMLInputElement;
  replace(
    main,
    h("h1", {}, "Reconnect help"),
    h("p", {}, "For Bluetooth controllers, often clones, that pair once and then will not reconnect with their normal button. Turn help on only for the ones that need it: the others are never touched."),
    h(
      "p",
      { class: ready ? "" : "small" },
      ready
        ? `Keepsake Helper ready (version ${s.helper?.version}): cable pairing, the SSP gate and the Bluetooth capture are available.`
        : s.helper?.problem === "version"
          ? "The Keepsake Helper does not match this Keepsake. Update it from Gaming Mode: Device, Reconnect help."
          : "Cable pairing, the SSP gate and the Bluetooth capture need the Keepsake Helper. Install it from Gaming Mode: Device, Reconnect help.",
    ),
    devices.length
      ? h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Device"), h("th", {}, "Class and modalias"), h("th", {}, "Adapter"), h("th", {}, "State"), h("th", {}, "Notes"))), h("tbody", {}, ...devices.map(deviceRow)))
      : h("p", {}, "No paired devices. Pair a controller in Steam's Bluetooth settings first."),
    ...devices.filter((d) => d.help).map(actions),
    showGate
      ? h(
          "section",
          {},
          h("h2", {}, "SSP gate"),
          h("p", { class: "warn" }, "The SSP gate lowers Bluetooth security for the whole adapter, for every device. While it is on, new pairings use the older PIN method and Secure Connections protection is lost. SSP goes back on while pairing, when you switch the gate off, and if Keepsake stops."),
          h("p", {}, gate?.on ? `On (now: ${gate.state}).` : "Off."),
          gate?.on
            ? h("div", { class: "actions" }, button("Switch the SSP gate off", async () => (await call("reconnect_set_ssp_gate", false, "", ""), await again())), gate.state === "needs-confirm" ? button("Restart Bluetooth to turn SSP off", async () => (await call("reconnect_ssp_confirm"), await again())) : null)
            : h("div", { class: "actions" }, confirmBox, button("Turn the SSP gate on", async () => (await call("reconnect_set_ssp_gate", true, s.adapters?.[0]?.address ?? "", confirmBox.value.trim()), await again()))),
        )
      : null,
    h("label", { class: "switch" }, dry, " Dry run (log what would be done, without scanning or connecting)"),
    (s.actions ?? []).length
      ? h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "When"), h("th", {}, "Action"), h("th", {}, "Device"))), h("tbody", {}, ...(s.actions ?? []).slice(-10).reverse().map((a) => h("tr", {}, h("td", {}, a.at.replace("T", " ").replace("Z", "")), h("td", {}, a.action), h("td", {}, a.device ?? "")))))
      : null,
  );
}

// Device: Other (R21 stage 6, ADR-0079): Wi-Fi power saving and the BIOS check
async function extrasPage(main: HTMLElement): Promise<void> {
  const s = await call<ExtrasDesk>("device_extras");
  const wifi = h("input", { type: "checkbox", checked: Boolean(s.wifiPowerSaving), "aria-label": "Wi-Fi power saving" }) as HTMLInputElement;
  wifi.addEventListener("change", () => void call("device_set_wifi_power_saving", wifi.checked).then(() => extrasPage(main), fail));
  replace(
    main,
    h("h1", {}, "Other"),
    s.wifiPowerSaving !== null ? h("label", { class: "switch" }, wifi, " Wi-Fi power saving (saves battery; turn off if streaming stutters)") : h("p", { class: "small" }, "Wi-Fi power saving: not offered by this device's steamos-manager."),
    h("h2", {}, `BIOS ${s.bios.version ?? "unknown"}`),
    s.bios.notes.length ? h("ul", { class: s.bios.level === "ok" ? "" : "warn" }, ...s.bios.notes.map((n) => h("li", {}, n))) : h("p", {}, s.bios.known ? "No known problems with this BIOS." : "No BIOS notes for this model."),
    h("p", { class: "small" }, "Refresh rate, frame limit and brightness are in Steam's own settings; Keepsake leaves them to Steam."),
  );
}

// Diagnostics: Device checks, as in Gaming Mode (Run all, Export results)
async function deviceChecksPage(main: HTMLElement): Promise<void> {
  const data = await call<{ checks: DeviceCheckDesk[]; results: DeviceCheckResultDesk[] }>("device_checks");
  const results = new Map(data.results.map((r) => [r.id, r]));
  replace(
    main,
    h("h1", {}, "Device checks"),
    h("p", {}, "Each check tries one thing on this device and says what it found. Checks marked (both) need your other device too."),
    h(
      "div",
      { class: "actions" },
      button("Run all", async () => (await call("device_checks_run_all"), await deviceChecksPage(main)), "primary"),
      button("Export results", async () => {
        const r = await call<{ where: string }>("device_checks_export");
        toast(`Saved as ${r.where}.`);
      }),
    ),
    h(
      "ul",
      { class: "list" },
      ...data.checks.map((c) => {
        const r = results.get(c.id);
        return h(
          "li",
          { class: `check ${r ? (r.status === "pass" ? "ok" : r.status === "skip" ? "info" : r.status === "warn" ? "warn" : "fail") : ""}` },
          h("strong", {}, `${c.title}${c.needs === "both" ? " (both)" : ""}`),
          h("p", {}, r ? `${r.status.toUpperCase()}: ${r.found}` : "Not run yet."),
          button("Run", async () => (await call("device_check_run", c.id), await deviceChecksPage(main))),
        );
      }),
    ),
  );
}

// Diagnostics: Logs
async function logsPage(main: HTMLElement): Promise<void> {
  const records = await call<LogRecordDesk[]>("get_logs", 300);
  replace(
    main,
    h("h1", {}, "Logs"),
    h("p", {}, "Keepsake's own log, newest first. It never holds passwords, tokens or the contents of your saves."),
    sortableTable(
      "logs",
      [
        { title: "Time", value: (r) => r.ts, cell: (r) => r.ts.replace("T", " ").slice(0, 19) },
        { title: "Level", value: (r) => r.level, cell: (r) => r.level },
        { title: "Event", value: (r) => r.event, cell: (r) => r.event },
        { title: "Message", value: (r) => r.msg, cell: (r) => r.msg },
      ],
      [...records].reverse(),
    ),
  );
}

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
  const groups: HTMLElement[] = [];
  let current = "";
  for (const p of PAGES) {
    if (p.group !== current) {
      current = p.group;
      if (current) groups.push(h("h3", { class: "group" }, current));
    }
    const item = h("button", { type: "button", id: `nav-${p.id}` }, p.title);
    item.addEventListener("click", () => void show(p.id));
    groups.push(item);
  }
  replace(nav, settingsSearch(), ...groups);
  onEvents((event, args) => {
    if (event === "keepsake_toast" && typeof args[0] === "string") toast(args[0]);
    if (event === "keepsake_replication" && document.getElementById("nav-devices")?.getAttribute("aria-current") === "true") void show("devices");
    if (event === "keepsake_signin") {
      const result = args[0] as { status?: string; reason?: string; method?: string } | undefined;
      toast(result?.status !== "signed-in" ? `Sign-in did not complete: ${result?.reason ?? "unknown reason"}` : result.method === "phone" ? "Signed in with your phone. Keepsake is signed in; you can close any sign-in tab left open." : "Signed in.");
      if (document.getElementById("nav-cloud")?.getAttribute("aria-current") === "true") void show("cloud");
    }
  }, ["keepsake_toast", "keepsake_signin", "keepsake_replication"]);
  void show(initialPage() ?? "overview");
}

start();
