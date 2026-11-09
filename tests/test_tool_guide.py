"""Tool guidance: find the step's tools in the Fusion toolbar, put their
native buttons in a temporary panel, start them on request. Uses a stub
toolbar; Fusion's real toolbar layout and names need Fusion Desktop."""
import unittest

from core.playback.tool_guide import ToolGuide, find, PANEL_ID


class Coll(list):
    @property
    def count(self):
        return len(self)

    def item(self, i):
        return self[i]

    def itemById(self, id_):
        return next((x for x in self if getattr(x, "id", None) == id_), None)


class Definition:
    def __init__(self, name):
        self.name, self.executed = name, 0

    def execute(self):
        self.executed += 1


class CommandControl:
    def __init__(self, definition, owner=None):
        self.commandDefinition, self.owner, self.isPromoted = definition, owner, False
        self.promoted_by_default = None

    def promote(self, byDefault=False):
        self.isPromoted, self.promoted_by_default = True, byDefault
        return True

    def deleteMe(self):
        self.owner.remove(self)


class DropDown:
    def __init__(self, name, controls):
        self.name, self.controls = name, Coll(controls)


class BrokenDropDown:
    """Like some real Fusion drop-downs: reading the name raises."""

    def __init__(self, controls):
        self.controls = Coll(controls)

    @property
    def name(self):
        raise RuntimeError("2 : InternalValidationError : nuInputControl")

    @property
    def commandDefinition(self):
        raise RuntimeError("2 : InternalValidationError : nuInputControl")


class Controls(Coll):
    def addCommand(self, definition):
        control = CommandControl(definition, self)
        self.append(control)
        return control


class Panel:
    def __init__(self, id_, name, controls=(), owner=None):
        self.id, self.name, self.controls, self.owner = id_, name, Controls(controls), owner

    def deleteMe(self):
        self.owner.remove(self)


class Panels(Coll):
    def add(self, id_, name):
        panel = Panel(id_, name, owner=self)
        self.append(panel)
        return panel


class Tab:
    def __init__(self, id_, name, panels):
        self.id, self.name, self.toolbarPanels = id_, name, Panels(panels)


def workspace():
    d = {n: Definition(n) for n in ("Extrude", "Revolve", "Create Sketch", "Fillet", "Mirror")}
    surface_extrude = Definition("Extrude")
    solid = Tab("SolidTab", "SOLID", [
        Panel("SolidCreatePanel", "CREATE", [CommandControl(d["Create Sketch"]), CommandControl(d["Extrude"]),
                                             DropDown("More", [CommandControl(d["Revolve"])]),
                                             DropDown("Pattern", [CommandControl(d["Mirror"])])]),
        Panel("SolidModifyPanel", "MODIFY", [BrokenDropDown([CommandControl(Definition("Draft"))]),
                                             CommandControl(d["Fillet"])])])
    surface = Tab("SurfaceTab", "SURFACE", [Panel("SurfaceCreatePanel", "CREATE",
                                                  [CommandControl(surface_extrude)])])
    # The surface tab comes first, to check that solid modelling is preferred.
    return type("Workspace", (), {"toolbarTabs": Coll([surface, solid])})(), d, solid, surface


class FindTests(unittest.TestCase):
    def setUp(self):
        self.ws, self.d, self.solid, self.surface = workspace()

    def test_paths_from_the_real_toolbar_structure(self):
        self.assertEqual(find(self.ws, "Extrude")["path"], ["SOLID", "CREATE", "Extrude"])
        self.assertIs(find(self.ws, "Extrude")["definition"], self.d["Extrude"])   # not the surface one
        self.assertEqual(find(self.ws, "Revolve")["path"], ["SOLID", "CREATE", "More", "Revolve"])
        self.assertEqual(find(self.ws, "Sketch")["path"], ["SOLID", "CREATE", "Create Sketch"])
        self.assertEqual(find(self.ws, "Fillet")["path"], ["SOLID", "MODIFY", "Fillet"])

    def test_a_control_fusion_refuses_to_describe_does_not_stop_the_search(self):
        self.assertEqual(find(self.ws, "Fillet")["path"], ["SOLID", "MODIFY", "Fillet"])
        self.assertEqual(find(self.ws, "Draft")["path"], ["SOLID", "MODIFY", "Draft"])   # nameless menu

    def test_unknown_tools_are_not_guessed(self):
        self.assertIsNone(find(self.ws, "Loft"))
        self.assertIsNone(find(self.ws, "Base Feature"))
        self.assertIsNone(find(self.ws, ""))


class GuideTests(unittest.TestCase):
    STEPS = [["Sketch", "Extrude"], ["Fillet"], ["Sketch"], ["Mirror"], ["Base Feature"]]

    def setUp(self):
        self.ws, self.d, self.solid, self.surface = workspace()
        self.ui = type("UI", (), {"activeWorkspace": self.ws})()
        self.guide = ToolGuide(self.ui)
        self.guide.load("tutorial-1")

    def play(self, index):
        used = [t for step in self.STEPS[:index] for t in step]
        return self.guide.show(self.STEPS[index], used)

    def panel(self):
        return self.solid.toolbarPanels.itemById(PANEL_ID)

    def tools(self):
        return [(c.commandDefinition.name, c.isPromoted) for c in self.panel().controls]

    def test_starts_empty(self):
        self.assertIsNone(self.panel())
        report = self.guide.describe(self.STEPS[0])              # card text only
        self.assertEqual([r["path"][-1] for r in report], ["Create Sketch", "Extrude"])
        self.assertIsNone(self.panel())

    def test_fills_as_you_go_with_the_current_step_pinned(self):
        report = self.play(0)
        self.assertEqual(report, [{"label": "Sketch", "path": ["SOLID", "CREATE", "Create Sketch"], "found": True},
                                  {"label": "Extrude", "path": ["SOLID", "CREATE", "Extrude"], "found": True}])
        self.assertEqual(self.tools(), [("Create Sketch", True), ("Extrude", True)])
        self.assertTrue(all(c.promoted_by_default is False for c in self.panel().controls))
        self.play(1)
        self.assertEqual(self.tools(), [("Create Sketch", False), ("Extrude", False), ("Fillet", True)])
        self.play(2)                                              # Sketch again: no duplicate
        self.assertEqual(self.tools(), [("Create Sketch", True), ("Extrude", False), ("Fillet", False)])
        self.play(3)
        self.assertEqual(self.tools()[-1], ("Mirror", True))
        report = self.play(4)                                     # a tool without a command
        self.assertEqual(report, [{"label": "Base Feature", "path": [], "found": False}])
        self.assertFalse(any(pinned for _, pinned in self.tools()))

    def test_jumping_back_removes_later_tools(self):
        self.play(3)
        self.play(1)
        self.assertEqual(self.tools(), [("Create Sketch", False), ("Extrude", False), ("Fillet", True)])
        panel = self.panel()
        self.play(0)
        self.assertIs(self.panel(), panel)
        self.assertEqual(self.tools(), [("Create Sketch", True), ("Extrude", True)])
        # Our panel is never reported as where the tool lives, even if
        # Fusion lists it first.
        self.solid.toolbarPanels.remove(panel)
        self.solid.toolbarPanels.insert(0, panel)
        self.assertEqual(find(self.ws, "Fillet")["path"], ["SOLID", "MODIFY", "Fillet"])

    def test_a_new_tutorial_starts_empty_again(self):
        self.play(1)
        self.guide.load("tutorial-1")                             # same tutorial: kept
        self.assertIsNotNone(self.panel())
        self.guide.load("tutorial-2")
        self.assertIsNone(self.panel())

    def test_use_starts_the_native_command_and_close_leaves_the_toolbar_as_before(self):
        self.play(0)
        self.assertEqual(self.guide.use("Extrude"), "SOLID › CREATE › Extrude")
        self.assertEqual(self.d["Extrude"].executed, 1)
        with self.assertRaises(ValueError):
            self.guide.use("Loft")
        self.guide.close()
        self.assertIsNone(self.panel())
        self.assertEqual(len(self.solid.toolbarPanels), 2)

    def test_a_panel_fusion_refuses_is_reported_not_hidden(self):
        def refuse(id_, name):
            raise RuntimeError("panel id already in use")
        self.solid.toolbarPanels.add = refuse
        report = self.play(0)
        self.assertTrue(report[0]["found"])                       # the menu path is still shown
        self.assertIn("panel id already in use", self.guide.last_error)
        self.assertIsNone(self.guide.panel)


if __name__ == "__main__":
    unittest.main()
