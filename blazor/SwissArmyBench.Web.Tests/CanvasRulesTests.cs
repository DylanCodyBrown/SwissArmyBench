using System.Text.Json;

using SwissArmyBench.Web.Api.Canvas;
using SwissArmyBench.Web.Pages.Canvas;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The Canvas's pure rules, as the classic canvasGrid.ts, canvasSnap.ts and canvasWiring.ts have them: the
/// snap to the step, the grid and the other items' edges; the nudge; the dots; the wiring's words and marks.</summary>
public sealed class CanvasRulesTests
{
    private static readonly GridSpec _page = new(12, 60, 8, 1200);

    private static SnapSettings Snap(SnapStep step, bool sizing = false, params BoardRect[] others) =>
        new(true, step, _page, others, 4, sizing);

    [Fact]
    public void A_move_lands_on_the_step()
    {
        var done = CanvasGrid.Snap(new BoardRect("a", 13, 22, 100, 50), Snap(new SnapStep(8, false)));
        Assert.Equal((16, 24), (done.Rect.Left, done.Rect.Top));
    }

    [Fact]
    public void A_size_keeps_its_corner_and_reaches_the_step()
    {
        var done = CanvasGrid.Snap(new BoardRect("a", 13, 22, 101, 49), Snap(new SnapStep(8, false), sizing: true));
        Assert.Equal((13, 22, 99, 50), (done.Rect.Left, done.Rect.Top, done.Rect.Width, done.Rect.Height));
    }

    [Fact]
    public void Snap_off_keeps_whole_pixels()
    {
        var done = CanvasGrid.Snap(new BoardRect("a", 10.4, 10.6, 0.2, 30.5), Snap(SnapStep.One) with { On = false });
        Assert.Equal((10, 11, 1, 31), (done.Rect.Left, done.Rect.Top, done.Rect.Width, done.Rect.Height));
        Assert.Empty(done.Guides);
    }

    [Fact]
    public void The_grid_step_puts_a_move_on_a_column_and_a_row()
    {
        var done = CanvasGrid.Snap(new BoardRect("a", 110, 75, 100, 50), Snap(new SnapStep(0, true)));
        Assert.Equal(101, done.Rect.Left);
        Assert.Equal(68, done.Rect.Top);
    }

    [Fact]
    public void Another_items_edge_wins_within_the_tolerance_and_is_guided()
    {
        var other = new BoardRect("b", 200, 300, 100, 40);
        var done = CanvasGrid.Snap(new BoardRect("a", 203, 10, 50, 20), Snap(SnapStep.One, false, other));
        Assert.Equal(200, done.Rect.Left);
        var guide = Assert.Single(done.Guides, g => g.Axis == "v");
        Assert.Equal(("left", 10.0, 340.0), (guide.Edge, guide.From, guide.To));
    }

    [Fact]
    public void Arrows_nudge_by_the_step_ten_steps_or_one_pixel()
    {
        Assert.Equal(4, CanvasGrid.NudgeBy(new SnapStep(4, false), shift: false, alt: false, _page));
        Assert.Equal(40, CanvasGrid.NudgeBy(new SnapStep(4, false), shift: true, alt: false, _page));
        Assert.Equal(1, CanvasGrid.NudgeBy(new SnapStep(4, false), shift: true, alt: true, _page));
        Assert.Equal(101, CanvasGrid.NudgeBy(new SnapStep(0, true), shift: false, alt: false, _page));
    }

    [Fact]
    public void The_dots_stay_twelve_screen_pixels_apart()
    {
        Assert.Equal(16, CanvasGrid.DotSpacing(SnapStep.One, 1));
        Assert.Equal(8, CanvasGrid.DotSpacing(new SnapStep(0, true), 2));
    }

    [Fact]
    public void A_snap_step_reads_the_servers_words()
    {
        Assert.Equal("grid", SnapStep.From(JsonSerializer.SerializeToElement("grid")).Value);
        Assert.Equal("4", SnapStep.From(JsonSerializer.SerializeToElement(4)).Value);
    }

    [Fact]
    public void Types_fit_as_the_widget_contract_says()
    {
        Assert.True(WiringRules.Fits("int", "float"));
        Assert.True(WiringRules.Fits("list[dict]", "Table"));
        Assert.True(WiringRules.Fits("list[int]", "list[float]"));
        Assert.False(WiringRules.Fits("str", "int"));
    }

    [Fact]
    public void A_wire_is_its_pickers_key_and_back()
    {
        Assert.Equal("table:orders", WiringRules.KeyOf(JsonSerializer.SerializeToElement(new { table = "orders" })));
        Assert.Equal("value", WiringRules.KeyOf(JsonSerializer.SerializeToElement(new { value = 3 })));
        Assert.Equal(string.Empty, WiringRules.KeyOf(null));
        Assert.Equal("w1.region", WiringRules.WireOf("out:w1.region")!["out"]);
        Assert.Null(WiringRules.WireOf(string.Empty));
    }

    [Fact]
    public void Broken_wires_are_said_before_play_and_marked_on_both_ends()
    {
        var wiring = new CanvasWiring
        {
            Wires = [new WireLine { From = "w1.region", To = "w2.region" }],
            Broken = [new BrokenWire { Instance = "w3", Port = "rows", Reason = "w9 is gone.", Source = "w9.rows" }],
        };
        Assert.Equal("A wire is broken: w3.rows: w9 is gone.", WiringRules.BrokenWords(wiring));
        Assert.Equal(" wire-source", WiringRules.NodeMarks("w1", ["w2"], wiring));
        Assert.Equal(" wire-reader", WiringRules.NodeMarks("w2", ["w1"], wiring));
        Assert.Equal(" wire-broken", WiringRules.NodeMarks("w9", [], wiring));
    }

    [Fact]
    public void Actions_group_by_their_api_the_local_one_first()
    {
        var groups = ApiActions.Groups(["[Orders] GET /orders", "GET /local", "POST /local"]);
        Assert.Equal([ApiActions.LocalApi, "Orders"], groups.Select(g => g.Key));
        Assert.Equal(("Orders", "GET /orders"), ApiActions.Parts("[Orders] GET /orders"));
        Assert.True(ApiActions.ReadsOnly("[Orders] GET /orders"));
        Assert.False(ApiActions.ReadsOnly("POST /local"));
    }
}
