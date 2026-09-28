"""Local HTML parser utility.

Extracts table rows from a locally saved HTML page (for example a page the
user saved from their own browser session, in line with the site's terms)
using only ``html.parser`` from the standard library. This module makes no
network requests and does not scrape live sites; it is intended purely to
help a user turn a page they have already saved into structured rows for
the ``calibrate`` command, for permitted black box calibration datasets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser


@dataclass
class _TableParserState:
    tables: list[list[list[str]]] = field(default_factory=list)
    in_table_depth: int = 0
    current_table: list[list[str]] | None = None
    current_row: list[str] | None = None
    current_cell_chunks: list[str] | None = None
    in_cell: bool = False


class TableExtractingParser(HTMLParser):
    """Extracts every ``<table>...<tr>...<td>/<th>`` structure in a page.

    Nested tables are flattened: a nested ``<table>`` simply contributes
    its own rows to the overall result list, since meteoblue style pages
    typically use a single flat data table for hourly/level values.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._state = _TableParserState()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._state.in_table_depth += 1
            if self._state.current_table is None:
                self._state.current_table = []
        elif tag == "tr" and self._state.current_table is not None:
            self._state.current_row = []
        elif tag in ("td", "th") and self._state.current_row is not None:
            self._state.in_cell = True
            self._state.current_cell_chunks = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._state.in_cell:
            text = "".join(self._state.current_cell_chunks or []).strip()
            text = " ".join(text.split())
            if self._state.current_row is not None:
                self._state.current_row.append(text)
            self._state.in_cell = False
            self._state.current_cell_chunks = None
        elif tag == "tr" and self._state.current_row is not None:
            if self._state.current_table is not None and self._state.current_row:
                self._state.current_table.append(self._state.current_row)
            self._state.current_row = None
        elif tag == "table" and self._state.in_table_depth > 0:
            self._state.in_table_depth -= 1
            if self._state.in_table_depth == 0 and self._state.current_table is not None:
                if self._state.current_table:
                    self._state.tables.append(self._state.current_table)
                self._state.current_table = None

    def handle_data(self, data: str) -> None:
        if self._state.in_cell and self._state.current_cell_chunks is not None:
            self._state.current_cell_chunks.append(data)

    @property
    def tables(self) -> list[list[list[str]]]:
        return self._state.tables


def parse_tables(html_text: str) -> list[list[list[str]]]:
    """Parse ``html_text`` and return a list of tables, each a list of rows,
    each row a list of cell text strings, using only ``html.parser``.
    """

    parser = TableExtractingParser()
    parser.feed(html_text)
    parser.close()
    return parser.tables


def parse_tables_from_file(path: str) -> list[list[list[str]]]:
    """Read a locally saved HTML file and extract its tables.

    This never performs a network request; the caller is responsible for
    having saved the page themselves in compliance with the source
    website's terms of use and data licence.
    """

    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return parse_tables(handle.read())


def largest_table(tables: list[list[list[str]]]) -> list[list[str]] | None:
    """Convenience helper: return the table with the most rows, a common
    heuristic for locating the main data table on a saved forecast page.
    """

    if not tables:
        return None
    return max(tables, key=len)


def rows_to_dicts(table: list[list[str]]) -> list[dict[str, str]]:
    """Treat the first row of ``table`` as a header and return the
    remaining rows as a list of dictionaries keyed by header cell text.
    Rows shorter than the header are padded with empty strings; rows
    longer than the header are truncated to the header length.
    """

    if not table:
        return []
    header = table[0]
    records: list[dict[str, str]] = []
    for row in table[1:]:
        padded = list(row) + [""] * (len(header) - len(row))
        records.append({header[i]: padded[i] for i in range(len(header))})
    return records
