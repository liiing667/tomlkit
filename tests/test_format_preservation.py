"""Round-trip tests for the three format-preservation layers.

The layers under test (see ``tomlkit/trivia.py`` and ``tomlkit/renderer.py``):

1. **Parse -> structure with format info**: the parser attaches ``Trivia``
   (indent / comment_ws / comment / trail), key separators and array
   whitespace to items. These tests inspect the structure directly, without
   rendering.
2. **Edit**: structural edits on containers/items. Only a small set of
   trivia is recomputed on edit (documented per test); everything else must
   survive untouched.
3. **Render**: a structure is rendered back to text by
   ``tomlkit.renderer.Renderer`` alone, so fragments can be round-trip
   checked without comparing whole documents.
"""

from tomlkit import dumps
from tomlkit import parse
from tomlkit.items import Comment
from tomlkit.items import Whitespace
from tomlkit.renderer import Renderer


class TestParsedStructureCarriesFormatInfo:
    """Layer 1: parsing produces a structure that carries all format info."""

    def test_item_trivia_fields(self):
        doc = parse("a = 1  # hi\n")
        item = doc.body[0][1]
        assert item.trivia.indent == ""
        assert item.trivia.comment_ws == "  "
        assert item.trivia.comment == "# hi"
        assert item.trivia.trail == "\n"

    def test_indented_item_trivia(self):
        doc = parse("[t]\n    a = 1\n")
        item = doc["t"].value.body[0][1]
        assert item.trivia.indent == "    "

    def test_key_separator_is_preserved(self):
        doc = parse("a= 1\nb  =2\n")
        assert doc.body[0][0].sep == "= "
        # whitespace before "=" is captured in the key's original text
        assert doc.body[1][0].sep == "="
        assert doc.body[1][0].as_string() == "b  "

    def test_standalone_comments_and_blank_lines_are_body_items(self):
        doc = parse("# head\n\na = 1\n")
        kinds = [type(item).__name__ for _, item in doc.body]
        assert kinds == ["Comment", "Whitespace", "Integer"]
        assert isinstance(doc.body[0][1], Comment)
        assert isinstance(doc.body[1][1], Whitespace)
        assert doc.body[1][1].s == "\n"

    def test_multiline_array_whitespace_is_part_of_the_structure(self):
        doc = parse("a = [\n  1,  # one\n  2,\n]\n")
        array = doc["a"]
        groups = list(array._value)
        assert groups[0].indent.s == "\n  "
        assert groups[0].comment.as_string() == "  # one"
        assert groups[1].value.value == 2
        assert array.as_string() == "[\n  1,  # one\n  2,\n]"

    def test_string_style_is_preserved_in_structure(self):
        doc = parse("a = 'literal'\nb = \"basic\"\nc = '''multi\nline'''\n")
        assert doc["a"].as_string() == "'literal'"
        assert doc["b"].as_string() == '"basic"'
        assert doc["c"].as_string() == "'''multi\nline'''"

    def test_crlf_line_endings_are_captured_in_trail(self):
        doc = parse("a = 1\r\nb = 2\r\n")
        assert doc.body[0][1].trivia.trail == "\r\n"
        assert doc.body[1][1].trivia.trail == "\r\n"


class TestRenderingIsIndependent:
    """Layer 3: rendering works on any structure, parsed or built by hand."""

    def test_render_matches_dumps_for_parsed_document(self):
        src = "# c\n\na = 1  # x\n\n[t]\nb = [1, 2]\n"
        doc = parse(src)
        assert Renderer().render(doc) == dumps(doc) == src

    def test_render_single_item_fragment(self):
        # A fragment can be round-trip checked on its own, without comparing
        # the whole document.
        doc = parse("a = 1  # hi\n")
        key, item = doc.body[0]
        assert Renderer().render_simple_item(key, item) == "a = 1  # hi\n"

    def test_render_table_fragment(self):
        doc = parse("[t]  # section\na = 1\n")
        key, table = next(pair for pair in doc.body if pair[0] is not None)
        assert Renderer().render_table(key, table) == "[t]  # section\na = 1\n"

    def test_render_programmatically_built_structure(self):
        import tomlkit

        doc = tomlkit.document()
        doc.add("a", tomlkit.item(1))
        table = tomlkit.table()
        table.add("b", tomlkit.item("x"))
        doc.add("t", table)
        assert Renderer().render(doc) == "a = 1\n\n[t]\nb = \"x\"\n"


class TestEditsPreserveFormat:
    """Layer 2+3: comparison cases for "format survives edits".

    Each case documents which trivia the edit must recompute; everything
    else is asserted byte-for-byte against the expected output.
    """

    def test_plain_round_trip_baseline(self):
        src = "# top\n\na = 1  # one\nb=2\n\n[t]  # section\n\nx = [1, 2]\n"
        assert dumps(parse(src)) == src

    def test_replace_value_keeps_comment_and_indent(self):
        # Recomputed on edit: the replacement inherits indent/comment_ws/
        # comment/trail from the replaced item (Container._replace_at).
        doc = parse("[t]\n  a = 1  # keep me\nb = 2\n")
        doc["t"]["a"] = 42
        assert dumps(doc) == "[t]\n  a = 42  # keep me\nb = 2\n"

    def test_replace_value_in_document_root(self):
        doc = parse("a = 1  # one\nb = 2\n")
        doc["a"] = 10
        assert dumps(doc) == "a = 10  # one\nb = 2\n"

    def test_add_key_recomputes_previous_trail(self):
        # Recomputed on edit: the previous item's trail gains "\n" so the new
        # key starts on its own line (Container.append).
        doc = parse("a = 1")
        doc["b"] = 2
        assert dumps(doc) == "a = 1\nb = 2\n"

    def test_new_key_gets_default_separator_and_trail(self):
        # Recomputed on edit: new keys/items take the Trivia/SingleKey
        # defaults (" = " separator, "\n" trail); existing items are untouched.
        doc = parse("a=1  # tight\n")
        doc["b"] = 2
        assert dumps(doc) == "a=1  # tight\nb = 2\n"

    def test_add_key_to_table_keeps_table_comment(self):
        doc = parse("[t]  # section\na = 1\n")
        doc["t"]["b"] = 2
        assert dumps(doc) == "[t]  # section\na = 1\nb = 2\n"

    def test_appended_table_gets_blank_line_indent(self):
        # Recomputed on edit: a table appended after non-whitespace content
        # gets trivia.indent "\n" so its header keeps a blank line before it.
        doc = parse("a = 1\n")
        doc["t"] = {}
        assert dumps(doc) == "a = 1\n\n[t]\n"

    def test_appended_table_after_table(self):
        doc = parse("[a]\nx = 1\n")
        doc["b"] = {}
        assert dumps(doc) == "[a]\nx = 1\n\n[b]\n"

    def test_remove_key_keeps_surrounding_comments_and_blanks(self):
        doc = parse("# head\n\na = 1\nb = 2  # two\n\nc = 3\n")
        doc.pop("b")
        assert dumps(doc) == "# head\n\na = 1\n\nc = 3\n"

    def test_remove_table_keeps_rest_of_document(self):
        doc = parse("[a]\nx = 1\n\n[b]  # gone\ny = 2\n\n[c]\nz = 3\n")
        del doc["b"]
        assert dumps(doc) == "[a]\nx = 1\n\n[c]\nz = 3\n"

    def test_multiline_array_append_keeps_layout(self):
        doc = parse("a = [\n  1,  # one\n  2,\n]\n")
        doc["a"].append(3)
        assert dumps(doc) == "a = [\n  1,  # one\n  2,\n  3,\n]\n"

    def test_inline_array_append_keeps_inline_layout(self):
        doc = parse("a = [1, 2]\n")
        doc["a"].append(3)
        assert dumps(doc) == "a = [1, 2, 3]\n"

    def test_crlf_line_endings_survive_edits(self):
        doc = parse("a = 1\r\nb = 2\r\n")
        doc["a"] = 10
        doc["c"] = 3
        assert dumps(doc) == "a = 10\r\nb = 2\r\nc = 3\n"

    def test_key_order_preserved_after_multiple_edits(self):
        doc = parse("z = 1\na = 2\nm = 3\n")
        doc["a"] = 20
        doc["n"] = 4
        del doc["z"]
        assert dumps(doc) == "a = 20\nm = 3\nn = 4\n"

    def test_edit_inside_aot_keeps_element_layout(self):
        src = "[root]\n\n[[fruit]]  # first\nname = 'apple'\n\n[[fruit]]\nname = 'pear'\n"
        doc = parse(src)
        doc["fruit"][0]["name"] = "cherry"
        # note: a *new* value takes the default basic-string style; only the
        # surrounding layout (header comment, blank lines, other elements'
        # quote style) is preserved
        assert dumps(doc) == (
            "[root]\n\n[[fruit]]  # first\nname = \"cherry\"\n\n[[fruit]]\nname = 'pear'\n"
        )

    def test_comment_api_recomputes_comment_ws_and_comment(self):
        # Recomputed on edit: Item.comment() sets comment_ws to " " and
        # comment to the given text; indent and trail are untouched.
        doc = parse("a = 1\n")
        doc["a"].comment("note")
        assert dumps(doc) == "a = 1 # note\n"

    def test_edit_with_existing_blank_line_before_table(self):
        doc = parse("a = 1\n\n[t]\nx = 1\n")
        doc["t"]["x"] = 2
        assert dumps(doc) == "a = 1\n\n[t]\nx = 2\n"

    def test_value_replacement_keeps_string_quote_style_of_neighbours(self):
        doc = parse("a = 'x'\nb = \"y\"\n")
        doc["b"] = "z"
        assert dumps(doc) == "a = 'x'\nb = \"z\"\n"
