// Haversack Helper's quick menu entry. Hand-written against Decky's globals (DFL, SP_REACT): the
// helper has no screens of its own; Haversack shows its state under Device, Controllers, Reconnect help.
const h = SP_REACT.createElement;
const definePlugin = (fn) => (...args) => fn(...args);

function Content() {
  return h(
    DFL.PanelSection,
    null,
    h(
      DFL.PanelSectionRow,
      null,
      h(DFL.Field, {
        label: "Used by Haversack",
        description: "This helper runs as root and does only a few Bluetooth jobs that Haversack asks for. Open Haversack, Device, Controllers, Reconnect help.",
      }),
    ),
  );
}

export default definePlugin(() => ({
  name: "Haversack Helper",
  titleView: h("div", { className: DFL.staticClasses.Title }, "Haversack Helper"),
  content: h(Content, null),
  icon: h("span", null, "K"),
  onDismount() {},
}));
