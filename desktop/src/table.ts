// A table you can sort by any column (layout v3, ADR-0073). Clicking a heading sorts by it;
// clicking it again reverses. The choice is kept per table while the page stays open, so a
// page that redraws itself every second keeps the order you picked.
import { h } from "./dom.js";

export interface Column<T> {
  title: string;
  value?: (row: T) => string | number;
  cell: (row: T) => Node | string | null;
  className?: string;
}

const chosen: Record<string, { column: number; down: boolean }> = {};

export function sortableTable<T>(id: string, columns: Column<T>[], rows: T[], extra?: (row: T) => HTMLElement | null): HTMLElement {
  const table = h("table", { class: "sortable", id });
  const draw = () => {
    const sort = chosen[id];
    const ordered = [...rows];
    if (sort && columns[sort.column]?.value) {
      const value = columns[sort.column].value as (row: T) => string | number;
      ordered.sort((a, b) => {
        const x = value(a);
        const y = value(b);
        const order = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), undefined, { sensitivity: "base" });
        return sort.down ? -order : order;
      });
    }
    const head = h(
      "tr",
      {},
      ...columns.map((c, index) => {
        if (!c.value) return h("th", {}, c.title);
        const mark = sort?.column === index ? (sort.down ? " ▼" : " ▲") : "";
        const label = h("button", { type: "button", class: "sort", "aria-label": `Sort by ${c.title}` }, `${c.title}${mark}`);
        label.addEventListener("click", () => {
          chosen[id] = { column: index, down: sort?.column === index ? !sort.down : false };
          draw();
        });
        return h("th", { "aria-sort": sort?.column === index ? (sort.down ? "descending" : "ascending") : "none" }, label);
      }),
    );
    const body = h("tbody", {});
    for (const row of ordered) {
      body.append(h("tr", {}, ...columns.map((c) => h("td", c.className ? { class: c.className } : {}, c.cell(row)))));
      const more = extra?.(row);
      if (more) body.append(h("tr", { class: "detail" }, h("td", { colspan: String(columns.length) }, more)));
    }
    table.replaceChildren(h("thead", {}, head), body);
  };
  draw();
  return table;
}
