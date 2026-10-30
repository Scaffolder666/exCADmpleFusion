"""Document isolation and lifecycle tests for step-to-geometry binding."""
import unittest
from core.geometry_links import GeometryLinks


class GeometryLinkTests(unittest.TestCase):
    def test_bind_and_display_for_current_document(self):
        store = GeometryLinks()
        link = store.bind("mount", "caster-doc", "opaque-token", "Caster Wheel:1", "occurrence")
        self.assertEqual(link.label, "Caster Wheel:1")
        self.assertEqual(store.get("mount", "caster-doc"), link)
        result = store.display([{"id": "mount"}, {"id": "wheel"}], "caster-doc")
        self.assertEqual(result["mount"], {"label": "Caster Wheel:1", "kind": "occurrence", "available": True})
        self.assertIsNone(result["wheel"])

    def test_other_document_does_not_resolve(self):
        store = GeometryLinks()
        store.bind("mount", "caster-doc", "opaque-token", "Wheel body", "body")
        self.assertIsNone(store.get("mount", "other-doc"))
        self.assertFalse(store.display([{"id": "mount"}], "other-doc")["mount"]["available"])

    def test_rebinding_and_unlinking(self):
        store = GeometryLinks()
        store.bind("mount", "doc", "old", "Old", "face")
        store.bind("mount", "doc", "new", "New", "body")
        self.assertEqual(store.get("mount", "doc").token, "new")
        self.assertTrue(store.remove("mount"))
        self.assertFalse(store.remove("mount"))
        self.assertIsNone(store.get("mount", "doc"))

    def test_importing_another_package_clears_links(self):
        store = GeometryLinks()
        store.bind("mount", "doc", "token", "Body", "body")
        store.clear()
        self.assertEqual(store.display([{"id": "mount"}], "doc"), {"mount": None})

    def test_reject_invalid_link_data(self):
        store = GeometryLinks()
        for kind in ("", "mesh", "feature"):
            with self.assertRaises(ValueError):
                store.bind("step", "doc", "token", "Body", kind)
        with self.assertRaises(ValueError):
            store.bind("step", "", "token", "Body", "body")


if __name__ == "__main__":
    unittest.main()
