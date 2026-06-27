#!/usr/bin/env python3

"""
扫描 C++ 源文件中的 export/import 语句，构建模块依赖有向图。

功能：
1. 递归扫描指定目录下的 .cpp / .ixx 文件
2. 使用正则表达式提取 `export module` 和 `import` 语句
3. 基于 NetworkX 构建模块依赖有向图
4. 将图导出为 JSON 文件
5. 使用 Matplotlib 绘制依赖图并保存为图片

示例：
    python module_dependency_graph.py --root src
    python module_dependency_graph.py --root src --json-out graph.json --image-out graph.png
    python module_dependency_graph.py --root src --show
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import networkx as nx
from networkx.readwrite import json_graph


SUPPORTED_SUFFIXES = {".cpp", ".ixx"}

# 匹配：
# export module Foo;
# export module Foo.Bar;
EXPORT_MODULE_RE = re.compile(
    r"^\s*export\s+module\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*;",
    re.MULTILINE,
)

# 匹配：
# import Foo;
# import Foo.Bar;
# 不匹配：import <vector>; import "x";
IMPORT_RE = re.compile(
    r"^\s*import\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*;",
    re.MULTILINE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="扫描 C++ 模块 export/import 语句并生成依赖图。"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("src"),
        help="待扫描的根目录，默认是 src",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=Path("module_dependency_graph.json"),
        help="导出的 JSON 文件路径",
    )
    parser.add_argument(
        "--image-out",
        type=Path,
        default=Path("module_dependency_graph.png"),
        help="导出的图片文件路径",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="保存图片后同时弹出窗口显示图像",
    )
    parser.add_argument(
        "--include-external",
        action="store_true",
        help="保留仅被 import、但没有 export 定义的外部模块节点",
    )
    return parser.parse_args()


def iter_source_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            yield path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def extract_module_info(path: Path) -> tuple[str | None, list[str]]:
    text = read_text(path)
    export_match = EXPORT_MODULE_RE.search(text)
    module_name = export_match.group(1) if export_match else None
    imports = IMPORT_RE.findall(text)
    return module_name, imports


def build_graph(root: Path, include_external: bool) -> nx.DiGraph:
    graph = nx.DiGraph()
    declared_modules: set[str] = set()
    imported_modules: set[str] = set()

    for path in iter_source_files(root):
        module_name, imports = extract_module_info(path)
        file_label = str(path.relative_to(root.parent if root.parent != Path("") else root))

        if module_name:
            declared_modules.add(module_name)
            graph.add_node(
                module_name,
                file=file_label,
                kind="declared",
                source=str(path),
            )

        for imported in imports:
            imported_modules.add(imported)
            if module_name:
                graph.add_edge(module_name, imported, source=file_label)

    if include_external:
        for module_name in imported_modules - declared_modules:
            graph.add_node(
                module_name,
                file=None,
                kind="external",
                source=None,
            )
    else:
        for module_name in list(graph.nodes):
            if module_name not in declared_modules:
                graph.remove_node(module_name)

    for module_name in graph.nodes:
        graph.nodes[module_name]["in_degree"] = graph.in_degree(module_name)
        graph.nodes[module_name]["out_degree"] = graph.out_degree(module_name)

    return graph


def save_graph_json(graph: nx.DiGraph, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = json_graph.node_link_data(graph)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def draw_graph(graph: nx.DiGraph, output_path: Path, show: bool) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if graph.number_of_nodes() == 0:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, "No modules found", ha="center", va="center", fontsize=16)
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(output_path, dpi=200, bbox_inches="tight")
        if show:
            plt.show()
        plt.close(fig)
        return

    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False

    fig_width = max(12, graph.number_of_nodes() * 0.8)
    fig_height = max(8, graph.number_of_nodes() * 0.5)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))

    pos = nx.spring_layout(graph, seed=42, k=1.2 / max(1, graph.number_of_nodes() ** 0.5))

    declared_nodes = [
        node for node, data in graph.nodes(data=True) if data.get("kind") == "declared"
    ]
    external_nodes = [
        node for node, data in graph.nodes(data=True) if data.get("kind") == "external"
    ]

    nx.draw_networkx_nodes(
        graph,
        pos,
        nodelist=declared_nodes,
        node_color="#4C78A8",
        node_size=2200,
        alpha=0.95,
        ax=ax,
    )
    if external_nodes:
        nx.draw_networkx_nodes(
            graph,
            pos,
            nodelist=external_nodes,
            node_color="#F58518",
            node_size=2000,
            alpha=0.9,
            ax=ax,
        )

    nx.draw_networkx_edges(
        graph,
        pos,
        edge_color="#777777",
        width=1.5,
        arrows=True,
        arrowsize=18,
        arrowstyle="-|>",
        min_source_margin=15,
        min_target_margin=15,
        ax=ax,
    )

    nx.draw_networkx_labels(
        graph,
        pos,
        font_size=10,
        font_color="black",
        font_weight="bold",
        ax=ax,
    )

    ax.set_title("C++ 模块依赖图", fontsize=18)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")

    if show:
        plt.show()

    plt.close(fig)


def main() -> None:
    args = parse_args()
    root = args.root.resolve()

    if not root.exists():
        raise FileNotFoundError(f"扫描目录不存在: {root}")

    graph = build_graph(root, include_external=args.include_external)
    save_graph_json(graph, args.json_out.resolve())
    draw_graph(graph, args.image_out.resolve(), args.show)

    print(f"扫描目录: {root}")
    print(f"模块数: {graph.number_of_nodes()}")
    print(f"依赖边数: {graph.number_of_edges()}")
    print(f"JSON 已写入: {args.json_out.resolve()}")
    print(f"图片已写入: {args.image_out.resolve()}")


if __name__ == "__main__":
    main()
