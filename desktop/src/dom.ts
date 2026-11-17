// Tiny DOM helpers. Text always goes in through textContent, never innerHTML, so names from games,
// clouds or servers can never inject markup (the host's CSP blocks inline scripts as well).

type Child = Node | string | number | null | undefined | false;
type Attrs = Record<string, string | boolean | ((event: Event) => void) | undefined>;

export function h(tag: string, attrs: Attrs = {}, ...children: Child[]): HTMLElement {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value === undefined || value === false) continue;
    if (typeof value === "function") element.addEventListener(name.replace(/^on/, ""), value);
    else if (value === true) element.setAttribute(name, "");
    else element.setAttribute(name, value);
  }
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    element.append(typeof child === "string" || typeof child === "number" ? document.createTextNode(String(child)) : child);
  }
  return element;
}

export function replace(target: HTMLElement, ...children: Child[]): void {
  target.replaceChildren();
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    target.append(typeof child === "string" || typeof child === "number" ? document.createTextNode(String(child)) : child);
  }
}

export function when(seconds: number | null | undefined): string {
  if (!seconds) return "never";
  return new Date(seconds * 1000).toLocaleString();
}

export function size(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}
