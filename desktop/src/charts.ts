// Small line charts drawn as SVG (layout v3, ADR-0073): the Advisor's session history. No
// library and no inline styles (the page's policy forbids them): colours come from classes.

const NS = "http://www.w3.org/2000/svg";

function svg(tag: string, attrs: Record<string, string>, ...children: (Node | string)[]): SVGElement {
  const element = document.createElementNS(NS, tag);
  for (const [name, value] of Object.entries(attrs)) element.setAttribute(name, value);
  for (const child of children) element.append(typeof child === "string" ? document.createTextNode(child) : child);
  return element;
}

export interface Series {
  label: string;
  className: string; // series-1 to series-4 in app.css
  points: (number | null)[];
}

/** One chart: a value per session, oldest on the left. Gaps (null) break the line. */
export function lineChart(title: string, unit: string, labels: string[], series: Series[]): HTMLElement {
  const width = 640;
  const height = 220;
  const pad = { left: 44, right: 12, top: 16, bottom: 28 };
  const values = series.flatMap((s) => s.points).filter((v): v is number => v !== null && Number.isFinite(v));
  const figure = document.createElement("figure");
  figure.className = "chart";
  const caption = document.createElement("figcaption");
  caption.textContent = title;
  figure.append(caption);
  if (!values.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No readings yet.";
    figure.append(empty);
    return figure;
  }
  const top = Math.max(...values) * 1.1 || 1;
  const steps = Math.max(1, labels.length - 1);
  const x = (i: number) => pad.left + ((width - pad.left - pad.right) * i) / steps;
  const y = (v: number) => height - pad.bottom - ((height - pad.top - pad.bottom) * v) / top;
  const chart = svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": `${title}, ${unit}` });
  for (const fraction of [0, 0.5, 1]) {
    const value = top * fraction;
    chart.append(
      svg("line", { x1: String(pad.left), x2: String(width - pad.right), y1: String(y(value)), y2: String(y(value)), class: "grid" }),
      svg("text", { x: String(pad.left - 6), y: String(y(value) + 4), class: "axis", "text-anchor": "end" }, value.toFixed(value < 10 ? 1 : 0)),
    );
  }
  labels.forEach((label, i) => {
    if (labels.length <= 10 || i % Math.ceil(labels.length / 10) === 0) {
      chart.append(svg("text", { x: String(x(i)), y: String(height - 8), class: "axis", "text-anchor": "middle" }, label));
    }
  });
  for (const s of series) {
    let path = "";
    s.points.forEach((v, i) => {
      if (v === null || !Number.isFinite(v)) return;
      path += `${path && s.points[i - 1] !== null ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)} `;
    });
    if (path) chart.append(svg("path", { d: path.trim(), class: `line ${s.className}` }));
    s.points.forEach((v, i) => {
      if (v !== null && Number.isFinite(v)) {
        chart.append(svg("circle", { cx: x(i).toFixed(1), cy: y(v).toFixed(1), r: "3", class: `dot ${s.className}` }, svg("title", {}, `${s.label}: ${v} ${unit}`)));
      }
    });
  }
  figure.append(chart);
  const legend = document.createElement("p");
  legend.className = "legend";
  for (const s of series) {
    const key = document.createElement("span");
    key.className = `key ${s.className}`;
    key.textContent = s.label;
    legend.append(key);
  }
  figure.append(legend);
  return figure;
}
