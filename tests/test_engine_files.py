"""Model notes that would break the ERD. Made-up data only."""

from __future__ import annotations

from swissarmygrid.domain.relationships import mermaid_erd, parse_model


def test_a_note_with_line_breaks_stays_on_one_mermaid_line() -> None:
    model = parse_model(
        {
            "tables": {"a": {"primary_key": ["id"]}, "b": {"primary_key": ["id"]}},
            "relationships": [
                {
                    "from": "a",
                    "from_columns": ["b_id"],
                    "to": "b",
                    "to_columns": ["id"],
                    "note": 'x\n"y"\r\nz',
                }
            ],
        }
    )
    lines = mermaid_erd(model, {}).splitlines()
    assert lines[-1] == "    a }o--|| b : \"x 'y' z\""
