// Settings, Help in the desktop app (R28, ADR-0090): the same user guide as Gaming Mode, built from
// docs/user by scripts/help.py. Text goes in through text nodes only, never as markup, and the indents
// are classes in app.css (the host's CSP allows no inline styles).
import { HELP, HelpBlock } from "./help.js";
import { h, replace } from "./dom.js";

/** "**bold**" marks as <b>; everything else as text. */
function rich(text: string): HTMLElement {
  const span = h("span");
  text.split("**").forEach((part, i) => span.append(i % 2 ? h("b", {}, part) : document.createTextNode(part)));
  return span;
}

function block(b: HelpBlock): HTMLElement {
  switch (b.k) {
    case "h":
      return h(`h${Math.min(b.l + 1, 4)}`, {}, rich(b.t));
    case "li":
      return h("p", { class: `help-item help-d${Math.min(b.d, 3)}` }, /^\d+\./.test(b.t) ? "" : "• ", rich(b.t));
    case "row":
      return h("p", { class: "small" }, rich(b.t));
    case "code":
      return h("pre", {}, b.t);
    default:
      return h("p", {}, rich(b.t));
  }
}

export async function helpPage(main: HTMLElement, topicId = HELP[0]?.id ?? ""): Promise<void> {
  const topic = HELP.find((t) => t.id === topicId) ?? HELP[0];
  const select = h("select", { "aria-label": "Topic" }, ...HELP.map((t) => h("option", { value: t.id, selected: t.id === topic?.id }, t.title))) as HTMLSelectElement;
  select.addEventListener("change", () => void helpPage(main, select.value));
  replace(
    main,
    h("h1", {}, "Help"),
    h("p", {}, "The user guide, also at github.com/breakmylegs/haversack. ", select),
    ...(topic ? topic.blocks.map(block) : [h("p", {}, "The guide is not included in this build.")]),
  );
}
