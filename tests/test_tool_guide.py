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
        Panel("SolidModifyPanel", "MODIFY", [CommandControl(d["Fillet"])])])
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

    def test_unknown_tools_are_not_guessed(self):
        self.assertIsNone(find(self.ws, "Loft"))
        self.assertIsNone(find(self.ws, "Base Feature"))
        self.assertIsNone(find(self.ws, ""))


class GuideTests(unittest.TestCase):
    TUTORIAL = ["Sketch", "Extrude", "Fillet", "Sketch", "Mirror", "Base Feature"]

    def setUp(self):
        self.ws, self.d, self.solid, self.surface = workspace()
        self.ui = type("UI", (), {"activeWorkspace": self.ws})()
        self.guide = ToolGuide(self.ui)
        self.guide.load("tutorial-1", self.TUTORIAL)

    def panel(self):
        return self.solid.toolbarPanels.itemById(PANEL_ID)

    def pinned(self):
        return [c.commandDefinition.name for c in self.panel().controls if c.isPromoted]

    def test_panel_holds_every_tool_of_the_tutorial_once(self):
        self.assertEqual([c.commandDefinition for c in self.panel().controls],
                         [self.d["Create Sketch"], self.d["Extrude"], self.d["Fillet"], self.d["Mirror"]])
        self.assertEqual(self.pinned(), [])                      # nothing pinned before a step

    def test_the_steps_tools_are_pinned_and_unpinned_on_the_next_step(self):
        report = self.guide.show(["Sketch", "Extrude"])
        self.assertEqual(report, [{"label": "Sketch", "path": ["SOLID", "CREATE", "Create Sketch"], "found": True},
                                  {"label": "Extrude", "path": ["SOLID", "CREATE", "Extrude"], "found": True}])
        self.assertEqual(self.pinned(), ["Create Sketch", "Extrude"])
        panel = self.panel()
        self.assertTrue(all(c.promoted_by_default is False for c in panel.controls if c.isPromoted))
        self.guide.show(["Fillet"])                                 # next step
        self.assertIs(self.panel(), panel)                          # same panel
        self.assertEqual(self.pinned(), ["Fillet"])                 # previous tools back in the drop-down
        self.assertEqual(len(panel.controls), 4)
        # Our panel is never reported as where the tool lives, even if
        # Fusion lists it first.
        self.solid.toolbarPanels.remove(panel)
        self.solid.toolbarPanels.insert(0, panel)
        self.assertEqual(find(self.ws, "Fillet")["path"], ["SOLID", "MODIFY", "Fillet"])

    def test_missing_tools_are_reported_not_pinned(self):
        report = self.guide.show(["Base Feature"])
        self.assertEqual(report, [{"label": "Base Feature", "path": [], "found": False}])
        self.assertEqual(self.pinned(), [])

    def test_same_tutorial_keeps_its_panel_new_tutorial_rebuilds(self):
        panel = self.panel()
        self.guide.load("tutorial-1", self.TUTORIAL)
        self.assertIs(self.panel(), panel)
        self.guide.load("tutorial-2", ["Revolve"])
        self.assertIsNot(self.panel(), panel)
        self.assertEqual([c.commandDefinition for c in self.panel().controls], [self.d["Revolve"]])

    def test_use_starts_the_native_command_and_close_leaves_the_toolbar_as_before(self):
        self.guide.show(["Extrude"])
        self.assertEqual(self.guide.use("Extrude"), "SOLID › CREATE › Extrude")
        self.assertEqual(self.d["Extrude"].executed, 1)
        with self.assertRaises(ValueError):
            self.guide.use("Loft")
        self.guide.close()
        self.assertIsNone(self.panel())
        self.assertEqual(len(self.solid.toolbarPanels), 2)        # nothing left pinned anywhere

    def test_a_panel_fusion_refuses_is_reported_not_hidden(self):
        guide = ToolGuide(self.ui)
        def refuse(id_, name):
            raise RuntimeError("panel id already in use")
        self.guide.close()
        self.solid.toolbarPanels.add = refuse
        guide.load("tutorial-3", ["Extrude"])
        report = guide.show(["Extrude"])
        self.assertTrue(report[0]["found"])                         # the menu path is still shown
        self.assertIn("panel id already in use", guide.last_error)
        self.assertIsNone(guide.panel)


if __name__ == "__main__":
    unittest.main()
