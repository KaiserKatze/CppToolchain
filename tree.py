#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
import tkinter as tk
from tkinter import filedialog


def select_directory() -> Path | None:
    """
    打开目录选择 Dialog。
    """
    root = tk.Tk()
    root.withdraw()

    root.attributes("-topmost", True)

    directory = filedialog.askdirectory(
        title="请选择要查看的目录"
    )

    root.destroy()

    if not directory:
        return None

    return Path(directory)


def print_tree(
    directory: Path,
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
    """

    try:
        entries = list(directory.iterdir())
    except PermissionError:
        print(f"{prefix}[Permission Denied]")
        return
    except OSError as exc:
        print(f"{prefix}[Error: {exc}]")
        return

    # 目录优先，然后文件；名称忽略大小写排序
    entries.sort(
        key=lambda p: (
            not p.is_dir(),
            p.name.lower(),
        )
    )

    count = len(entries)

    for index, entry in enumerate(entries):
        is_last = index == count - 1

        connector = "└── " if is_last else "├── "

        if entry.is_dir():
            print(f"{prefix}{connector}{entry.name}/")
        else:
            print(f"{prefix}{connector}{entry.name}")

        if entry.is_dir():
            child_prefix = prefix + (
                "    " if is_last else "│   "
            )

            print_tree(
                entry,
                prefix=child_prefix,
            )


def main() -> None:
    directory = select_directory()

    if directory is None:
        print("未选择目录。")
        return

    print()
    print(f"{directory.name}/")

    print_tree(directory)

    print()


if __name__ == "__main__":
    main()
