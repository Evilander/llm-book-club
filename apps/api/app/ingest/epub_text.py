"""Plain EPUB text and an inert map of its block/inline structure.

No source HTML, attributes, stylesheets, or URLs reach the reader. Coordinates
count Unicode code points in the returned text, including its whitespace.
"""
from itertools import groupby
import re

from bs4 import BeautifulSoup, CData, NavigableString, Tag

BLOCK_TAGS = {"p", "div", "section", "article", "aside", "header", "footer",
              "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "li", "dt", "dd", "pre", "figcaption", "td", "th", "caption"}
INLINE_MARKS = {"em": "emphasis", "i": "emphasis", "strong": "strong", "b": "strong", "code": "code", "sup": "superscript", "sub": "subscript"}
HTML_SPACE = re.compile(r"[ \t\r\n\f]+")


def _tokens(soup: BeautifulSoup | Tag):
    list_labels = {}
    for node in soup.descendants:
        is_break = isinstance(node, Tag) and node.name == "br"
        if not is_break and type(node) not in {NavigableString, CData}:
            continue
        ancestors = [parent for parent in node.parents if isinstance(parent, Tag)]
        owner = next((parent for parent in ancestors if parent.name in BLOCK_TAGS), soup)
        names = {parent.name for parent in ancestors}
        kind = "heading" if owner.name in {"h1", "h2", "h3", "h4", "h5", "h6"} else (
            "preformatted" if "pre" in names else "list_item" if "li" in names else "quote" if "blockquote" in names else "paragraph")
        info = {"kind": kind}
        if kind == "heading":
            info["level"] = int(owner.name[1])
        item = next((parent for parent in ancestors if parent.name == "li"), None)
        if item is not None:
            info["list_id"] = id(item)
            info["list_label"] = "•"
            if item.parent and item.parent.name == "ol":
                if id(item.parent) not in list_labels:
                    labels = {}
                    try:
                        number = int(item.parent.get("start", 1))
                    except (TypeError, ValueError):
                        number = 1
                    for sibling in item.parent.find_all("li", recursive=False):
                        try:
                            number = int(sibling.get("value", number))
                        except (TypeError, ValueError):
                            pass
                        labels[id(sibling)] = f"{max(-9999, min(9999, number))}."
                        number += 1
                    list_labels[id(item.parent)] = labels
                info["list_label"] = list_labels[id(item.parent)].get(id(item), "•")
        marks = sorted({INLINE_MARKS[name] for name in names if name in INLINE_MARKS})
        yield {"owner": id(owner), "info": info, "raw": "\n" if is_break else str(node), "break": is_break, "marks": marks}


def document_text(soup: BeautifulSoup | Tag, *, legacy: bool = False) -> tuple[str, list[dict]]:
    tokens = list(_tokens(soup))
    if legacy:
        return _legacy_text(tokens)
    text_parts, blocks = [], []
    position = 0
    labelled_items = set()
    for _owner, group in groupby(tokens, key=lambda token: token["owner"]):
        group = list(group)
        info = group[0]["info"]
        parts, marks = [], []
        length = 0
        previous = ""
        for token in group:
            value = token["raw"]
            if not token["break"] and info["kind"] != "preformatted":
                value = HTML_SPACE.sub(" ", value)
                if not previous or previous.endswith((" ", "\n")):
                    value = value.lstrip(" ")
            start = length
            parts.append(value)
            length += len(value)
            if value:
                previous = value
                for kind in token["marks"] + (["line_break"] if token["break"] else []):
                    marks.append({"kind": kind, "char_start": start, "char_end": length})
        raw = "".join(parts)
        value = raw.strip("\n") if info["kind"] == "preformatted" else raw.strip()
        if not value.strip():
            continue
        info = _block_info(info, labelled_items)
        trim = raw.find(value)
        if text_parts:
            text_parts.append("\n\n")
            position += 2
        block = {**info, "char_start": position, "char_end": position + len(value), "marks": []}
        for mark in marks:
            start, end = max(trim, mark["char_start"]), min(trim + len(value), mark["char_end"])
            if start < end:
                block["marks"].append({**mark, "char_start": position + start - trim, "char_end": position + end - trim})
        text_parts.append(value)
        blocks.append(block)
        position += len(value)
    return "".join(text_parts), blocks


def _block_info(info: dict, labelled_items: set) -> dict:
    result = {key: value for key, value in info.items() if key not in {"list_id", "list_label"}}
    if "list_id" in info and info["list_id"] not in labelled_items:
        labelled_items.add(info["list_id"])
        result["list_label"] = info["list_label"]
    return result


def _legacy_text(tokens: list[dict]) -> tuple[str, list[dict]]:
    """Reproduce get_text(separator='\\n', strip=True) without rewriting an edition.

    Newlines inserted between inline fragments get inert display annotations;
    their original coordinates remain available to existing citations.
    """
    parts, blocks = [], []
    position = 0
    current = None
    previous = None
    hard_break = False
    intervening_space = False
    labelled_items = set()
    for token in tokens:
        if token["break"]:
            hard_break = True
            continue
        value = token["raw"].strip()
        if not value:
            intervening_space = intervening_space or bool(token["raw"])
            continue
        same = previous is not None and previous["owner"] == token["owner"]
        if parts:
            parts.append("\n")
            if same and current is not None:
                kind = "line_break" if hard_break else "join" if not (
                    intervening_space or previous["raw"][-1:].isspace() or token["raw"][:1].isspace()) else None
                if kind:
                    current["marks"].append({"kind": kind, "char_start": position, "char_end": position + 1})
            position += 1
        if not same:
            current = {**_block_info(token["info"], labelled_items), "char_start": position, "char_end": position, "marks": []}
            blocks.append(current)
        parts.append(value)
        for kind in token["marks"]:
            current["marks"].append({"kind": kind, "char_start": position, "char_end": position + len(value)})
        position += len(value)
        current["char_end"] = position
        previous, hard_break, intervening_space = token, False, False
    return "".join(parts), blocks
