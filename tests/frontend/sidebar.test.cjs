// The full page's sidebar (src/sidebar.ts, src/routeData.ts), compiled and loaded from KEEPSAKE_FRONTEND_OUT.
// v0.41.1: the sidebar is static. It takes no input, so no module status, however late, can change it.
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const out = process.env.KEEPSAKE_FRONTEND_OUT;
const { sidebarEntries, legacyRoutes } = require(path.join(out, "sidebar.js"));
const { LAYOUT, LEGACY, SECTION_IDS, pagePath, sectionPath, firstTab } = require(path.join(out, "routeData.js"));

const pages = (entries) => entries.filter((e) => e.kind === "page");

test("the sidebar takes no input and is the same every time", () => {
  assert.equal(sidebarEntries.length, 0);
  const first = sidebarEntries();
  for (let i = 0; i < 5; i++) assert.deepEqual(sidebarEntries(), first);
});

test("every section and every tab is there, in order, whatever module it belongs to", () => {
  const entries = pages(sidebarEntries());
  const expected = LAYOUT.flatMap((s) => s.tabs.map((t) => `${s.id}/${t.id}`));
  assert.deepEqual(entries.map((e) => `${e.section}/${e.tab}`), expected);
  assert.deepEqual([...new Set(entries.map((e) => e.section))], SECTION_IDS);
  for (const module of ["advisor", "replication", "installer", "device", "saves"]) {
    assert.ok(entries.some((e) => e.module === module), `${module} entries stay in the list`);
  }
});

test("titles and routes are unique, and each route names its section and tab", () => {
  const entries = pages(sidebarEntries());
  assert.equal(new Set(entries.map((e) => e.title)).size, entries.length);
  assert.equal(new Set(entries.map((e) => e.route)).size, entries.length);
  for (const e of entries) assert.equal(e.route, `/keepsake/${e.section}/${e.tab}`);
  for (const e of entries) assert.equal(Object.keys(e).includes("visible"), false);
});

test("one line between sections, never first, last or doubled", () => {
  const entries = sidebarEntries();
  assert.notEqual(entries[0].kind, "separator");
  assert.notEqual(entries[entries.length - 1].kind, "separator");
  entries.forEach((e, i) => assert.ok(!(e.kind === "separator" && entries[i + 1]?.kind === "separator")));
  assert.equal(entries.filter((e) => e.kind === "separator").length, LAYOUT.length - 1);
  entries.forEach((e, i) => {
    const next = entries[i + 1];
    if (e.kind === "page" && next?.kind === "page") assert.equal(e.section, next.section, "sections are separated by a line");
  });
});

test("pagePath falls back to the first tab", () => {
  assert.equal(pagePath("saves"), "/keepsake/saves/games");
  assert.equal(pagePath("saves", "nope"), "/keepsake/saves/games");
  assert.equal(pagePath("device", "reconnect"), "/keepsake/device/reconnect");
  assert.equal(firstTab("diagnostics"), "health");
});

test("old addresses redirect to a page, never to themselves or to another redirect", () => {
  const routes = legacyRoutes();
  const sidebar = new Set(pages(sidebarEntries()).map((e) => e.route));
  const olds = new Set(routes.map((r) => r.path));
  assert.equal(olds.size, routes.length);
  for (const r of routes) {
    const target = pagePath(r.section, r.tab);
    assert.ok(sidebar.has(target), `${r.path} goes to a sidebar page`);
    assert.ok(!olds.has(target), `${r.path} goes to another redirect`);
    assert.ok(!sidebar.has(r.path), `${r.path} is a sidebar page`);
  }
  for (const s of SECTION_IDS) assert.ok(olds.has(sectionPath(s)), `${s} (a page before v0.41.1) redirects`);
  const by = Object.fromEntries(routes.map((r) => [r.path, pagePath(r.section, r.tab)]));
  assert.equal(by["/keepsake/games"], "/keepsake/saves/games");
  assert.equal(by["/keepsake/devices"], "/keepsake/games-devices/moving");
  assert.equal(by["/keepsake/updates"], "/keepsake/settings/updates");
  assert.equal(by["/keepsake/settings"], "/keepsake/settings/general");
  for (const old of Object.keys(LEGACY)) assert.ok(olds.has(`/keepsake/${old}`), `${old} still opens`);
});
