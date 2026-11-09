"""Point the user at the Fusion tools the current tutorial step uses.

Fusion's API cannot make a toolbar button flash, and Custom Graphics are
drawn only inside the canvas. So the tool is shown in two supported ways:

* a toolbar panel "exCADmple" of its own (at the end of the tab where the
  tools live) that starts empty and fills as the tutorial plays: each
  step's tools are added as Fusion's own buttons and pinned to the toolbar
  row (Fusion's "Pin to Toolbar"); earlier steps' tools move into its
  drop-down; jumping back removes later steps' tools; removed on stop;
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
    "copypastebody": (),
}
# Tools that are not toolbar commands: how the designer used them instead.
SHORTCUTS = {
    "copypastebody": "Copy and paste the body: Ctrl+C, then Ctrl+V",
    "paste bodies": "Copy and paste the body: Ctrl+C, then Ctrl+V",
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


ICON_FILES = ("32x32@2x.png", "64x64.png", "32x32.png", "16x16@2x.png", "16x16.png")


def icon_uri(definition):
    """file:// URI of the command's own icon, if Fusion exposes its resource
    folder; "" otherwise (the panel then shows a plain letter tile)."""
    from pathlib import Path
    folder = _read(definition, "resourceFolder", "")
    if not folder:
        return ""
    try:
        base = Path(folder)
        for name in ICON_FILES:
            path = base / name
            if path.is_file():
                return path.resolve().as_uri()
    except Exception:
        return ""
    return ""


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
    """One "exCADmple" toolbar panel per tutorial, empty at first.

    It collects Fusion's own buttons for the tools used up to the current
    step; the current step's tools are pinned (promoted) to the toolbar
    row, exactly like Fusion's "Pin to Toolbar". The panel is removed when
    the tutorial closes, so nothing stays pinned in the user's Fusion.
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

    def load(self, key):
        """A new tutorial (``key`` identifies it) starts with an empty panel."""
        if key is not None and key == self.loaded_for:
            return
        self.close()
        self.loaded_for = key

    def _match(self, label):
        if label not in self.matches:
            workspace = self._workspace()
            self.matches[label] = find(workspace, label) if workspace is not None else None
        return self.matches[label]

    def _ensure_panel(self, tab):
        if self.panel is None:
            panels = tab.toolbarPanels
            self.panel = panels.itemById(PANEL_ID) or panels.add(PANEL_ID, PANEL_NAME)
            self.panel_tab = tab

    def show(self, labels, used=()):
        """The panel holds the tools ``used`` so far (steps up to this one,
        in tutorial order); this step's ``labels`` are pinned to the toolbar
        row, the earlier ones sit in the drop-down. Jumping back removes the
        tools of later steps again. Returns [{label, path, found}]."""
        labels = self._labels(labels)
        used = self._labels(list(used) + labels)
        self.last_error = ""
        wanted = [(label, self._match(label)) for label in used]
        wanted = [(label, match) for label, match in wanted if match]
        try:
            for label in [l for l in self.controls if l not in dict(wanted)]:
                self.controls.pop(label).deleteMe()   # a later step's tool, after jumping back
            for label, match in wanted:
                if label not in self.controls:
                    self._ensure_panel(match["tab"])
                    self.controls[label] = self.panel.controls.addCommand(match["definition"])
        except Exception as error:
            self.last_error = "{}: {}".format(type(error).__name__, error)
            self.log("exCADmple tool panel: " + self.last_error)
        for label, control in self.controls.items():
            self._pin(control, label in labels)
        return self.describe(labels)

    def describe(self, labels):
        """Where the tools live, without touching the panel."""
        out = []
        for label in self._labels(labels):
            match = self._match(label)
            out.append({"label": label, "path": match["path"] if match else [], "found": match is not None,
                        "hint": "" if match else SHORTCUTS.get(label.lower(), ""),
                        "name": _read(match["definition"], "name", label) if match else label,
                        "icon": icon_uri(match["definition"]) if match else ""})
        return out

    def _pin(self, control, pinned):
        try:
            if bool(control.isPromoted) == pinned:
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
