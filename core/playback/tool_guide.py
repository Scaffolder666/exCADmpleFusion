"""Point the user at the Fusion tools the current tutorial step uses.

Fusion's API cannot make a toolbar button flash, and Custom Graphics are
drawn only inside the canvas. So the tool is shown in two supported ways:

* a temporary toolbar panel "exCADmple · this step" in the tab where the
  tool lives, holding the step's *native* Fusion command buttons (clicking
  one runs Fusion's own command); replaced on every step, removed on stop;
* the tool's menu path (e.g. SOLID > CREATE > Extrude) for the panel, found
  at run time by walking the active workspace's toolbar, so it matches the
  user's Fusion version and layout. Nothing is hard-coded per version; a
  tool that is not found is reported as not found.
"""

PANEL_ID = "excadmple_step_tools"
PANEL_NAME = "exCADmple · this step"

# Tutorial tool label -> Fusion command names to look for (English UI).
ALIASES = {
    "sketch": ("Create Sketch", "Sketch"),
    "move": ("Move/Copy", "Move"),
    "construction plane": ("Offset Plane", "Plane at Angle", "Midplane"),
    "offset faces": ("Offset Face", "Press Pull"),
    "split body": ("Split Body",),
    "split face": ("Split Face",),
    "paste bodies": (),
    "base feature": (),
}
MAX_DEPTH = 4


def _items(collection, limit=500):
    if collection is None:
        return []
    try:
        return [collection.item(i) for i in range(min(collection.count, limit))]
    except Exception:
        return []


def _norm(text):
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def candidate_names(label):
    """Command names that stand for this tutorial tool label."""
    label = str(label or "").strip()
    names = ALIASES.get(label.lower())
    if names is None:
        names = (label,)
    return [n for n in names if n]


def walk(controls, path, depth=0):
    """(path, definition) for every command in a control tree."""
    for control in _items(controls):
        definition = None
        try:
            definition = control.commandDefinition
        except Exception:
            definition = None
        if definition is not None:
            yield path + [getattr(definition, "name", "")], definition
            continue
        nested = getattr(control, "controls", None)
        if nested is not None and depth < MAX_DEPTH:
            name = getattr(control, "name", "") or ""
            yield from walk(nested, path + ([name] if name else []), depth + 1)


def find(workspace, label):
    """Best match for ``label`` in the workspace toolbar: {"path", "definition"}
    or None. Exact command-name matches first; within them the solid
    modelling tab and the shallowest menu position win."""
    wanted = {_norm(name): rank for rank, name in enumerate(candidate_names(label))}
    if not wanted:
        return None
    found = []
    for tab_rank, tab in enumerate(_items(getattr(workspace, "toolbarTabs", None))):
        tab_name = getattr(tab, "name", "") or ""
        solid = 0 if "solid" in (getattr(tab, "id", "") or "").lower() or tab_name.lower() == "solid" else 1
        for panel in _items(getattr(tab, "toolbarPanels", None)):
            if getattr(panel, "id", "") == PANEL_ID:
                continue                              # our own copy of the button
            for path, definition in walk(getattr(panel, "controls", None),
                                         [tab_name, getattr(panel, "name", "") or ""]):
                key = _norm(path[-1])
                if key in wanted:
                    found.append(((wanted[key], solid, len(path), tab_rank),
                                  {"path": [p for p in path if p], "definition": definition, "tab": tab}))
    if not found:
        return None
    found.sort(key=lambda item: item[0])
    return found[0][1]


class ToolGuide:
    """Keeps the temporary toolbar panel in sync with the current step."""

    def __init__(self, ui, log=None):
        self.ui = ui
        self.log = log or (lambda *_: None)
        self.panel = None
        self.panel_tab = None
        self.matches = {}

    def _workspace(self):
        try:
            return self.ui.activeWorkspace
        except Exception:
            return None

    def show(self, labels):
        """Find each tool; put the found native buttons in the temporary
        panel. Returns [{label, path, found}] for the tutorial panel."""
        self._clear_buttons()
        workspace = self._workspace()
        report, matches = [], {}
        for label in labels:
            label = str(label or "").strip()
            if not label or label in matches:
                continue
            match = find(workspace, label) if workspace is not None else None
            matches[label] = match
            report.append({"label": label, "path": match["path"] if match else [],
                           "found": match is not None})
        self.matches = matches
        found = [m for m in matches.values() if m]
        if found:
            try:
                self._fill_panel(found)
            except Exception as error:
                self.log("exCADmple tool panel: " + str(error))
                self.close()
        else:
            self._remove_panel()
        return report

    def _fill_panel(self, found):
        tab = found[0]["tab"]
        if self.panel is not None and self.panel_tab is not tab:
            self._remove_panel()                      # the tools live in another tab now
        if self.panel is None:
            panels = tab.toolbarPanels
            self.panel = panels.itemById(PANEL_ID) or panels.add(PANEL_ID, PANEL_NAME)
            self.panel_tab = tab
        for match in found:
            control = self.panel.controls.addCommand(match["definition"])
            try:
                control.isPromoted = True             # show it in the toolbar row itself
            except Exception:
                pass

    def use(self, label):
        """Start the native Fusion command for this tool."""
        match = self.matches.get(str(label or "").strip())
        if not match:
            raise ValueError("This tool was not found in the current Fusion workspace")
        match["definition"].execute()
        return " › ".join(match["path"])

    def _clear_buttons(self):
        self.matches = {}
        if self.panel is None:
            return
        try:
            for control in reversed(_items(self.panel.controls)):
                control.deleteMe()
        except Exception as error:
            self.log("exCADmple tool panel cleanup: " + str(error))

    def _remove_panel(self):
        panel, self.panel, self.panel_tab = self.panel, None, None
        if panel is None:
            return
        try:
            for control in reversed(_items(panel.controls)):
                control.deleteMe()
            panel.deleteMe()
        except Exception as error:
            self.log("exCADmple tool panel cleanup: " + str(error))

    def close(self):
        """Remove the temporary panel (tutorial closed or add-in stopped)."""
        self.matches = {}
        self._remove_panel()
