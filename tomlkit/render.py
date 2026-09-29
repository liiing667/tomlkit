"""Rendering layer: turn a format-carrying structure back into TOML text.

This module is the third of the three format-preservation layers:

1. Parsing (:mod:`tomlkit.parser`) produces a structure in which every
   :class:`~tomlkit.items.Item` carries its original formatting as
   :class:`~tomlkit.items.Trivia` (indent, comment whitespace, comment,
   trailing newline) and every :class:`~tomlkit.items.Key` carries its
   separator.
2. Editing (:class:`~tomlkit.container.Container`, ``Array``/``InlineTable``
   mutation methods) changes that structure, synthesizing trivia for freshly
   created items so they blend into the surrounding formatting.
3. Rendering (this module) walks the structure and reproduces the text.

Keeping every formatting decision here means a rendering rule only has to
change in one place, and the layer can be unit-tested on hand-built
structures without parsing a whole document.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tomlkit._compat import decode
from tomlkit.items import AoT
from tomlkit.items import InlineTable
from tomlkit.items import Item
from tomlkit.items import Key
from tomlkit.items import Null
from tomlkit.items import Table
from tomlkit.items import Whitespace


if TYPE_CHECKING:
    from tomlkit.container import Container
    from tomlkit.items import Array


class Renderer:
    """Render items and containers back to TOML text.

    The methods only *read* trivia and separators from the structure; they
    never mutate it. All whitespace, comment, comma-placement and newline
    decisions are made here.
    """

    def render_container(self, container: Container) -> str:
        """Render a container body (document, table or out-of-order proxy)."""
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
                    for _, v in table._value.body
                )
                and not key.is_dotted()
            )
            or (
                any(
                    k is not None and k.is_dotted()
                    for k, v in table._value.body
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

        for k, v in table._value.body:
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

        for k, v in table._value.body:
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

    def render_inline_table(self, table: InlineTable) -> str:
        buf = "{"
        emitted_key = False
        needs_separator = False
        # Single pass over the body to precompute everything the render loop
        # needs, instead of rescanning the tail on every separator comma (which
        # was O(n^2) on large inline tables): whether any explicit-comma
        # whitespace is present, the index of the last real key, and the index
        # of the last Null (deleted) element.
        has_explicit_commas = False
        last_item_idx = None
        last_null_idx = -1
        for _i, (_k, _v) in enumerate(table._value.body):
            if _k is not None:
                last_item_idx = _i
            elif isinstance(_v, Whitespace) and "," in _v.s:
                has_explicit_commas = True
            if isinstance(_v, Null):
                last_null_idx = _i
        pending_separator = False
        # Buffer position right after the last rendered value, used to place a
        # deferred separator comma after the value rather than after a trailing
        # comment/whitespace.
        last_value_end = len(buf)
        body = table._value.body
        for i, (k, v) in enumerate(body):
            if k is None:
                if isinstance(v, Whitespace) and "," in v.s:
                    if not emitted_key:
                        buf += v.as_string().replace(",", "", 1)
                        continue

                    # Equivalent to scanning body[i + 1 :] for a Null / a real
                    # key, but O(1) using the indices precomputed above.
                    has_following_null = last_null_idx > i
                    has_following_key = last_item_idx is not None and last_item_idx > i
                    if has_following_null and not has_following_key:
                        buf += v.as_string().replace(",", "", 1)
                        continue

                    if pending_separator:
                        # A previous key was removed, leaving this comma as a
                        # duplicate of an already emitted separator. Drop it to
                        # avoid producing an invalid ``, ,`` sequence.
                        buf += v.as_string().replace(",", "", 1)
                        continue

                    pending_separator = True

                if i == len(body) - 1:
                    if table._new:
                        buf = buf.rstrip(", ")
                    elif not has_explicit_commas or "," in v.as_string():
                        buf = buf.rstrip(",")

                v_string = v.as_string()
                buf += v_string
                if "," in v_string:
                    needs_separator = False

                continue

            if has_explicit_commas and needs_separator:
                # Insert the deferred separator right after the previous value,
                # not after any trailing comment/whitespace -- otherwise the
                # comma is swallowed by a trailing comment (see #512).
                buf = f"{buf[:last_value_end]},{buf[last_value_end:]}"
                needs_separator = False

            v_trivia_trail = v.trivia.trail.replace("\n", "")
            if k.is_dotted() and isinstance(v, Table):
                # A table materialized from a dotted key renders one
                # `prefix.child = value` pair per child, so that keys added
                # after parsing stay attached to the dotted prefix.
                rendered = ", ".join(self.render_inline_dotted(k, v))
            else:
                rendered = (
                    f"{k.as_string() + ('.' if k.is_dotted() else '')}"
                    f"{k.sep}"
                    f"{v.as_string()}"
                )
            buf += f"{v.trivia.indent}{rendered}"
            last_value_end = len(buf)
            buf += f"{v.trivia.comment}{v_trivia_trail}"
            emitted_key = True
            pending_separator = False
            if has_explicit_commas:
                needs_separator = True

            if (
                not has_explicit_commas
                and last_item_idx is not None
                and i < last_item_idx
            ):
                buf += ","
                if table._new:
                    buf += " "

        buf += "}"

        return buf

    def render_inline_dotted(self, key: Key, table: Table) -> list[str]:
        """Render a table materialized from a dotted key as a list of
        ``prefix.child = value`` strings, recursing into nested dotted
        children."""
        prefix = f"{key.as_string()}.{key.sep}"
        parts = []
        for k, v in table._value.body:
            if k is None:
                continue
            if isinstance(v, Table):
                parts.extend(f"{prefix}{sub}" for sub in self.render_inline_dotted(k, v))
            else:
                trail = v.trivia.trail.replace("\n", "")
                parts.append(
                    f"{prefix}{v.trivia.indent}{k.as_string()}{k.sep}{v.as_string()}"
                    f"{v.trivia.comment_ws}{v.trivia.comment}{trail}"
                )
        return parts

    def render_array(self, array: Array) -> str:
        if not array._multiline or not array._value:
            return f"[{''.join(v.as_string() for v in array._iter_items())}]"

        s = "[\n"
        s += "".join(
            array.trivia.indent
            + " " * 4
            + v.value.as_string()
            + ("," if not isinstance(v.value, Null) else "")
            + (v.comment.as_string() if v.comment is not None else "")
            + "\n"
            for v in array._value
            if v.value is not None
        )
        s += array.trivia.indent + "]"

        return s


_default_renderer = Renderer()


def render_container(container: Container) -> str:
    return _default_renderer.render_container(container)


def render_inline_table(table: InlineTable) -> str:
    return _default_renderer.render_inline_table(table)


def render_array(array: Array) -> str:
    return _default_renderer.render_array(array)
