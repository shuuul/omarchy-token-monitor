#!/usr/bin/env python3
"""Catch QML declarations that collide with a built-in name."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ITEM = {
    "activeFocus",
    "activeFocusOnTab",
    "anchors",
    "antialiasing",
    "baselineOffset",
    "children",
    "childrenRect",
    "clip",
    "containmentMask",
    "data",
    "enabled",
    "focus",
    "height",
    "implicitHeight",
    "implicitWidth",
    "layer",
    "opacity",
    "parent",
    "resources",
    "rotation",
    "scale",
    "smooth",
    "state",
    "states",
    "transform",
    "transformOrigin",
    "transitions",
    "visible",
    "visibleChildren",
    "width",
    "x",
    "y",
    "z",
}
POSITIONER = {
    "add",
    "bottomPadding",
    "layoutDirection",
    "leftPadding",
    "move",
    "padding",
    "populate",
    "rightPadding",
    "spacing",
    "topPadding",
}
RECTANGLE = {"border", "color", "gradient", "radius"}

BUILTINS = {
    "Item": ITEM,
    "Column": ITEM | POSITIONER,
    "Row": ITEM | POSITIONER,
    "Grid": ITEM | POSITIONER,
    "Flow": ITEM | POSITIONER,
    "Rectangle": ITEM | RECTANGLE,
    "BorderSurface": ITEM | RECTANGLE,
    "CursorSurface": ITEM,
    "Canvas": ITEM,
    "Flickable": ITEM,
    "Text": ITEM,
    "Panel": ITEM,
}

DECLARATION = re.compile(
    r"^\s*(?:readonly\s+|required\s+|default\s+)*property\s+[\w.<>]+\s+(\w+)"
)
SIGNAL = re.compile(r"^\s*signal\s+(\w+)")
OPENING = re.compile(r"([A-Za-z_][\w.]*)\s*$")


def strip_noise(line):
    out = []
    quote = None
    index = 0
    while index < len(line):
        char = line[index]
        if quote:
            out.append(" ")
            if char == "\\":
                out.append(" ")
                index += 2
                continue
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            out.append(" ")
        elif char == "/" and index + 1 < len(line) and line[index + 1] == "/":
            break
        else:
            out.append(char)
        index += 1
    return "".join(out)


def check(path):
    problems = []
    stack = []
    in_block_comment = False

    for number, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw
        if in_block_comment:
            end = line.find("*/")
            if end < 0:
                continue
            line = line[end + 2 :]
            in_block_comment = False
        start = line.find("/*")
        if start >= 0:
            if "*/" in line[start:]:
                line = line[:start] + line[line.find("*/", start) + 2 :]
            else:
                line = line[:start]
                in_block_comment = True

        clean = strip_noise(line)
        declaration = DECLARATION.match(line)
        signal = SIGNAL.match(line)
        if (declaration or signal) and stack:
            name = (declaration or signal).group(1)
            type_name, seen = stack[-1]
            forbidden = BUILTINS.get(type_name, set())
            if name in forbidden:
                problems.append(
                    f"{path.name}:{number}: `{name}` is already a property of {type_name}"
                )
            if name in seen:
                problems.append(f"{path.name}:{number}: `{name}` is declared twice")
            seen.add(name)

        for index, char in enumerate(clean):
            if char == "{":
                prefix = clean[:index].rstrip()
                match = OPENING.search(prefix)
                stack.append(((match.group(1) if match else "?"), set()))
            elif char == "}":
                if not stack:
                    problems.append(f"{path.name}:{number}: unbalanced closing brace")
                else:
                    stack.pop()

    if stack:
        problems.append(f"{path.name}: {len(stack)} unclosed brace(s)")
    return problems


def main():
    files = sorted(ROOT.glob("*.qml"))
    if not files:
        print("no QML files found", file=sys.stderr)
        return 1
    problems = [problem for path in files for problem in check(path)]
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    print(f"qml name checks passed ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
