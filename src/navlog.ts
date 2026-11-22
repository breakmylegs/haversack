// The navigation recorder (v0.41.1): "Record navigation for 60 seconds" in Diagnostics, Tools.
//
// While it runs it notes, with times from the start:
// - Keepsake's own navigations and redirects;
// - mounts and unmounts of the full page and of each sidebar page;
// - every programmatic focus() call;
// - where focus goes, sidebar or page;
// - focus leaving the sidebar with no button pressed just before.
//
// Nothing personal: page ids, routes and element tags only, never text or names. The page is drawn
// in Steam's window, not the plugin's own context, so the listeners go on the full page root's
// document.

export interface NavEvent {
  t: number;
  kind: string;
  detail?: Record<string, string | number | boolean>;
}

const PROMPT_MS = 400; // focus that moves within this long after a button press was asked for
let start = 0;
let until = 0;
let events: NavEvent[] = [];
let root: HTMLElement | null = null;
let routeMounts = 0;

export function navlog(kind: string, detail?: NavEvent["detail"]): void {
  if (Date.now() < until && events.length < 5000) events.push({ t: Date.now() - start, kind, ...(detail ? { detail } : {}) });
}

export function recording(): boolean {
  return Date.now() < until;
}

/** The full page tells the recorder where it lives; called on mount and unmount. */
export function setNavRoot(element: HTMLElement | null): void {
  root = element;
  if (element) routeMounts += 1;
  navlog(element ? "route-mount" : "route-unmount", { count: routeMounts });
}

function region(target: EventTarget | null): string {
  const element = target as HTMLElement | null;
  if (!element || typeof element.closest !== "function") return "other";
  const page = element.closest("[data-keepsake-page]") as HTMLElement | null;
  if (page) return `page:${page.dataset.keepsakePage ?? ""}`;
  return element.closest("[data-keepsake-root]") ? "sidebar" : "other";
}

function describe(element: HTMLElement): string {
  return `${element.tagName.toLowerCase()}@${region(element)}`;
}

/** Record for ``seconds``, then hand the events over. Returns false if the page is not open. */
export function startRecording(seconds: number, done: (events: NavEvent[]) => void): boolean {
  const doc = root?.ownerDocument;
  const win = doc?.defaultView as (Window & typeof globalThis) | null | undefined;
  if (!doc || !win || recording()) return false;
  start = Date.now();
  until = start + seconds * 1000;
  events = [];
  let lastInput = 0;
  let lastRegion = "other";
  const proto = win.HTMLElement.prototype;
  const original = proto.focus;
  proto.focus = function (this: HTMLElement, options?: FocusOptions) {
    navlog("focus-call", { element: describe(this) });
    return original.call(this, options);
  };
  const input = (event: Event) => {
    lastInput = Date.now();
    navlog("input", { type: event.type });
  };
  const focusin = (event: Event) => {
    const now = region(event.target);
    const prompted = Date.now() - lastInput <= PROMPT_MS;
    navlog("focus", { region: now, prompted });
    if (lastRegion === "sidebar" && now.startsWith("page:") && !prompted) navlog("focus-left-sidebar-unprompted", { to: now });
    lastRegion = now;
  };
  const inputs = ["keydown", "click", "vgp_onbuttondown"];
  for (const name of inputs) doc.addEventListener(name, input, true);
  doc.addEventListener("focusin", focusin, true);
  navlog("start", { seconds, routeMounts });
  win.setTimeout(() => {
    navlog("stop");
    until = 0;
    proto.focus = original;
    for (const name of inputs) doc.removeEventListener(name, input, true);
    doc.removeEventListener("focusin", focusin, true);
    done(events);
  }, seconds * 1000);
  return true;
}

/** The short summary shown on screen and saved with the record. */
export function summarise(list: NavEvent[]): Record<string, number> {
  const count = (kind: string) => list.filter((e) => e.kind === kind).length;
  return {
    events: list.length,
    routeMounts: count("route-mount"),
    pageMounts: count("page-mount"),
    navigations: count("navigate"),
    redirects: count("redirect"),
    focusCalls: count("focus-call"),
    unpromptedLeaves: count("focus-left-sidebar-unprompted"),
  };
}
