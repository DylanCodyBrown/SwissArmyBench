"""The designer's snapline maths (web/src/canvasSnap.ts: pure functions over rectangles), run as the page
runs them: the module bundled by the page's own esbuild and called by Node with made-up rectangles. Skipped
where Node or the page's packages are not there."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

WEB = Path(__file__).resolve().parents[1] / "web"
ESBUILD = WEB / "node_modules" / ".bin" / "esbuild"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not ESBUILD.exists(), reason="Node and the page's packages are needed"
)

CALLS = """
import * as snap from "./snap.mjs";
const asked = JSON.parse(process.argv[2]);
console.log(JSON.stringify(asked.map(([name, ...args]) => snap[name](...args))));
"""


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> Any:
    folder = tmp_path_factory.mktemp("snap")
    built = subprocess.run(  # noqa: S603
        [
            str(ESBUILD),
            str(WEB / "src" / "canvasSnap.ts"),
            "--format=esm",
            f"--outfile={folder / 'snap.mjs'}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    (folder / "calls.mjs").write_text(CALLS, encoding="utf-8")

    def call(*asked: list[Any]) -> list[Any]:
        done = subprocess.run(  # noqa: S603
            ["node", str(folder / "calls.mjs"), json.dumps(asked)],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0, done.stderr
        return list(json.loads(done.stdout))

    return call


def rect(name: str, left: float, top: float, width: float, height: float) -> dict[str, Any]:
    return {"id": name, "left": left, "top": top, "width": width, "height": height}


A = rect("a", 100, 0, 200, 80)
B = rect("b", 100, 200, 300, 80)  # its left edge under a's
C = rect("c", 500, 0, 100, 80)  # beside a, the same row
D = rect("d", 150, 400, 100, 40)  # its centre under a's (x = 200)


def test_guides_join_matching_edges_and_centres(run: Any) -> None:
    (found,) = run(["guides", A, [A, B, C, D]])
    by_edge = {g["edge"]: g for g in found}
    # Its left edge lines up with b's: one vertical line from a's top to b's bottom.
    assert by_edge["left"] == {"axis": "v", "at": 100, "from": 0, "to": 280, "edge": "left", "with": ["b"]}
    # Its centre with d's centre; its top, middle and bottom with c's (the same row).
    assert (by_edge["centre"]["at"], by_edge["centre"]["with"], by_edge["centre"]["to"]) == (200, ["d"], 440)
    assert by_edge["top"] == {"axis": "h", "at": 0, "from": 100, "to": 600, "edge": "top", "with": ["c"]}
    assert by_edge["bottom"]["at"] == 80 and by_edge["middle"]["with"] == ["c"]
    assert "right" not in by_edge  # nothing ends at x = 300... but b does not either (it ends at 400)
    # An edge never matches a centre: a block whose left edge is at another's centre draws no guide.
    (none,) = run(["guides", rect("m", 200, 600, 50, 50), [A]])
    assert [g for g in none if g["axis"] == "v"] == []
    # Within the tolerance counts; past it does not. Itself is never matched.
    (near, far, alone) = run(
        ["guides", rect("m", 101, 600, 50, 50), [A], 1],
        ["guides", rect("m", 103, 600, 50, 50), [A], 1],
        ["guides", A, [A]],
    )
    assert [g["edge"] for g in near] == ["left"] and far == [] and alone == []


def test_a_dragged_block_snaps_to_the_nearest_line_within_reach(run: Any) -> None:
    moving = rect("m", 104, 203, 120, 60)
    (near, out_of_reach, both) = run(
        ["snapped", moving, [A, B], 6],
        ["snapped", rect("m", 120, 120, 50, 20), [A, B], 6],
        ["snapped", rect("m", 296, 76, 100, 40), [A], 6],
    )
    assert (near["left"], near["top"]) == (100, 200)  # onto b's left edge and top
    assert (out_of_reach["left"], out_of_reach["top"]) == (120, 120)
    assert (both["left"], both["top"]) == (300, 80)  # its left edge onto a's right, its top onto a's bottom


def test_equal_gaps_same_size_and_the_rubber_band(run: Any) -> None:
    row = [
        rect("a", 0, 0, 100, 50),
        rect("b", 140, 0, 100, 50),
        rect("c", 280, 0, 60, 50),
        rect("d", 400, 0, 50, 50),
    ]
    (gaps, none, sizes, band, miss) = run(
        ["equalGaps", row],
        ["equalGaps", row[:2]],
        ["sameSize", row[0], row],
        ["inBand", {"x1": 260, "y1": 60, "x2": 90, "y2": -5}, row],
        ["inBand", {"x1": 341, "y1": 0, "x2": 399, "y2": 50}, row],
    )
    # a-b and b-c are 40 apart (marked); c-d is 60 (not).
    assert gaps == [{"from": 100, "to": 140, "y": 25}, {"from": 240, "to": 280, "y": 25}]
    assert none == []
    assert sizes == {"width": ["b"], "height": ["b", "c", "d"]}
    assert band == ["a", "b"] and miss == []  # dragged up and to the left: the same band
