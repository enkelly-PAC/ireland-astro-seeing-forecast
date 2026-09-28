import unittest
from pathlib import Path

from meteoblue_seeing.html_parser import (
    largest_table,
    parse_tables,
    parse_tables_from_file,
    rows_to_dicts,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "sample_meteoblue_page.html"
)


class TestHtmlTableParser(unittest.TestCase):
    def test_parses_inline_html_snippet(self):
        html = """
        <html><body>
        <table>
          <tr><th>a</th><th>b</th></tr>
          <tr><td>1</td><td>2</td></tr>
        </table>
        </body></html>
        """
        tables = parse_tables(html)
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0], [["a", "b"], ["1", "2"]])

    def test_multiple_tables_are_separated(self):
        html = """
        <table><tr><td>x</td></tr></table>
        <table><tr><td>y</td></tr><tr><td>z</td></tr></table>
        """
        tables = parse_tables(html)
        self.assertEqual(len(tables), 2)
        self.assertEqual(tables[0], [["x"]])
        self.assertEqual(tables[1], [["y"], ["z"]])
        self.assertEqual(largest_table(tables), [["y"], ["z"]])

    def test_fixture_file_extracts_forecast_table(self):
        tables = parse_tables_from_file(str(FIXTURE_PATH))
        self.assertEqual(len(tables), 2)
        table = largest_table(tables)
        self.assertEqual(
            table[0],
            ["hour", "seeing1_arcsec", "seeing2_arcsec", "jet_200hpa_ms", "cloud_low_pct"],
        )
        self.assertEqual(len(table), 5)  # header + 4 data rows

    def test_rows_to_dicts(self):
        table = [["a", "b"], ["1", "2"], ["3", "4"]]
        records = rows_to_dicts(table)
        self.assertEqual(records, [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}])

    def test_empty_html_gives_no_tables(self):
        self.assertEqual(parse_tables("<p>no tables here</p>"), [])

    def test_whitespace_and_charrefs_are_normalised(self):
        html = "<table><tr><td>  spaced &amp;   text  </td></tr></table>"
        tables = parse_tables(html)
        self.assertEqual(tables[0], [["spaced & text"]])


if __name__ == "__main__":
    unittest.main()
