#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _int_attr(element: ET.Element, name: str) -> int:
    try:
        return int(element.attrib.get(name, "0") or 0)
    except ValueError:
        return 0


def _float_attr(element: ET.Element, name: str) -> float:
    try:
        return float(element.attrib.get(name, "0") or 0)
    except ValueError:
        return 0.0


def summarize_junit(path: Path) -> dict[str, float | int]:
    root = ET.parse(path).getroot()

    if root.tag == "testsuite":
        suites = [root]
    elif root.tag == "testsuites":
        suites = [suite for suite in root.findall("testsuite")]
    else:
        raise ValueError(f"unsupported junit root tag: {root.tag}")

    summary = {
        "tests": 0,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "time": 0.0,
        "suites": len(suites),
    }
    for suite in suites:
        summary["tests"] += _int_attr(suite, "tests")
        summary["failures"] += _int_attr(suite, "failures")
        summary["errors"] += _int_attr(suite, "errors")
        summary["skipped"] += _int_attr(suite, "skipped")
        summary["time"] += _float_attr(suite, "time")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize a JUnit XML report as Markdown.")
    parser.add_argument("path", help="Path to the JUnit XML file.")
    parser.add_argument("--title", default="JUnit Summary", help="Heading shown in the markdown output.")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Emit a missing-file note instead of failing when the XML file does not exist.",
    )
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        if args.allow_missing:
            print(f"### {args.title}")
            print()
            print(f"- status: missing")
            print(f"- junit_xml: `{path}`")
            return 0
        raise SystemExit(f"JUnit XML not found: {path}")

    summary = summarize_junit(path)
    print(f"### {args.title}")
    print()
    print(f"- tests: {summary['tests']}")
    print(f"- failures: {summary['failures']}")
    print(f"- errors: {summary['errors']}")
    print(f"- skipped: {summary['skipped']}")
    print(f"- suites: {summary['suites']}")
    print(f"- time_seconds: {summary['time']:.2f}")
    print(f"- junit_xml: `{path}`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
