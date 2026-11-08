"""Several design examples open at once, each with its own playback state."""
import re


class LibraryError(ValueError):
    pass


def _slug(text):
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "example").lower()).strip("-")
    return slug or "example"


class ExampleLibrary:
    def __init__(self):
        self._items = {}      # id -> {"package", "step_index", "elapsed"}
        self._order = []
        self.active_id = None

    def __len__(self):
        return len(self._order)

    def add(self, package):
        """Add (or replace, for the same example id) and activate a package."""
        wanted = package.data.get("id") or _slug(package.data.get("title"))
        example_id = _slug(wanted)
        if example_id in self._items:
            self._items[example_id]["package"].close()
            self._items[example_id] = {"package": package, "step_index": 0}
        else:
            self._items[example_id] = {"package": package, "step_index": 0}
            self._order.append(example_id)
        self.active_id = example_id
        return example_id

    def remove(self, example_id):
        item = self._items.pop(example_id, None)
        if not item:
            raise LibraryError("Unknown example")
        item["package"].close()
        self._order.remove(example_id)
        if self.active_id == example_id:
            self.active_id = self._order[0] if self._order else None

    def activate(self, example_id):
        if example_id not in self._items:
            raise LibraryError("Unknown example: " + str(example_id))
        self.active_id = example_id
        return self._items[example_id]

    def package(self, example_id=None):
        item = self._items.get(example_id or self.active_id)
        return item["package"] if item else None

    def step_index(self, example_id=None):
        item = self._items.get(example_id or self.active_id)
        return item["step_index"] if item else 0

    def remember_step(self, index, example_id=None):
        item = self._items.get(example_id or self.active_id)
        if item:
            item["step_index"] = int(index)

    def examples(self):
        """(id, data) pairs for decision collection."""
        return [(i, self._items[i]["package"].data) for i in self._order]

    def listing(self):
        return [{"id": i, "title": self._items[i]["package"].data["title"],
                 "steps": len(self._items[i]["package"].data["steps"]),
                 "step_index": self._items[i]["step_index"],
                 "active": i == self.active_id} for i in self._order]

    def close(self):
        for item in self._items.values():
            item["package"].close()
        self._items.clear()
        self._order.clear()
        self.active_id = None
