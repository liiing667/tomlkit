"""The rendering layer of tomlkit's format preservation.

A :class:`~tomlkit.container.Container` (layer 1 structure, possibly mutated
through the layer 2 editing API) is turned back into text purely from the
items it holds and their :class:`~tomlkit.trivia.Trivia`. The parser is not
involved, so this layer can be tested on its own: build or edit a structure,
render it, compare strings.

:class:`Container` keeps thin ``_render_*`` delegates to this module so the
public behaviour (``dumps`` output) is defined in exactly one place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tomlkit._compat import decode
from tomlkit.items import AoT
from tomlkit.items import Item
from tomlkit.items import Key
from tomlkit.items import Null
from tomlkit.items import Table
from tomlkit.items import Whitespace


if TYPE_CHECKING:
    from tomlkit.container import Container


class Renderer:
    """Renders a container back to its TOML text representation."""

    def render(self, container: Container) -> str:
        s = ""
        for k, v in container.body:
            if k is not None:
                if isinstance(v, Table):
                    if (
                        s.strip(" ")
                        and not s.strip(" ").endswith("\n")
                        and "\n" not in v.trivia.indent
                    ):
                        s += "\n"
                    s += self.render_table(k, v)
                elif isinstance(v, AoT):
                    if (
                        s.strip(" ")
                        and not s.strip(" ").endswith("\n")
                        and "\n" not in v.trivia.indent
                    ):
                        s += "\n"
                    s += self.render_aot(k, v)
                else:
                    s += self.render_simple_item(k, v)
            else:
                s += self.render_simple_item(k, v)

        return s

    def render_table(self, key: Key, table: Table, prefix: str | None = None) -> str:
        cur = ""

        if table.display_name is not None:
            _key = table.display_name
        else:
            _key = key.as_string()

            if prefix is not None:
                _key = prefix + "." + _key

        if (
            not table.is_super_table()
            or (
                any(
                    not isinstance(v, (Table, AoT, Whitespace, Null))
                    for _, v in table.value.body
                )
                and not key.is_dotted()
            )
            or (
                any(
                    k is not None and k.is_dotted()
                    for k, v in table.value.body
                    if isinstance(v, Table)
                )
                and not key.is_dotted()
            )
        ):
            open_, close = "[", "]"
            if table.is_aot_element():
                open_, close = "[[", "]]"

            newline_in_table_trivia = (
                "\n" if "\n" not in table.trivia.trail and len(table.value) > 0 else ""
            )
            cur += (
                f"{table.trivia.indent}"
                f"{open_}"
                f"{decode(_key)}"
                f"{close}"
                f"{table.trivia.comment_ws}"
                f"{decode(table.trivia.comment)}"
                f"{table.trivia.trail}"
                f"{newline_in_table_trivia}"
            )
        elif table.trivia.indent == "\n":
            cur += table.trivia.indent

        for k, v in table.value.body:
            if isinstance(v, Table):
                if (
                    cur.strip(" ")
                    and not cur.strip(" ").endswith("\n")
                    and "\n" not in v.trivia.indent
                ):
                    cur += "\n"
                assert k is not None
                if v.is_super_table():
                    if k.is_dotted() and not key.is_dotted():
                        # Dotted key inside table
                        cur += self.render_table(k, v)
                    else:
                        cur += self.render_table(k, v, prefix=_key)
                else:
                    cur += self.render_table(k, v, prefix=_key)
            elif isinstance(v, AoT):
                if (
                    cur.strip(" ")
                    and not cur.strip(" ").endswith("\n")
                    and "\n" not in v.trivia.indent
                ):
                    cur += "\n"
                assert k is not None
                cur += self.render_aot(k, v, prefix=_key)
            else:
                cur += self.render_simple_item(
                    k, v, prefix=_key if key.is_dotted() else None
                )

        return cur

    def render_aot(self, key: Key, aot: AoT, prefix: str | None = None) -> str:
        _key = key.as_string()
        if prefix is not None:
            _key = prefix + "." + _key

        cur = ""
        _key = decode(_key)
        for table in aot.body:
            cur += self.render_aot_table(table, prefix=_key)

        return cur

    def render_aot_table(self, table: Table, prefix: str | None = None) -> str:
        cur = ""
        _key = prefix or ""
        open_, close = "[[", "]]"

        cur += (
            f"{table.trivia.indent}"
            f"{open_}"
            f"{decode(_key)}"
            f"{close}"
            f"{table.trivia.comment_ws}"
            f"{decode(table.trivia.comment)}"
            f"{table.trivia.trail}"
        )

        for k, v in table.value.body:
            if isinstance(v, Table):
                assert k is not None
                if v.is_super_table():
                    if k.is_dotted():
                        # Dotted key inside table
                        cur += self.render_table(k, v)
                    else:
                        cur += self.render_table(k, v, prefix=_key)
                else:
                    cur += self.render_table(k, v, prefix=_key)
            elif isinstance(v, AoT):
                assert k is not None
                cur += self.render_aot(k, v, prefix=_key)
            else:
                cur += self.render_simple_item(k, v)

        return cur

    def render_simple_item(
        self, key: Key | None, item: Item, prefix: str | None = None
    ) -> str:
        if key is None:
            return item.as_string()

        _key = key.as_string()
        if prefix is not None:
            _key = prefix + "." + _key

        return (
            f"{item.trivia.indent}"
            f"{decode(_key)}"
            f"{key.sep}"
            f"{decode(item.as_string())}"
            f"{item.trivia.comment_ws}"
            f"{decode(item.trivia.comment)}"
            f"{item.trivia.trail}"
        )


def render(container: Container) -> str:
    """Render a container to its TOML text representation."""
    return Renderer().render(container)
