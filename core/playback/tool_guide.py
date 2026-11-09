"""Point the user at the Fusion tools the current tutorial step uses.

Fusion's API cannot make a toolbar button flash, and Custom Graphics are
drawn only inside the canvas. So the tool is shown in two supported ways:

* a temporary toolbar panel "exCADmple" in the tab where the tools live,
  whose drop-down holds Fusion's own buttons for every tool the tutorial
  uses; the current step's tools are pinned to the toolbar row (Fusion's
  "Pin to Toolbar") and unpinned on the next step; removed on stop;
* the tool's menu path (e.g. SOLID > CREATE > Extrude) for the panel, found
  at run time by walking the active workspace's toolbar, so it matches the
  user's Fusion version and layout. Nothing is hard-coded per version; a
  tool that is not found is reported as not found.
"""

PANEL_ID = "excadmple_step_tools"
PANEL_NAME = "exCADmple"

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
    """Items of a Fusion collection; an item Fusion refuses is skipped."""
    if collection is None:
        return []
    try:
        count = min(collection.count, limit)
    except Exception:
        return []
    out = []
    for i in range(count):
        try:
            out.append(collection.item(i))
        except Exception:
            continue
    return out


def _read(obj, name, default=None):
    """An attribute of a Fusion UI object. Fusion raises RuntimeError (not
    AttributeError) for some controls, e.g. reading a drop-down's name
    ("InternalValidationError : nuInputControl"); one such control must not
    stop the search."""
    try:
        value = getattr(obj, name)
    except Exception:
        return default
    return default if value is None else value


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
        definition = _read(control, "commandDefinition")
        if definition is not None:
            yield path + [_read(definition, "name", "")], definition
            continue
        nested = _read(control, "controls")
        if nested is not None and depth < MAX_DEPTH:
            name = _read(control, "name", "")
            yield from walk(nested, path + ([name] if name else []), depth + 1)


def find(workspace, label):
    """Best match for ``label`` in the workspace toolbar: {"path", "definition"}
    or None. Exact command-name matches first; within them the solid
    modelling tab and the shallowest menu position win."""
    wanted = {_norm(name): rank for rank, name in enumerate(candidate_names(label))}
    if not wanted:
        return None
    found = []
    for tab_rank, tab in enumerate(_items(_read(workspace, "toolbarTabs"))):
        tab_name = _read(tab, "name", "")
        solid = 0 if "solid" in _read(tab, "id", "").lower() or tab_name.lower() == "solid" else 1
        for panel in _items(_read(tab, "toolbarPanels")):
            if _read(panel, "id", "") == PANEL_ID:
                continue                              # our own copy of the button
            for path, definition in walk(_read(panel, "controls"),
                                         [tab_name, _read(panel, "name", "")]):
                key = _norm(path[-1])
                if key in wanted:
                    found.append(((wanted[key], solid, len(path), tab_rank),
                                  {"path": [p for p in path if p], "definition": definition, "tab": tab}))
    if not found:
        return None
    found.sort(key=lambda item: item[0])
    return found[0][1]


class ToolGuide:
    """One "exCADmple" toolbar panel per tutorial.

    Its drop-down holds Fusion's own buttons for every tool the tutorial
    uses; the current step's tools are pinned (promoted) to the toolbar row,
    exactly like Fusion's "Pin to Toolbar", and unpinned when the step
    changes. The panel is removed when the tutorial closes, so nothing stays
    pinned in the user's Fusion.
    """

    def __init__(self, ui, log=None):
        self.ui = ui
        self.log = log or (lambda *_: None)
        self.panel = None
        self.panel_tab = None
        self.matches = {}              # label -> match (or None if not found)
        self.controls = {}             # label -> our CommandControl
        self.loaded_for = None
        self.last_error = ""           # why the toolbar panel could not be filled

    def _workspace(self):
        try:
            return self.ui.activeWorkspace
        except Exception:
            return None

    @staticmethod
    def _labels(labels):
        out = []
        for label in labels:
            label = str(label or "").strip()
            if label and label not in out:
                out.append(label)
        return out

    def load(self, key, labels):
        """Build the panel for a tutorial (``key`` identifies it): every
        tool it uses, in tutorial order, in the panel's drop-down."""
        if key is not None and key == self.loaded_for and self.panel is not None:
            return
        self.close()
        self.loaded_for = key
        self.last_error = ""
        workspace = self._workspace()
        for label in self._labels(labels):
            self.matches[label] = find(workspace, label) if workspace is not None else None
        found = [(label, m) for label, m in self.matches.items() if m]
        if not found:
            return
        try:
            tab = found[0][1]["tab"]
            panels = tab.toolbarPanels
            self.panel = panels.itemById(PANEL_ID) or panels.add(PANEL_ID, PANEL_NAME)
            self.panel_tab = tab
            for label, match in found:
                self.controls[label] = self.panel.controls.addCommand(match["definition"])
        except Exception as error:
            self.last_error = "{}: {}".format(type(error).__name__, error)
            self.log("exCADmple tool panel: " + self.last_error)
            self._remove_panel()

    def show(self, labels):
        """Pin the step's tools to the toolbar row, unpin the others.
        Returns [{label, path, found}] for the tutorial panel."""
        labels = self._labels(labels)
        missing = [label for label in labels if label not in self.matches]
        if missing:                                   # not loaded with the tutorial
            workspace = self._workspace()
            for label in missing:
                self.matches[label] = find(workspace, label) if workspace is not None else None
                match = self.matches[label]
                if match and self.panel is not None:
                    try:
                        self.controls[label] = self.panel.controls.addCommand(match["definition"])
                    except Exception as error:
                        self.log("exCADmple tool panel: " + str(error))
        for label, control in self.controls.items():
            if label not in labels:
                self._pin(control, False)
        for label in labels:
            if label in self.controls:
                self._pin(self.controls[label], True)
        return [{"label": label, "path": self.matches[label]["path"] if self.matches.get(label) else [],
                 "found": self.matches.get(label) is not None} for label in labels]

    def _pin(self, control, pinned):
        try:
            if control.isPromoted == pinned:
                return
            if pinned and hasattr(control, "promote"):
                # byDefault=False: a UI reset never keeps it pinned.
                if control.promote(False) is False:
                    raise RuntimeError("Fusion did not pin the tool")
            else:
                control.isPromoted = pinned
        except Exception as error:
            self.last_error = "{}: {}".format(type(error).__name__, error)
            self.log("exCADmple tool pin: " + self.last_error)

    def use(self, label):
        """Start the native Fusion command for this tool."""
        match = self.matches.get(str(label or "").strip())
        if not match:
            raise ValueError("This tool was not found in the current Fusion workspace")
        match["definition"].execute()
        return " › ".join(match["path"])

    def _remove_panel(self):
        panel, self.panel, self.panel_tab = self.panel, None, None
        self.controls = {}
        if panel is None:
            return
        try:
            for control in reversed(_items(panel.controls)):
                control.deleteMe()
            panel.deleteMe()
        except Exception as error:
            self.log("exCADmple tool panel cleanup: " + str(error))

    def close(self):
        """Remove the panel (tutorial closed or add-in stopped)."""
        self.matches = {}
        self.loaded_for = None
        self._remove_panel()
