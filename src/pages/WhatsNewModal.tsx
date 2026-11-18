import { DialogButton, ModalRoot, showModal } from "@decky/ui";

// "What's new" once after an update, from the changelog section shipped with the release (ADR-0049).
export function openWhatsNew(version: string, notes: string) {
  showModal(<WhatsNewModal version={version} notes={notes} />);
}

function WhatsNewModal({ version, notes, closeModal }: { version: string; notes: string; closeModal?: () => void }) {
  // The changelog is Markdown: show its bullets and headings as plain lines, never as HTML.
  const lines = notes
    .split("\n")
    .map((line) => line.replace(/^#+\s*/, "").replace(/^-\s+/, "• ").replace(/\*\*/g, "").replace(/`/g, ""))
    .filter((line, i, all) => line.trim() || (i > 0 && all[i - 1].trim()));
  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      <div style={{ fontSize: 20, fontWeight: "bold", marginBottom: 8 }}>What's new in Keepsake {version}</div>
      <div style={{ maxHeight: "60vh", overflowY: "auto", whiteSpace: "pre-wrap", fontSize: 14 }}>
        {lines.length ? lines.join("\n") : "This version has no release notes."}
      </div>
      <DialogButton style={{ width: "auto", marginTop: 12 }} onClick={closeModal}>
        Close
      </DialogButton>
    </ModalRoot>
  );
}
