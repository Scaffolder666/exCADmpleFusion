"""HiM Algorithm 1/2 on a fake timeline modeled after the paper's Figure 5."""
import unittest

from core.playback.him_filter import FeatureInfo, InputRef, extract_relevant_features, show_more


class FakeModel:
    """Faces are strings; a face exists from the state after its creator."""

    def __init__(self):
        f = FeatureInfo
        self._features = [
            f(0, "Sketch1", "Sketch"),
            f(1, "Base plate", "ExtrudeFeature"),
            f(2, "Sketch2", "Sketch"),
            f(3, "Rod", "ExtrudeFeature"),
            f(4, "Thread1", "ThreadFeature"),
            f(5, "Thread2", "ThreadFeature"),
            f(6, "Rod pattern", "CircularPatternFeature"),
            f(7, "Plate fillet", "FilletFeature"),
            f(8, "Hole cut", "ExtrudeFeature"),
        ]
        self.creates = {1: {"top", "plate_side"}, 3: {"rod_side", "rod_end"},
                        4: {"thread1"}, 5: {"thread2"}, 6: {"rod_copy_side"},
                        7: {"fillet_face"}, 8: {"hole_wall"}}
        self.edges = {"plate_edge": ("top", "plate_side"), "rod_edge": ("rod_side", "rod_end")}
        self.vertices = {"corner": ("plate_edge", "rod_edge")}
        by = {f.index: f for f in self._features}
        self.inputs = {
            1: [InputRef("sketch", "sk1", 1, by[0])],
            3: [InputRef("sketch", "sk2", 3, by[2])],
            4: [InputRef("face", "rod_side", 4)],
            5: [InputRef("face", "rod_side", 5)],
            6: [InputRef("feature", None, 6, by[3]), InputRef("feature", None, 6, by[4]),
                InputRef("feature", None, 6, by[5])],
            7: [InputRef("edge", "plate_edge", 7)],
            8: [InputRef("sketch", "sk1", 8, by[0])],
        }
        self.sketch_faces = {"sk1": None, "sk2": "top"}
        self.calls = 0

    def end_state(self):
        return 9

    def features(self):
        return self._features

    def _exists(self, face, state):
        return any(face in faces and index < state for index, faces in self.creates.items())

    def extract_faces(self, ref, state):
        if ref in self.vertices:
            faces = []
            for edge in self.vertices[ref]:
                faces.extend(x for x in self.edges[edge] if x not in faces)
            return faces
        if ref in self.edges:
            return list(self.edges[ref])
        return [ref] if self._exists(ref, state) else []

    def created(self, feature, face, state):
        self.calls += 1
        return face in self.creates.get(feature.index, ()) and feature.index < state

    def input_geometries(self, feature):
        return self.inputs.get(feature.index, [])

    def sketch_base_face(self, sketch_ref):
        return self.sketch_faces[sketch_ref]

    def signature(self, ref, state):
        faces = self.extract_faces(ref, state) if ref not in self.edges else [ref]
        if not faces or (ref not in self.edges and not self._exists(ref, state)):
            return None
        if ref == "top":     # fillet rounds an edge, cut adds a hole
            return ("top", state >= 8, state >= 9)
        return (ref,)


def names(result):
    return [f.name for f in result.features]


class HiMFilterTests(unittest.TestCase):
    def setUp(self):
        self.model = FakeModel()

    def test_patterned_threaded_rod_matches_figure_5(self):
        result = extract_relevant_features(self.model, "rod_copy_side")
        self.assertEqual(names(result), ["Rod pattern", "Thread2", "Thread1", "Rod"])
        self.assertEqual(result.roles[6], "created")
        self.assertEqual(result.roles[4], "input")
        self.assertTrue(result.can_show_more())     # Sketch2 lies on a face

    def test_show_more_follows_sketch_face_until_ground_plane(self):
        result = extract_relevant_features(self.model, "rod_copy_side")
        show_more(self.model, result)
        self.assertEqual(names(result), ["Rod pattern", "Thread2", "Thread1", "Rod", "Base plate"])
        self.assertEqual(result.levels[1], 1)
        self.assertFalse(result.can_show_more())     # Sketch1 is on a ground plane
        self.assertEqual(result.as_dict()["features"][-1]["level"], 1)

    def test_modifications_detected_by_before_after_comparison(self):
        result = extract_relevant_features(self.model, "top")
        self.assertEqual(names(result), ["Hole cut", "Plate fillet", "Base plate"])
        self.assertEqual(result.roles[8], "modified")
        self.assertEqual(result.roles[1], "created")

    def test_modifications_can_be_disabled(self):
        result = extract_relevant_features(self.model, "top", include_modifications=False)
        self.assertEqual(names(result), ["Base plate"])

    def test_edge_uses_both_adjacent_faces(self):
        result = extract_relevant_features(self.model, "rod_edge", include_modifications=False)
        self.assertEqual(names(result), ["Rod"])

    def test_vertex_uses_faces_of_all_edges(self):
        result = extract_relevant_features(self.model, "corner", include_modifications=False)
        self.assertEqual(names(result), ["Rod", "Base plate"])

    def test_fillet_traces_input_edge_faces(self):
        result = extract_relevant_features(self.model, "fillet_face", include_modifications=False)
        self.assertEqual(names(result), ["Plate fillet", "Base plate"])

    def test_unrelated_features_are_filtered_out(self):
        result = extract_relevant_features(self.model, "thread1")
        self.assertNotIn("Plate fillet", names(result))
        self.assertNotIn("Hole cut", names(result))
        self.assertEqual(names(result), ["Thread1", "Rod"])

    def test_result_is_serialisable_for_the_panel(self):
        data = extract_relevant_features(self.model, "rod_copy_side").as_dict()
        self.assertEqual(data["features"][0]["timeline_index"], 6)
        self.assertEqual(data["bases"][0]["name"], "Sketch2")
        self.assertTrue(data["can_show_more"])


if __name__ == "__main__":
    unittest.main()
