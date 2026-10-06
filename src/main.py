import argparse
import base64
import csv
import getpass
import os
import socket
import sys
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter.scrolledtext import ScrolledText


class ShellError(Exception):
    """Ошибка выполнения команды оболочки."""


@dataclass
class VFSNode:
    path: str
    kind: str
    content: str = ""
    owner: str = "root"


class VirtualFileSystem:
    """Виртуальная файловая система, полностью находящаяся в памяти."""

    def __init__(self):
        self.nodes = {
            "/": VFSNode("/", "dir", "", "root")
        }

    @staticmethod
    def normalize(path: str, current: str = "/") -> str:
        if not path:
            return current

        if path.startswith("/"):
            result = path
        else:
            result = current.rstrip("/") + "/" + path

        parts = []
        for part in result.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                if parts:
                    parts.pop()
            else:
                parts.append(part)

        return "/" + "/".join(parts)

    def exists(self, path: str) -> bool:
        return self.normalize(path) in self.nodes

    def get(self, path: str, current: str = "/") -> VFSNode:
        normalized = self.normalize(path, current)

        if normalized not in self.nodes:
            raise ShellError(f"Нет такого файла или каталога: {normalized}")

        return self.nodes[normalized]

    def load_csv(self, filename: str):
        path = Path(filename)

        if not path.exists():
            raise ShellError(f"VFS-файл не найден: {filename}")

        try:
            with path.open("r", encoding="utf-8", newline="") as file:
                reader = csv.DictReader(file)

                required = {"path", "type", "content", "owner"}

                if not reader.fieldnames or not required.issubset(reader.fieldnames):
                    raise ShellError(
                        "Некорректный формат VFS: "
                        "необходимы поля path,type,content,owner"
                    )

                for row in reader:
                    node_path = self.normalize(row["path"])
                    node_type = row["type"]

                    if node_type not in ("file", "dir"):
                        raise ShellError(
                            f"Некорректный тип VFS-элемента: {node_type}"
                        )

                    content = row["content"] or ""

                    if node_type == "file" and content:
                        try:
                            content = base64.b64decode(
                                content.encode("ascii")
                            ).decode("utf-8")
                        except Exception as exc:
                            raise ShellError(
                                f"Ошибка base64 для {node_path}"
                            ) from exc

                    self.nodes[node_path] = VFSNode(
                        node_path,
                        node_type,
                        content,
                        row["owner"] or "root",
                    )

        except UnicodeDecodeError as exc:
            raise ShellError("Не удалось прочитать VFS как UTF-8") from exc
        except csv.Error as exc:
            raise ShellError("Ошибка разбора CSV VFS") from exc

    def children(self, directory: str):
        directory = self.normalize(directory)
        prefix = directory.rstrip("/") + "/"
        result = []

        for path, node in self.nodes.items():
            if path == directory or not path.startswith(prefix):
                continue

            relative = path[len(prefix):]

            if "/" not in relative:
                result.append(node)

        return sorted(result, key=lambda item: (item.kind != "dir", item.path))

    def add_file(self, path: str, content: str, owner: str = "root"):
        normalized = self.normalize(path)

        if self.exists(normalized):
            raise ShellError(f"Элемент уже существует: {normalized}")

        parent = str(Path(normalized).parent).replace("\\", "/")

        if parent == ".":
            parent = "/"

        if not self.exists(parent):
            raise ShellError(f"Каталог не существует: {parent}")

        if self.get(parent).kind != "dir":
            raise ShellError(f"Родитель не является каталогом: {parent}")

        self.nodes[normalized] = VFSNode(
            normalized, "file", content, owner
        )


class Shell:
    """Командная оболочка эмулятора."""

    def __init__(self, vfs=None):
        self.username = getpass.getuser()
        self.hostname = socket.gethostname()
        self.vfs = vfs
        self.current_dir = "/"

    @property
    def prompt(self):
        return f"{self.username}@{self.hostname}:{self.current_dir}$ "

    def parse(self, line: str):
        parts = line.strip().split()

        if not parts:
            return "", []

        return parts[0], parts[1:]

    def execute(self, line: str):
        command, args = self.parse(line)

        if not command:
            return ""

        commands = {
            "ls": self.cmd_ls,
            "cd": self.cmd_cd,
            "tail": self.cmd_tail,
            "uniq": self.cmd_uniq,
            "tac": self.cmd_tac,
            "chown": self.cmd_chown,
        }

        if command == "exit":
            raise SystemExit(0)

        if command not in commands:
            raise ShellError(f"Неизвестная команда: {command}")

        return commands[command](args)

    def require_vfs(self):
        if self.vfs is None:
            raise ShellError("VFS не загружена")

    def cmd_ls(self, args):
        self.require_vfs()

        if len(args) > 1:
            raise ShellError("Использование: ls [путь]")

        path = args[0] if args else self.current_dir
        node = self.vfs.get(path, self.current_dir)

        if node.kind != "dir":
            return node.path.split("/")[-1]

        result = []

        for child in self.vfs.children(node.path):
            name = child.path.rstrip("/").split("/")[-1]
            result.append(name + ("/" if child.kind == "dir" else ""))

        return "\n".join(result)

    def cmd_cd(self, args):
        self.require_vfs()

        if len(args) > 1:
            raise ShellError("Использование: cd [путь]")

        target = args[0] if args else "/"
        node = self.vfs.get(target, self.current_dir)

        if node.kind != "dir":
            raise ShellError(f"Не каталог: {node.path}")

        self.current_dir = node.path
        return ""

    def get_file(self, args, command):
        self.require_vfs()

        if len(args) != 1:
            raise ShellError(f"Использование: {command} <файл>")

        node = self.vfs.get(args[0], self.current_dir)

        if node.kind != "file":
            raise ShellError(f"Не файл: {node.path}")

        return node

    def cmd_tail(self, args):
        node = self.get_file(args, "tail")
        lines = node.content.splitlines()
        return "\n".join(lines[-10:])

    def cmd_uniq(self, args):
        node = self.get_file(args, "uniq")

        lines = node.content.splitlines()
        result = []

        for line in lines:
            if not result or result[-1] != line:
                result.append(line)

        return "\n".join(result)

    def cmd_tac(self, args):
        node = self.get_file(args, "tac")
        return "\n".join(reversed(node.content.splitlines()))

    def cmd_chown(self, args):
        self.require_vfs()

        if len(args) != 2:
            raise ShellError("Использование: chown <пользователь> <путь>")

        owner, path = args
        node = self.vfs.get(path, self.current_dir)
        node.owner = owner

        return f"Владелец {node.path} изменён на {owner}"


class EmulatorGUI:
    """Графический интерфейс командной строки."""

    def __init__(self, shell):
        self.shell = shell

        self.root = tk.Tk()
        self.root.title(
            f"Эмулятор - [{shell.username}@{shell.hostname}]"
        )
        self.root.geometry("900x600")

        self.output = ScrolledText(
            self.root,
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.output.pack(
            fill=tk.BOTH,
            expand=True,
            padx=10,
            pady=10,
        )

        self.entry = tk.Entry(self.root)
        self.entry.pack(fill=tk.X, padx=10, pady=(0, 10))

        self.entry.bind("<Return>", self.process)

        self.print_line(
            "Эмулятор UNIX-подобной командной оболочки"
        )
        self.print_line(
            "Введите команду. Доступны: ls, cd, tail, uniq, tac, chown, exit."
        )
        self.print_prompt()

    def print_line(self, text):
        self.output.config(state=tk.NORMAL)
        self.output.insert(tk.END, text + "\n")
        self.output.config(state=tk.DISABLED)
        self.output.see(tk.END)

    def print_prompt(self):
        self.print_line(self.shell.prompt)

    def process(self, event=None):
        command = self.entry.get()
        self.entry.delete(0, tk.END)

        self.print_line(self.shell.prompt + command)

        try:
            result = self.shell.execute(command)

            if result:
                self.print_line(result)

        except SystemExit:
            self.root.destroy()
            return

        except ShellError as exc:
            self.print_line(f"Ошибка: {exc}")

        self.print_prompt()

    def run(self):
        self.root.mainloop()


def run_script(shell, script_path):
    path = Path(script_path)

    if not path.exists():
        raise ShellError(f"Startup-скрипт не найден: {script_path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            for number, raw_line in enumerate(file, 1):
                line = raw_line.strip()

                if not line or line.startswith("#"):
                    continue

                print(f"{shell.prompt}{line}")

                try:
                    result = shell.execute(line)

                    if result:
                        print(result)

                except SystemExit:
                    return 0

                except ShellError as exc:
                    print(
                        f"Ошибка в startup-скрипте "
                        f"(строка {number}): {exc}"
                    )
                    return 1

    except OSError as exc:
        raise ShellError(
            f"Не удалось прочитать startup-скрипт: {exc}"
        ) from exc

    return 0


def parse_args():
    parser = argparse.ArgumentParser(
        description="Эмулятор UNIX-подобной командной оболочки"
    )

    parser.add_argument(
        "--vfs",
        help="путь к CSV-файлу виртуальной файловой системы",
    )

    parser.add_argument(
        "--script",
        help="путь к startup-скрипту",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    print("Параметры запуска:")
    print(f" vfs = {args.vfs}")
    print(f" script = {args.script}")

    vfs = None

    if args.vfs:
        vfs = VirtualFileSystem()

        try:
            vfs.load_csv(args.vfs)
        except ShellError as exc:
            print(f"Ошибка загрузки VFS: {exc}", file=sys.stderr)
            return 1

    shell = Shell(vfs)

    if args.script:
        result = run_script(shell, args.script)

        if result != 0:
            return result

        return 0

    app = EmulatorGUI(shell)
    app.run()

    return 0


if __name__ == "__main__":
    sys.exit(main())
