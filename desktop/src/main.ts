// Keepsake's desktop interface for PCs and Desktop Mode (ADR-0038, ADR-0040).
// Plain TypeScript and the DOM: no framework, no third-party code, nothing from another origin.

import { ApiError, call, hasToken, initialPage, onEvents } from "./api.js";
import { h, replace, size, when } from "./dom.js";
import type {
  ConflictDetails,
  ConflictEntry,
  HealthCheck,
  HistoryItem,
  ModuleStatus,
  PcResult,
  PcUpdateStatus,
  QamSummary,
  UpdateCheck,
} from "./types.js";

type Page = { id: string; title: string; render: (main: HTMLElement) => Promise<void> };

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
    ["Cloud", `${summary.store}${summary.signedIn ? ", signed in" : summary.store === "local" ? "" : ", not signed in"}`],
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
  const card = h(
    "div",
    { class: "card" },
    h("h2", {}, entry.name),
    h("p", {}, `${entry.conflict.heads.length} cloud version(s), ${entry.conflict.localFiles} files here.`),
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
  { id: "history", title: "History", render: history },
  { id: "health", title: "Health", render: health },
  { id: "modules", title: "Modules", render: modules },
  { id: "updates", title: "Updates", render: (main) => updates(main) },
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
  }, ["keepsake_toast", "keepsake_signin"]);
  void show(initialPage() ?? "overview");
}

start();
