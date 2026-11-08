"""Two-instance link: first binds (workspace), second connects (reference)."""
import queue
import socket
import unittest

from core.link import InstanceLink, WORKSPACE, REFERENCE


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LinkTests(unittest.TestCase):
    def test_roles_and_messages_both_ways(self):
        port = free_port()
        inbox_w, inbox_r = queue.Queue(), queue.Queue()
        workspace = InstanceLink(inbox_w.put, port)
        reference = InstanceLink(inbox_r.put, port)
        try:
            self.assertEqual(workspace.start(), WORKSPACE)
            self.assertEqual(reference.start(), REFERENCE)
            self.assertTrue(reference.send({"cmd": "examples", "paths": ["a.excadmple"]}))
            self.assertEqual(inbox_w.get(timeout=3), {"cmd": "examples", "paths": ["a.excadmple"]})
            for _ in range(50):
                if workspace.connected:
                    break
                import time; time.sleep(0.02)
            self.assertTrue(workspace.send({"cmd": "watch", "example_id": "phone-stand", "step_index": 3}))
            self.assertEqual(inbox_r.get(timeout=3)["step_index"], 3)
            reference.stop()
            self.assertEqual(inbox_w.get(timeout=3), {"cmd": "_disconnected"})
        finally:
            reference.stop()
            workspace.stop()

    def test_send_without_peer_is_harmless(self):
        link = InstanceLink(lambda m: None, free_port())
        try:
            self.assertEqual(link.start(), WORKSPACE)
            self.assertFalse(link.send({"cmd": "x"}))
        finally:
            link.stop()


if __name__ == "__main__":
    unittest.main()
