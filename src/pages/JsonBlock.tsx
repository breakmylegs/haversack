import { Focusable } from "@decky/ui";

// Read-only JSON viewer. Focusable so the controller can scroll to it.
export function JsonBlock({ value }: { value: unknown }) {
  if (value === undefined) return null;
  return (
    <Focusable
      style={{
        background: "rgba(0, 0, 0, 0.3)",
        borderRadius: 4,
        padding: 8,
        marginTop: 8,
        maxHeight: 320,
        overflowY: "auto",
      }}
    >
      <pre style={{ margin: 0, fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
        {JSON.stringify(value, null, 2)}
      </pre>
    </Focusable>
  );
}
