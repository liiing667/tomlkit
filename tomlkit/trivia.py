"""The format-preservation model ("trivia").

This module is the first of tomlkit's three format-preservation layers:

1. **Structure with format info** (this module + the items built by
   :mod:`tomlkit.parser`): every :class:`~tomlkit.items.Item` carries a
   :class:`Trivia` instance describing the whitespace and comments that
   surrounded it in the source text, and containers additionally hold
   standalone ``Whitespace``/``Comment`` items in their body so that blank
   lines and full-line comments keep their exact position.
2. **Editing** (:class:`tomlkit.container.Container` and the item mutation
   APIs): structural edits reuse the trivia of the items they touch and only
   recompute the small set of fields documented below.
3. **Rendering** (:mod:`tomlkit.renderer`): a structure is rendered back to
   text purely from the items and their trivia, with no parser involvement.

Which format info an edit must recompute
----------------------------------------

- ``Trivia.trail`` of the *previous* sibling: when a new item is appended
  after an item whose trail does not end in a newline, the edit adds ``"\\n"``
  so the new item starts on its own line (see ``Container.append`` /
  ``Container._insert_after`` / ``Container._insert_at``).
- ``Trivia.indent`` of a newly appended ``Table``/``AoT``: a table following
  non-whitespace content gets ``"\\n"`` so its header is preceded by a blank
  line.
- The full ``Trivia`` of a *replaced* item: a replacement value inherits
  ``indent``, ``comment_ws``, ``comment`` and ``trail`` from the item it
  replaces so surrounding comments survive value edits
  (see ``Container._replace_at``).
- ``Key.sep`` and the item's ``comment_ws``/``comment``/``trail`` for
  *newly created* items come from the ``Trivia``/``SingleKey`` defaults
  (``" = "`` separator, ``"\\n"`` trail); nothing is recomputed for them.

Everything else (array element whitespace, string quoting style, key order,
line endings inside ``trail``) is stored verbatim on the items and never
recomputed, which is what keeps ``dumps(parse(text)) == text``.
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class Trivia:
    """
    Trivia information (aka metadata).
    """

    # Whitespace before a value.
    indent: str = ""
    # Whitespace after a value, but before a comment.
    comment_ws: str = ""
    # Comment, starting with # character, or empty string if no comment.
    comment: str = ""
    # Trailing newline.
    trail: str = "\n"

    def copy(self) -> Trivia:
        return dataclasses.replace(self)
