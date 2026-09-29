"""Format preservation across the parse -> edit -> render layers.

The format-preservation logic is split into three independently testable
layers:

1. **Structure** (:mod:`tomlkit.parser` + :mod:`tomlkit.items`): parsing
   captures the original formatting on every item as ``Trivia``
   (``indent``, ``comment_ws``, ``comment``, ``trail``) and on every key as
   ``Key.sep``.  These tests verify the capture without rendering a whole
   document.
2. **Editing** (:class:`tomlkit.container.Container` and the mutation
   methods of ``Array``/``InlineTable``): edits change the structure and
   must *recompute* the format information that the edit invalidates:
   - replacing a value in place copies the old value's ``Trivia`` and the
     old key's ``sep`` onto the new item (``Container._replace_at``);
   - appending a new key synthesizes a default ``sep`` of ``" = "`` and,
     for tables, a leading newline in ``trivia.indent``
     (``Container.append``);
   - appending to an ``Array`` rewrites the previous last element's comma
     whitespace (``Array.append``);
   - appending to a parsed ``InlineTable`` gives the new item a single
     space indent, and commas are re-derived from the explicit-comma
     whitespace markers at render time (``InlineTable.append``);
   - moving a value into an inline table clears its comment, which cannot
     be rendered inline (``InlineTable.__setitem__``);
   - renaming/reparenting a table invalidates its cached ``display_name``
     (``invalidate_display_name``).
3. **Rendering** (:class:`tomlkit.render.Renderer`): walks the structure
   and reproduces the text.  It only reads trivia, so it can be exercised
   on hand-built structures without parsing anything.

The edit-preservation matrix below pins the exact rendered output of
editing a parsed document, so a regression in any of the three layers
fails a focused test instead of a whole-document comparison.
"""

import pytest

import tomlkit

from tomlkit import parse
from tomlkit.container import Container
from tomlkit.items import SingleKey
from tomlkit.items import Trivia
from tomlkit.items import item
from tomlkit.render import Renderer


# ---------------------------------------------------------------------------
# Layer 1: parsing captures format information on the structure
# ---------------------------------------------------------------------------


def test_parsing_captures_value_trivia() -> None:
    doc = parse("a = 1 # keep\n")

    trivia = doc["a"].trivia
    assert trivia.indent == ""
    assert trivia.comment_ws == " "
    assert trivia.comment == "# keep"
    assert trivia.trail == "\n"


def test_parsing_captures_indent_and_key_separator() -> None:
    doc = parse("  a  =  1\n")

    key, value = next(iter(doc.body))
    assert value.trivia.indent == "  "
    # Whitespace before "=" stays on the key, whitespace after on the separator.
    assert key.as_string() == "a  "
    assert key.sep == "=  "


def test_parsing_captures_crlf_line_endings() -> None:
    doc = parse("a = 1\r\nb = 2\r\n")

    assert doc["a"].trivia.trail == "\r\n"
    assert doc["b"].trivia.trail == "\r\n"


def test_parsing_captures_table_header_trivia() -> None:
    doc = parse("[t]  # section\nx = 1\n")

    table = doc["t"]
    assert table.trivia.comment_ws == "  "
    assert table.trivia.comment == "# section"


# ---------------------------------------------------------------------------
# Layer 3: rendering works on hand-built structures, no parser involved
# ---------------------------------------------------------------------------


def test_render_simple_item_from_hand_built_structure() -> None:
    renderer = Renderer()

    rendered = renderer.render_simple_item(SingleKey("a"), item(1))

    assert rendered == "a = 1\n"


def test_render_container_from_hand_built_structure() -> None:
    container = Container()
    container.append("a", 1)
    container.append("b", "x")

    assert Renderer().render_container(container) == 'a = 1\nb = "x"\n'


def test_render_multiline_array_from_hand_built_structure() -> None:
    array = item([1, 2]).multiline(True)

    assert Renderer().render_array(array) == "[\n    1,\n    2,\n]"


def test_render_inline_table_from_hand_built_structure() -> None:
    table = tomlkit.inline_table()
    table.append("a", 1)
    table.append("b", 2)

    assert Renderer().render_inline_table(table) == "{a = 1, b = 2}"


def test_renderer_matches_public_entry_point_on_parsed_documents() -> None:
    doc = parse(
        "# head\n"
        "a = 1 # one\n"
        "arr = [\n  1,\n  2, # two\n]\n"
        "inline = {x = 1, y = 2}\n"
        "\n"
        "[t]  # section\n"
        "s = 'lit'\n"
        "[[t.aot]]\n"
        "n = 1\n"
    )

    assert Renderer().render_container(doc) == doc.as_string()


# ---------------------------------------------------------------------------
# Layer 2 + 3: editing preserves the surrounding formatting
# ---------------------------------------------------------------------------

EDIT_CASES = [
    # (name, source, edit, expected)
    (
        "set-value-keeps-comment",
        "a = 1 # keep\nb = 2\n",
        lambda d: d.__setitem__("a", 99),
        "a = 99 # keep\nb = 2\n",
    ),
    (
        "set-value-keeps-key-alignment",
        "a   = 1\nbb  = 2\n",
        lambda d: d.__setitem__("a", 22),
        "a   = 22\nbb  = 2\n",
    ),
    (
        "set-value-keeps-crlf",
        "a = 1\r\nb = 2\r\n",
        lambda d: d.__setitem__("a", 9),
        "a = 9\r\nb = 2\r\n",
    ),
    (
        "set-value-keeps-indent",
        "  a = 1\n",
        lambda d: d.__setitem__("a", 2),
        "  a = 2\n",
    ),
    (
        "add-key-uses-default-separator",
        "a = 1\n",
        lambda d: d.__setitem__("b", 2),
        "a = 1\nb = 2\n",
    ),
    (
        "add-key-to-table-body",
        "[t]\nx = 1\n",
        lambda d: d["t"].__setitem__("y", 2),
        "[t]\nx = 1\ny = 2\n",
    ),
    (
        "remove-key-keeps-neighbours",
        "a = 1 # x\nb = 2 # y\n",
        lambda d: d.__delitem__("a"),
        "b = 2 # y\n",
    ),
    (
        "comments-and-blank-lines-survive-edit",
        "# top\na = 1\n\n# mid\n[t] # tc\nx = 1\n",
        lambda d: d["t"].__setitem__("x", 2),
        "# top\na = 1\n\n# mid\n[t] # tc\nx = 2\n",
    ),
    (
        "array-append-inline",
        "a = [1, 2] # c\n",
        lambda d: d["a"].append(3),
        "a = [1, 2, 3] # c\n",
    ),
    (
        "array-append-multiline-keeps-comments",
        "a = [\n  1, # one\n]\n",
        lambda d: d["a"].append(2),
        "a = [\n  1, # one\n  2,\n]\n",
    ),
    (
        "array-setitem-keeps-group-whitespace",
        "a = [ 1,  2 ]\n",
        lambda d: d["a"].__setitem__(0, 9),
        "a = [ 9,  2 ]\n",
    ),
    (
        "inline-table-add-gets-single-space",
        "p = {x = 1}\n",
        lambda d: d["p"].append("y", 2),
        "p = {x = 1, y = 2}\n",
    ),
    (
        "inline-table-remove-recomputes-commas",
        "p = {x = 1, y = 2}\n",
        lambda d: d["p"].__delitem__("x"),
        "p = { y = 2}\n",
    ),
    (
        "inline-table-set-keeps-inner-spacing",
        "p = { x = 1, y = 2 }\n",
        lambda d: d["p"].__setitem__("x", 9),
        "p = { x = 9, y = 2 }\n",
    ),
    (
        "dotted-key-value-set",
        "a.b = 1 # c\n",
        lambda d: d["a"].__setitem__("b", 2),
        "a.b = 2 # c\n",
    ),
    (
        "aot-element-edit",
        "[[a]]\nx = 1\n[[a]]\nx = 2\n",
        lambda d: d["a"][1].__setitem__("y", 3),
        "[[a]]\nx = 1\n[[a]]\nx = 2\ny = 3\n",
    ),
    (
        "super-table-blank-line-preserved",
        "[a]\n\n[a.b]\nx = 1\n",
        lambda d: d["a"]["b"].__setitem__("x", 2),
        "[a]\n\n[a.b]\nx = 2\n",
    ),
    (
        "string-escaping-on-new-value",
        "s = 'plain'\n",
        lambda d: d.__setitem__("s", "x\ny\tt"),
        's = "x\\ny\\tt"\n',
    ),
    (
        "unicode-key-order-preserved",
        "z = 1\na = 2\n",
        lambda d: d.__setitem__("m", 3),
        "z = 1\na = 2\nm = 3\n",
    ),
]


@pytest.mark.parametrize("name,source,edit,expected", EDIT_CASES, ids=lambda c: c if isinstance(c, str) and "\n" not in c else None)
def test_edit_preserves_format(name, source, edit, expected) -> None:
    doc = parse(source)
    edit(doc)
    assert tomlkit.dumps(doc) == expected


# ---------------------------------------------------------------------------
# Format information that edits must recompute
# ---------------------------------------------------------------------------


def test_replaced_value_inherits_trivia_and_separator() -> None:
    doc = parse("a  =  1 # keep\n")
    old = doc["a"]

    doc["a"] = 2
    new = doc.item("a")

    assert new.trivia.indent == old.trivia.indent
    assert new.trivia.comment_ws == old.trivia.comment_ws
    assert new.trivia.comment == old.trivia.comment
    assert new.trivia.trail == old.trivia.trail
    key, _ = next(iter(doc.body))
    assert key.as_string() == "a  "
    assert key.sep == "=  "


def test_appended_key_gets_fresh_default_trivia() -> None:
    doc = parse("a = 1\n")
    doc["b"] = 2

    key, value = list(doc.body)[-1]
    assert key.sep == " = "
    assert value.trivia == Trivia()


def test_value_moved_into_inline_table_loses_comment() -> None:
    doc = parse("p = {x = 1}\n")
    commented = item(2)
    commented.comment("# nope")

    doc["p"]["y"] = commented

    assert doc["p"]["y"].trivia.comment == ""
    assert tomlkit.dumps(doc) == "p = {x = 1,y = 2}\n"


def test_reparented_table_recomputes_display_name() -> None:
    doc = parse("[t]\nx = 1\n")
    table = doc["t"]
    doc["outer"] = tomlkit.table()
    doc["outer"]["inner"] = table

    rendered = tomlkit.dumps(doc)
    assert "[t.inner]" not in rendered
    assert "[outer.inner]" in rendered
