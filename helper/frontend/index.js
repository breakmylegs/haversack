// Keepsake Helper's quick menu entry. Hand-written against Decky's globals (DFL, SP_REACT): the
// helper has no screens of its own; Keepsake shows its state under Device, Reconnect help.
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
        label: "Used by Keepsake",
        description: "This helper runs as root and does only a few Bluetooth jobs that Keepsake asks for. Open Keepsake, Device, Reconnect help.",
      }),
    ),
  );
}

export default definePlugin(() => ({
  name: "Keepsake Helper",
  titleView: h("div", { className: DFL.staticClasses.Title }, "Keepsake Helper"),
  content: h(Content, null),
  icon: h("span", null, "K"),
  onDismount() {},
}));
