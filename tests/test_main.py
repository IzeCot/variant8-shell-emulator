import unittest

from src.main import Shell, ShellError, VirtualFileSystem


class TestVirtualFileSystem(unittest.TestCase):

    def setUp(self):
        self.vfs = VirtualFileSystem()
        self.vfs.nodes["/home"] = self.vfs.nodes["/"]
        self.vfs.nodes["/home"] = type(
            self.vfs.nodes["/"]
        )("/home", "dir", "", "root")

        self.vfs.add_file(
            "/test.txt",
            "one\none\ntwo\nthree\n",
            "student",
        )

    def test_normalize(self):
        self.assertEqual(
            self.vfs.normalize("../test.txt", "/"),
            "/test.txt",
        )

    def test_file_exists(self):
        self.assertTrue(self.vfs.exists("/test.txt"))


class TestShell(unittest.TestCase):

    def setUp(self):
        self.vfs = VirtualFileSystem()
        self.vfs.add_file(
            "/test.txt",
            "one\none\ntwo\nthree\n",
        )
        self.shell = Shell(self.vfs)

    def test_parser(self):
        command, args = self.shell.parse("ls /tmp")

        self.assertEqual(command, "ls")
        self.assertEqual(args, ["/tmp"])

    def test_tail(self):
        result = self.shell.execute("tail /test.txt")

        self.assertIn("three", result)

    def test_uniq(self):
        result = self.shell.execute("uniq /test.txt")

        self.assertEqual(
            result,
            "one\ntwo\nthree",
        )

    def test_tac(self):
        result = self.shell.execute("tac /test.txt")

        self.assertEqual(
            result,
            "three\ntwo\none\none",
        )

    def test_chown(self):
        self.shell.execute("chown student /test.txt")

        self.assertEqual(
            self.vfs.get("/test.txt").owner,
            "student",
        )

    def test_unknown_command(self):
        with self.assertRaises(ShellError):
            self.shell.execute("unknown")


if __name__ == "__main__":
    unittest.main()
