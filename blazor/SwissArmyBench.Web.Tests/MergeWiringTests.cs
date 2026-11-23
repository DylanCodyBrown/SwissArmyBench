using System.Text.Json;

using Bunit;

using SwissArmyBench.Web.Api.App;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.Pages.Workbench;
using SwissArmyBench.Web.State;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>What the merge wired: a routed cell's route and its table result, the beta note's place in words, the
/// IDE's panel under the code, and the page plug-ins the extensions register.</summary>
public sealed class MergeWiringTests : AppTestContext
{
    private static readonly Dictionary<string, CellRoute> _routes = new()
    {
        ["typescript"] = new("TypeScript", "typescript", "/made-up/run", Grid: "/made-up/grid"),
        ["sql"] = new("SQL", "sql", "/made-up/run"),
    };

    [Fact]
    public void ACellRunsOnItsRouteOnlyWhereTheModeDeclaresOne()
    {
        Assert.Equal("/made-up/run", RoutedRunner.RouteOf(new CellModel { Kind = "typescript" }, _routes)?.Run);
        Assert.NotNull(RoutedRunner.RouteOf(new CellModel { Kind = "sql" }, _routes));
        // A SQL cell with a connection of its own runs in the Python kernel; a TSX cell needs its own route.
        Assert.Null(RoutedRunner.RouteOf(new CellModel { Kind = "sql", Connection = "Made Up Books" }, _routes));
        Assert.Null(RoutedRunner.RouteOf(new CellModel { Kind = "tsx" }, _routes));
        Assert.Null(RoutedRunner.RouteOf(new CellModel { Kind = "code" }, _routes));
    }

    [Fact]
    public void ATableResultIsReadAsData()
    {
        var output = JsonSerializer.Deserialize<JsonElement>("""
            {"output_type": "execute_result", "data": {"application/vnd.swissarmybench.table+json":
              {"id": "r1", "columns": ["region", "total"], "types": ["VARCHAR", "DOUBLE"],
               "rows": [{"region": "North", "total": 12.5}, {"region": null, "total": 7}], "total": 1200}}}
            """);

        var table = ResultTable.Of(output);

        Assert.NotNull(table);
        Assert.Equal("r1", table.Id);
        Assert.Equal(["region", "total"], table.Columns);
        Assert.Equal("12.5", ResultTable.Cell(table.Rows[0], "total"));
        Assert.Equal(string.Empty, ResultTable.Cell(table.Rows[1], "region"));
        Assert.StartsWith("1,200 rows, 2 columns: the first 2 shown", table.Said, StringComparison.Ordinal);
        Assert.Null(ResultTable.Of(JsonSerializer.Deserialize<JsonElement>("""{"output_type": "stream", "text": "hi"}""")));
    }

    [Fact]
    public void ABetaNotesPlaceIsSaidAsTheClassicSaysIt()
    {
        Assert.Equal("Button: Save", new BetaElement("button", "button", "Save", string.Empty, "div > button").Words);
        Assert.Equal("label: Name", new BetaElement("label", string.Empty, string.Empty, "Name", "label").Words);
        Assert.Equal("Menu: Orders", BetaElement.Named("menu", "Orders").Words);
        Assert.Equal("div", BetaElement.Named(string.Empty, string.Empty).Words);
    }

    [Fact]
    public void TheIdePanelIsFoldedUntilATabIsPressed()
    {
        string? asked = "unset";
        var panel = Render<IdeRunPanel>(p => p
            .Add(x => x.Folded, true)
            .Add(x => x.Problems, [new EditorProblem(3, 1, "made_up is not defined")])
            .Add(x => x.OnTab, (string? tab) => asked = tab));

        Assert.Contains("folded", panel.Find("section").ClassList);
        Assert.Empty(panel.FindAll(".ide-run-body"));
        Assert.Equal("1", panel.Find("[data-tab=problems] .ide-count").TextContent.Trim());
        panel.Find("[data-tab=problems]").Click();
        Assert.Equal("problems", asked);
    }

    [Fact]
    public void TheExtensionsPageActionsAreRegistered()
    {
        var plugins = ExtensionPlugins.RegisterIn(new PagePlugins());

        Assert.True(plugins.Has("powerbi_export"));
        Assert.True(plugins.Has("powerbi_report_pages"));
        Assert.False(plugins.Has("made_up_plugin"));
    }
}
