#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Prompt to generate this script
# --------------------------
# 模仿 linux 命令 tree，编写 python 脚本，运行时打开一个 Dialog，接受目录路径，
# 然后递归查看子目录、文件，最后利用制表符等打印文件结构。
# 使用一个 stack 数据结构记录各级目录的 .gitignore 规则。
# 在使用 Dialog 打开指定目录以后，首先检测该目录是否存在 .gitignore 文件，
# 如果有 .gitignore 则按照其规则忽略文件，
# 递归进入子目录以后，也要检测子目录是否存在 .gitignore 文件并按其规则忽略文件。
# 注意：子目录的忽略规则实际应该是其祖先结点
# （对于多叉树中的结点 `x`，它的**祖先结点**一般指：从根结点到 `x` 的路径上，除了 `x` 本身以外的所有结点）
# 及其本身忽略规则的\*并集\*（不是只使用子结点规则，而不使用祖先结点规则）；
# 但是在递归遍历流程退出该结点，进入其兄弟结点时，需要清空该结点忽略规则的作用，
# 只留下其祖先结点的作用，再检测和加载其兄弟结点的忽略规则。
# 不进入也不记录 .git 目录的子目录，只记录和打印 .git 目录本身。

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

from pathspec import GitIgnoreSpec


@dataclass(slots=True)
class IgnoreContext:
    """
    表示递归路径中的一级目录，以及该目录自己的 .gitignore 规则。
    """

    directory: Path
    spec: GitIgnoreSpec | None


class GitIgnoreStack:
    """
    保存从根目录到当前递归结点的 .gitignore 规则栈。

    例如当前正在遍历：

        root/
            src/
                module/
                    file.py

    那么栈可能是：

        [
            root/.gitignore,
            root/src/.gitignore,
            root/src/module/.gitignore,
        ]

    某一级没有 .gitignore 时，也会压入一个 spec=None 的栈帧，
    这样 push / pop 与递归层级始终严格对应。
    """

    def __init__(self) -> None:
        self._stack: list[IgnoreContext] = []

    def push_directory(self, directory: Path) -> None:
        """
        进入一个目录。

        检测该目录中的 .gitignore，
        若存在则读取规则，然后压入 stack。
        """

        gitignore = directory / ".gitignore"

        spec: GitIgnoreSpec | None = None

        if gitignore.is_file():
            try:
                with gitignore.open(
                    "r",
                    encoding="utf-8",
                    errors="replace",
                ) as file:
                    spec = GitIgnoreSpec.from_lines(file)

            except OSError as exc:
                print(
                    f"[警告] 无法读取 {gitignore}: {exc}"
                )

        self._stack.append(
            IgnoreContext(
                directory=directory,
                spec=spec,
            )
        )

    def pop_directory(self) -> None:
        """
        离开当前目录。

        弹出当前目录自己的 .gitignore 规则，
        避免这些规则继续作用到当前目录的兄弟结点。
        """

        if not self._stack:
            raise RuntimeError(
                "gitignore 规则栈为空，无法 pop"
            )

        self._stack.pop()

    def is_ignored(
        self,
        path: Path,
        *,
        is_dir: bool,
    ) -> bool:
        """
        判断 path 是否应该被忽略。

        注意：

        按要求采用“祖先规则 ∪ 当前规则”的并集语义。

        即：

            root rules
                ∪
            parent rules
                ∪
            current rules

        只要 stack 中任意一级 .gitignore 判定该路径
        应被忽略，就返回 True。
        """

        for context in self._stack:
            if context.spec is None:
                continue

            try:
                relative_path = path.relative_to(
                    context.directory
                )

            except ValueError:
                # 正常递归情况下不会发生。
                continue

            # .gitignore 使用 POSIX 风格 "/"。
            relative_text = relative_path.as_posix()

            # 对目录增加 "/"，
            # 使 build/、cache/ 之类的规则能够正确匹配。
            if is_dir:
                relative_text += "/"

            if context.spec.match_file(relative_text):
                return True

        return False


def select_directory() -> Path | None:
    """
    打开目录选择 Dialog。
    """

    root = tk.Tk()

    root.withdraw()

    # 让 Dialog 尽量显示在最前方。
    root.attributes(
        "-topmost",
        True,
    )

    directory = filedialog.askdirectory(
        parent=root,
        title="请选择要查看的目录",
        mustexist=True,
    )

    root.destroy()

    if not directory:
        return None

    return Path(directory).resolve()


def safe_is_dir(path: Path) -> bool:
    """
    安全判断路径是否为目录。
    """

    try:
        return path.is_dir()

    except OSError:
        return False


def is_git_directory(path: Path) -> bool:
    """
    判断 path 是否为 .git 目录。

    Windows 文件名通常大小写不敏感，因此这里使用 casefold()。
    该判断只针对目录；名为 .git 的普通文件不会被当作目录处理。
    """

    return path.name.casefold() == ".git"


def display_name(
    path: Path,
    *,
    is_dir: bool,
) -> str:
    """
    获取 tree 中显示的名称。

    对符号链接额外显示目标。
    """

    if path.is_symlink():
        try:
            target = path.readlink()

            suffix = "/" if is_dir else ""

            return (
                f"{path.name}"
                f"{suffix}"
                f" -> "
                f"{target}"
            )

        except OSError:
            pass

    if is_dir:
        return path.name + "/"

    return path.name


def get_visible_entries(
    directory: Path,
    ignore_stack: GitIgnoreStack,
) -> list[tuple[Path, bool]]:
    """
    获取当前目录中没有被 .gitignore 忽略的文件和目录。
    """

    try:
        entries = list(
            directory.iterdir()
        )

    except PermissionError:
        print(
            f"[Permission Denied] {directory}"
        )

        return []

    except OSError as exc:
        print(
            f"[Error] {directory}: {exc}"
        )

        return []

    visible_entries: list[
        tuple[Path, bool]
    ] = []

    for entry in entries:
        is_dir = safe_is_dir(entry)

        # .git 目录本身始终保留并打印，
        # 但绝不会递归进入其中。
        if is_git_directory(entry) and is_dir:
            visible_entries.append(
                (
                    entry,
                    is_dir,
                )
            )
            continue

        if ignore_stack.is_ignored(
            entry,
            is_dir=is_dir,
        ):
            continue

        visible_entries.append(
            (
                entry,
                is_dir,
            )
        )

    # 排序方式：
    #
    # 1. 目录优先；
    # 2. 文件其次；
    # 3. 名称忽略大小写排序。
    visible_entries.sort(
        key=lambda item: (
            not item[1],
            item[0].name.casefold(),
        )
    )

    return visible_entries


def print_tree(
    directory: Path,
    ignore_stack: GitIgnoreStack,
    prefix: str = "",
) -> None:
    """
    递归打印目录树。

    示例：

    project/
    ├── src/
    │   ├── main.py
    │   └── utils.py
    ├── README.md
    └── requirements.txt

    核心 .gitignore 规则出入栈模型：

        push(current)
            |
            +-- child A
            |      push(A)
            |      ...
            |      pop(A)
            |
            +-- child B
            |      push(B)
            |      ...
            |      pop(B)
            |
        pop(current)

    因此 A 的 .gitignore 不会污染 B。
    """

    # --------------------------------------------------
    # 最后一层防线：即使调用者错误地对 .git 调用了
    # print_tree()，也直接返回，绝不枚举 .git 的内容。
    #
    # .git 目录本身由父目录负责打印；这里仅阻止进入。
    # --------------------------------------------------

    if is_git_directory(directory):
        return

    # --------------------------------------------------
    # 进入当前结点：
    # 加载当前目录自己的 .gitignore。
    # --------------------------------------------------

    ignore_stack.push_directory(
        directory
    )

    try:
        entries = get_visible_entries(
            directory,
            ignore_stack,
        )

        total = len(entries)

        for index, (
            entry,
            is_dir,
        ) in enumerate(entries):

            is_last = (
                index == total - 1
            )

            if is_last:
                connector = "└── "
            else:
                connector = "├── "

            name = display_name(
                entry,
                is_dir=is_dir,
            )

            print(
                f"{prefix}"
                f"{connector}"
                f"{name}"
            )

            # ------------------------------------------
            # 递归进入普通子目录。
            #
            # 特殊规则：
            #
            # 1. .git 目录只打印目录本身，不进入；
            # 2. 不跟随目录符号链接，避免循环递归。
            # ------------------------------------------

            if (
                is_dir
                and not is_git_directory(entry)
                and not entry.is_symlink()
            ):
                if is_last:
                    child_prefix = (
                        prefix
                        + "    "
                    )

                else:
                    child_prefix = (
                        prefix
                        + "│   "
                    )

                print_tree(
                    entry,
                    ignore_stack,
                    prefix=child_prefix,
                )

    finally:
        # --------------------------------------------------
        # 无论递归期间是否出现异常，
        # 都必须弹出当前目录规则。
        #
        # 这是保证兄弟目录不会互相污染的关键。
        # --------------------------------------------------

        ignore_stack.pop_directory()


def main() -> None:
    directory = select_directory()

    if directory is None:
        print("未选择目录。")
        return

    if not directory.is_dir():
        root = tk.Tk()

        root.withdraw()

        messagebox.showerror(
            "错误",
            (
                "目录不存在：\n"
                f"{directory}"
            ),
            parent=root,
        )

        root.destroy()

        return

    print()
    print(f"{directory.name}/")

    ignore_stack = GitIgnoreStack()

    print_tree(
        directory,
        ignore_stack,
    )

    print()


if __name__ == "__main__":
    main()
