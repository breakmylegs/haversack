import qrcode from "qrcode-generator";
import { useMemo } from "react";

// Renders text as a QR code in SVG. Used for the update fallback and, from
// slice 6, for device code sign-in.
export function QrCode({ text, size = 200 }: { text: string; size?: number }) {
  const cells = useMemo(() => {
    const qr = qrcode(0, "M");
    qr.addData(text);
    qr.make();
    const count = qr.getModuleCount();
    const dark: [number, number][] = [];
    for (let row = 0; row < count; row += 1) {
      for (let col = 0; col < count; col += 1) {
        if (qr.isDark(row, col)) dark.push([col, row]);
      }
    }
    return { count, dark };
  }, [text]);

  const quiet = 4;
  const total = cells.count + quiet * 2;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${total} ${total}`} shapeRendering="crispEdges" role="img">
      <rect width={total} height={total} fill="#ffffff" />
      {cells.dark.map(([x, y]) => (
        <rect key={`${x}-${y}`} x={x + quiet} y={y + quiet} width={1} height={1} fill="#000000" />
      ))}
    </svg>
  );
}
