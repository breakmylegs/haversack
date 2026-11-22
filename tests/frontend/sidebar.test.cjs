// v0.39.1: the full page's sidebar (src/sidebar.ts), compiled and loaded from KEEPSAKE_FRONTEND_OUT.
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const out = process.env.KEEPSAKE_FRONTEND_OUT;
const { sidebarEntries, sidebarKey, legacyRoutes } = require(path.join(out, "sidebar.js"));
const { LEGACY, sectionPath } = require(path.join(out, "routeData.js"));

const SECTIONS = [
  { id: "play", tabs: [{ id: "now", module: "core" }, { id: "advisor", module: "advisor" }] },
  { id: "saves", tabs: [{ id: "games", module: "saves" }, { id: "conflicts", module: "saves" }] },
  { id: "games-devices", tabs: [{ id: "moving", module: "replication" }, { id: "disk", module: "core" }] },
  { id: "device", tabs: [{ id: "status", module: "core" }, { id: "power", module: "device" }] },
  { id: "install", tabs: [{ id: "install", module: "installer" }] },
  { id: "settings", tabs: [{ id: "general", module: "core" }] },
  { id: "diagnostics", tabs: [{ id: "health", module: "core" }] },
];

const pages = (entries) => entries.filter((e) => e.kind === "page");

test("every entry maps to its own section, before and after the module state changes", () => {
  const before = sidebarEntries(SECTIONS, new Set(["saves"]));
  const after = sidebarEntries(SECTIONS, new Set(["saves", "advisor", "replication", "installer", "device"]));
  for (const entries of [before, after]) {
    for (const e of pages(entries)) {
      assert.equal(e.route, sectionPath(e.section)); // the route names the section: no position involved
    }
  }
  assert.deepEqual(pages(before).map((e) => e.section), ["play", "saves", "games-devices", "device", "settings", "diagnostics"]);
  assert.deepEqual(pages(after).map((e) => e.section), ["play", "saves", "games-devices", "device", "install", "settings", "diagnostics"]);
  assert.notEqual(sidebarKey(before), sidebarKey(after)); // a change rebuilds the sidebar, never reuses an index
  assert.equal(sidebarKey(after), sidebarKey(sidebarEntries(SECTIONS, new Set(["saves", "advisor", "replication", "installer", "device"]))));
});

test("tabs follow the modules", () => {
  const entries = pages(sidebarEntries(SECTIONS, new Set(["saves"])));
  assert.deepEqual(entries.find((e) => e.section === "play").tabs, ["now"]);
  assert.deepEqual(entries.find((e) => e.section === "games-devices").tabs, ["disk"]);
});

test("no hidden or legacy pages are in the sidebar", () => {
  const entries = sidebarEntries(SECTIONS, new Set(["saves", "advisor", "replication", "installer", "device"]));
  const legacy = new Set(legacyRoutes().map((r) => r.path));
  for (const e of pages(entries)) {
    assert.ok(!legacy.has(e.route), `${e.route} is an old route`);
    assert.equal(Object.keys(e).includes("visible"), false);
  }
  assert.equal(pages(entries).length, SECTIONS.length);
});

test("separators are never first, last or doubled", () => {
  for (const running of [new Set(), new Set(["saves"]), new Set(["saves", "installer"])]) {
    const entries = sidebarEntries(SECTIONS, running);
    assert.notEqual(entries[0].kind, "separator");
    assert.notEqual(entries[entries.length - 1].kind, "separator");
    entries.forEach((e, i) => assert.ok(!(e.kind === "separator" && entries[i + 1]?.kind === "separator")));
  }
});

test("each old route lands on the right section and tab", () => {
  const routes = legacyRoutes();
  // install, settings and diagnostics are section routes today: no redirect, or it would loop
  assert.deepEqual(routes.map((r) => r.path.split("/").pop()).sort(), Object.keys(LEGACY).filter((k) => !["install", "settings", "diagnostics"].includes(k)).sort());
  const sections = new Set(SECTIONS.map((s) => sectionPath(s.id)));
  for (const r of routes) assert.ok(!sections.has(r.path), `${r.path} would redirect a live section`);
  const by = Object.fromEntries(routes.map((r) => [r.path.split("/").pop(), [r.section, r.tab]]));
  assert.deepEqual(by.games, ["saves", "games"]);
  assert.deepEqual(by.devices, ["games-devices", "moving"]);
  assert.deepEqual(by.updates, ["settings", "updates"]);
  assert.deepEqual(by.storage, ["games-devices", "disk"]);
  assert.deepEqual(by.logs, ["diagnostics", "logs"]);
  for (const r of routes) assert.ok(r.path.startsWith("/keepsake/"));
});

test("a separator after the last section is dropped", () => {
  const short = [SECTIONS[0], SECTIONS[2]]; // ends with a section that has a separator after it
  const entries = sidebarEntries(short, new Set());
  assert.equal(entries[entries.length - 1].kind, "page");
});

test("a module that only adds tabs still rebuilds the sidebar", () => {
  const without = sidebarEntries(SECTIONS, new Set(["saves"]));
  const withAdvisor = sidebarEntries(SECTIONS, new Set(["saves", "advisor"]));
  assert.deepEqual(pages(without).map((e) => e.section), pages(withAdvisor).map((e) => e.section));
  assert.notEqual(sidebarKey(without), sidebarKey(withAdvisor));
});
