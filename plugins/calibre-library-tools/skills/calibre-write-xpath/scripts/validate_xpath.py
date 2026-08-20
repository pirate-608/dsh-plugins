#!/usr/bin/env python3
"""Validate XPath with Calibre's bundled Python/lxml runtime."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lxml import etree


NAMESPACES = {
    "h": "http://www.w3.org/1999/xhtml",
    "epub": "http://www.idpf.org/2007/ops",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "ncx": "http://www.daisy.org/z3986/2005/ncx/",
    "re": "http://exslt.org/regular-expressions",
    "svg": "http://www.w3.org/2000/svg",
    "m": "http://www.w3.org/1998/Math/MathML",
}


def parse_namespace(value: str) -> tuple[str, str]:
    prefix, separator, uri = value.partition("=")
    if not separator or not prefix or not uri:
        raise argparse.ArgumentTypeError("namespace must be prefix=URI")
    return prefix, uri


def node_preview(tree: etree._ElementTree, node: etree._Element) -> dict[str, object]:
    text = " ".join("".join(node.itertext()).split())
    return {
        "path": tree.getpath(node),
        "tag": node.tag,
        "id": node.get("id"),
        "class": node.get("class"),
        "text": text[:180],
    }


def scalar_preview(value: object) -> object:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")[:300]
    if isinstance(value, str):
        return value[:300]
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return str(value)[:300]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate XPath 1.0 with Calibre's lxml runtime and ebook namespaces."
    )
    parser.add_argument("--file", required=True, type=Path, help="XML/XHTML/OPF/NCX file")
    parser.add_argument("--xpath", required=True, help="XPath expression")
    parser.add_argument(
        "--ns",
        action="append",
        default=[],
        type=parse_namespace,
        metavar="PREFIX=URI",
        help="add or override a namespace mapping; may be repeated",
    )
    parser.add_argument("--max", type=int, default=20, help="maximum result previews")
    parser.add_argument(
        "--require-elements",
        action="store_true",
        help="fail unless the expression returns only element nodes",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    namespaces = dict(NAMESPACES)
    namespaces.update(dict(args.ns))

    try:
        parser = etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            recover=False,
            huge_tree=False,
            remove_blank_text=False,
        )
        tree = etree.parse(str(args.file), parser)
        result = tree.xpath(args.xpath, namespaces=namespaces, smart_strings=False)
    except (OSError, etree.XMLSyntaxError, etree.XPathError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    if isinstance(result, list):
        elements_only = all(isinstance(item, etree._Element) for item in result)
        if args.require_elements and not elements_only:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "XPath did not return only element nodes",
                        "count": len(result),
                        "result_types": sorted({type(item).__name__ for item in result}),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 3

        previews = []
        for item in result[: max(args.max, 0)]:
            if isinstance(item, etree._Element):
                previews.append(node_preview(tree, item))
            else:
                previews.append(scalar_preview(item))
        payload = {
            "ok": True,
            "result_type": "node-set",
            "count": len(result),
            "elements_only": elements_only,
            "matches": previews,
            "truncated": len(result) > len(previews),
        }
    else:
        if args.require_elements:
            print(
                json.dumps(
                    {"ok": False, "error": "XPath returned a scalar, not element nodes"},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 3
        payload = {
            "ok": True,
            "result_type": type(result).__name__,
            "value": scalar_preview(result),
        }

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
