// The full page's menu (src/sidebar.ts, src/routeData.ts), compiled and loaded from KEEPSAKE_FRONTEND_OUT.
// The redesign (ADR-0095): the sidebar is the sections, static; each section's sub-pages are its own
// page's native tabs; old addresses and shortcut links land on the right section and sub-page. The strip
// (ADR-0098) left four sections; the addresses of removed ones open the nearest page that is left.
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const out = process.env.KEEPSAKE_FRONTEND_OUT;
const { sidebarEntries, pageRoutes, legacyRoutes } = require(path.join(out, "sidebar.js"));
const { LAYOUT, LEGACY, MOVED, SECTION_IDS, pagePath, sectionPath, firstPage, resolve } = require(path.join(out, "routeData.js"));

test("the sidebar has at most eight entries, takes no input and is the same every time", () => {
  assert.equal(sidebarEntries.length, 0);
  const first = sidebarEntries();
  assert.ok(first.length <= 8);
  assert.deepEqual(first.map((e) => e.section), SECTION_IDS);
  for (let i = 0; i < 5; i++) assert.deepEqual(sidebarEntries(), first);
  for (const e of first) {
    assert.equal(e.route, `/keepsake/${e.section}`);
    assert.equal(Object.keys(e).includes("visible"), false);
  }
});

test("every section has at most six sub-pages, with unique ids and titles", () => {
  for (const s of LAYOUT) {
    assert.ok(s.pages.length >= 1 && s.pages.length <= 6, `${s.id} has ${s.pages.length}`);
    assert.equal(new Set(s.pages.map((p) => p.id)).size, s.pages.length);
    assert.equal(new Set(s.pages.map((p) => p.title)).size, s.pages.length);
    for (const p of s.pages) assert.ok(p.about && p.parts.length >= 1, `${s.id}/${p.id}`);
  }
});

test("every sub-page is reachable at its own address, and modules that are off keep theirs", () => {
  const routes = pageRoutes();
  const expected = LAYOUT.flatMap((s) => s.pages.map((p) => `/keepsake/${s.id}/${p.id}`));
  assert.deepEqual(routes.map((r) => r.path), expected);
  assert.equal(new Set(routes.map((r) => r.path)).size, routes.length);
  const sections = new Set(sidebarEntries().map((e) => e.route));
  for (const r of routes) assert.ok(!sections.has(r.path), "a sub-page never shares its section's address");
  const modules = new Set(routes.flatMap((r) => r.modules));
  assert.deepEqual([...modules].sort(), ["core", "installer", "replication"]);
  assert.deepEqual(SECTION_IDS, ["install", "games-devices", "settings", "diagnostics"]);
});

test("the grouping review: merged and moved sub-pages are where the strip put them", () => {
  const parts = Object.fromEntries(LAYOUT.flatMap((s) => s.pages.map((p) => [`${s.id}/${p.id}`, p.parts.map((x) => x.id)])));
  assert.deepEqual(parts["settings/general"], ["general", "quick-menu"]);
  assert.deepEqual(parts["games-devices/games"], ["games"]);
  assert.deepEqual(Object.keys(parts), [
    "install/install",
    "games-devices/games",
    "games-devices/moving",
    "games-devices/devices",
    "games-devices/emulators",
    "settings/general",
    "settings/modules",
    "settings/updates",
    "settings/help",
    "diagnostics/checks",
    "diagnostics/tools",
    "diagnostics/logs",
  ]);
  const everyPart = Object.values(parts).flat();
  assert.equal(new Set(everyPart).size, everyPart.length, "each panel is on exactly one sub-page");
});

test("resolve follows moves and falls back to the first sub-page", () => {
  assert.deepEqual(resolve("settings", "quick-menu"), ["settings", "general"]);
  assert.deepEqual(resolve("settings", "cloud"), ["settings", "general"]);
  assert.deepEqual(resolve("diagnostics", "health"), ["diagnostics", "checks"]);
  assert.deepEqual(resolve("games-devices", "disk"), ["games-devices", "games"]);
  assert.deepEqual(resolve("games-devices", "nope"), ["games-devices", "games"]);
  assert.deepEqual(resolve("settings"), ["settings", "general"]);
  assert.equal(pagePath("diagnostics", "health"), "/keepsake/diagnostics/checks");
  assert.equal(pagePath("diagnostics"), "/keepsake/diagnostics/checks");
  assert.equal(firstPage("games-devices"), "games");
  assert.equal(sectionPath("install"), "/keepsake/install");
});

test("old addresses land on the right section and sub-page, never on another old one or a loop", () => {
  const routes = legacyRoutes();
  const pages = new Set(pageRoutes().map((r) => r.path));
  const sections = new Set(sidebarEntries().map((e) => e.route));
  const olds = new Set(routes.map((r) => r.path));
  assert.equal(olds.size, routes.length);
  for (const r of routes) {
    const target = pagePath(r.section, r.page);
    assert.ok(pages.has(target), `${r.path} goes to a sub-page`);
    assert.ok(!olds.has(target), `${r.path} goes to another redirect`);
    assert.ok(!pages.has(r.path) && !sections.has(r.path), `${r.path} is not a live address`);
  }
  const by = Object.fromEntries(routes.map((r) => [r.path, pagePath(r.section, r.page)]));
  assert.equal(by["/keepsake/games-devices/disk"], "/keepsake/games-devices/games");
  assert.equal(by["/keepsake/settings/quick-menu"], "/keepsake/settings/general");
  assert.equal(by["/keepsake/settings/sync"], "/keepsake/settings/general");
  assert.equal(by["/keepsake/games"], "/keepsake/games-devices/games");
  // The sections the strip removed (ADR-0098) open the nearest page that is left, never a blank one.
  assert.equal(by["/keepsake/saves"], "/keepsake/games-devices/games");
  assert.equal(by["/keepsake/play"], "/keepsake/install/install");
  assert.equal(by["/keepsake/device"], "/keepsake/diagnostics/checks");
  assert.equal(by["/keepsake/updates"], "/keepsake/settings/updates");
  for (const old of Object.keys(MOVED)) assert.ok(olds.has(`/keepsake/${old}`), `${old} still opens`);
  for (const old of Object.keys(LEGACY)) {
    if (!SECTION_IDS.includes(old)) assert.ok(olds.has(`/keepsake/${old}`), `${old} still opens`);
  }
});
