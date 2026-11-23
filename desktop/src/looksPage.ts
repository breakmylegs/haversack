// Device, Looks in the desktop app (R29 stage 1, ADR-0091): the same as Gaming Mode's page.
import { ApiError, call } from "./api.js";
import { h, replace } from "./dom.js";

type Kind = "boot" | "suspend" | "throbber";
interface Video {
  who: "steam" | "haversack" | "other";
  name: string | null;
}
interface Looks {
  enabled: boolean;
  animations: { videos: Record<Kind, Video>; blockedBy: string | null; steamFound: boolean };
  choices: { id: string; name: string; from: string }[];
  plugins: { css: boolean; audio: boolean; animations: boolean };
  themes: { name: string }[];
  sounds: { name: string }[];
}

const KINDS: [Kind, string][] = [
  ["boot", "Boot"],
  ["suspend", "Sleep"],
  ["throbber", "Sleep from the loading screen"],
];

function now(v: Video): string {
  if (v.who === "haversack") return `Now: ${v.name ?? "your video"}.`;
  if (v.who === "other") return "Now: a video put there by hand or by another tool. Choosing one keeps it, so Use Steam's own brings it back.";
  return "Now: Steam's own.";
}

export async function looksPage(main: HTMLElement, problem = ""): Promise<void> {
  const s = await call<Looks>("looks_status");
  const act = async (method: string, ...args: unknown[]) => {
    try {
      await call(method, ...args);
      await looksPage(main);
    } catch (error) {
      await looksPage(main, error instanceof ApiError ? error.message : "That did not work.");
    }
  };
  const rows = KINDS.map(([kind, label]) => {
    const v = s.animations.videos[kind];
    const select = h("select", { "aria-label": `${label} animation`, disabled: Boolean(s.animations.blockedBy) || !s.enabled || s.choices.length === 0 }, h("option", { value: "" }, s.choices.length ? "Choose a video" : "No WebM videos found"), ...s.choices.map((c) => h("option", { value: c.id }, `${c.name} (${c.from})`))) as HTMLSelectElement;
    select.addEventListener("change", () => {
      if (select.value) void act("looks_set_animation", kind, select.value);
    });
    const reset = v.who === "haversack" && s.enabled && !s.animations.blockedBy ? h("button", { onclick: () => void act("looks_reset_animation", kind) }, "Use Steam's own") : null;
    return h("div", { class: "card" }, h("h3", {}, label), h("p", {}, now(v)), s.animations.blockedBy ? null : h("p", {}, select, " ", reset));
  });
  replace(
    main,
    h("h1", {}, "Looks"),
    !s.enabled ? h("p", { class: "warn" }, "Looks is off. Turn it on in Settings, Modules.") : null,
    h(
      "p",
      {},
      s.animations.blockedBy
        ? `${s.animations.blockedBy} manages the animations on this device, so Haversack only shows them.`
        : "Steam plays these when the device starts and when it goes to sleep. Choose one of your own WebM videos (from your Videos or Downloads folder); the change shows the next time the device starts or sleeps.",
    ),
    ...rows,
    h("h2", {}, "Themes and sounds"),
    h("p", {}, s.plugins.css ? `CSS Loader themes: ${s.themes.map((t) => t.name).join(", ") || "none yet"}.` : "Themes come from CSS Loader, in Decky's store."),
    h("p", {}, s.plugins.audio ? `Audio Loader sound packs: ${s.sounds.map((p) => p.name).join(", ") || "none yet"}.` : "Sound packs come from Audio Loader, in Decky's store."),
    problem ? h("p", { class: "warn" }, problem) : null,
  );
}
