using System.Text.Json;

using Bunit;

using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Api.Relationships;
using SwissArmyBench.Web.Pages.Grids.Cards;
using SwissArmyBench.Web.Pages.Grids.Compare;
using SwissArmyBench.Web.Pages.Grids.Tabs;
using SwissArmyBench.Web.Pages.Grids.Values;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The Grids page's pure rules: the tab row's order and groups, the known joins a compare starts from, the
/// value viewer's reading of a value, the Analyze cards, and the Compare row's tools.</summary>
public sealed class GridRulesTests : AppTestContext
{
    private static GridListItem Tab(string grid, string dataset, string? connection = null, string kind = "unknown") =>
        new(grid, dataset, 0, new GridOrigin(kind, connection));

    [Fact]
    public void TheRememberedOrderComesFirstThenNewTabs()
    {
        IReadOnlyList<GridListItem> open = [Tab("a", "orders"), Tab("b", "customers"), Tab("c", "products")];
        Assert.Equal(["c", "a", "b"], TabOrder.Normalize(open, ["c", "gone", "a"]));
    }

    [Fact]
    public void AConnectionsTablesStayTogetherUnderItsHead()
    {
        IReadOnlyList<GridListItem> open = [Tab("a", "orders", "Shop"), Tab("b", "notes", kind: "file"), Tab("c", "lines", "Shop")];
        var order = TabOrder.Normalize(open, ["a", "b", "c"]);
        Assert.Equal(["a", "c", "b"], order);
        var groups = TabOrder.Groups(open, order);
        Assert.Equal(["Shop", "Files"], groups.Select(g => g.Name));
        Assert.Equal(["b", "a", "c"], TabOrder.MoveGroup(order, open, "k:file", "a"));
    }

    [Fact]
    public void ASecondGridOnOneTableIsNumbered()
    {
        IReadOnlyList<GridListItem> open = [Tab("a", "orders"), Tab("b", "orders")];
        Assert.Equal("orders · 2", TabOrder.Label(open[1], open, ["a", "b"]));
        Assert.Equal(["b", "a"], TabOrder.Move(["a", "b"], "b", "a"));
    }

    [Fact]
    public void AKnownJoinIsReadFromEitherSideActiveFirst()
    {
        var model = new Model(
        [
            new Join("orders", ["ship_date"], "calendar", ["day"], Active: false),
            new Join("calendar", ["day"], "orders", ["order_date"]),
        ]);
        Assert.Equal([("order_date", "day")], KnownJoins.Pairs(model, "orders", "calendar"));
        Assert.True(KnownJoins.IsKnown(model, "orders", "calendar", "ship_date", "day"));
        var self = new Model([], Tables: new Dictionary<string, ModelTable> { ["orders"] = new(["order_id"]) });
        Assert.Equal([("order_id", "order_id")], KnownJoins.Pairs(self, "orders", "orders"));
    }

    [Theory]
    [InlineData("null", ValueShape.Blank)]
    [InlineData("{\"a\": 1}", ValueShape.Object)]
    [InlineData("[{\"a\": 1}, {\"a\": 2}]", ValueShape.Table)]
    [InlineData("[1, 2]", ValueShape.Array)]
    [InlineData("\"# Title\\n\\ntext\"", ValueShape.Markdown)]
    [InlineData("\"North\"", ValueShape.Short)]
    [InlineData("42", ValueShape.Number)]
    public void AValueIsReadAsWhatItIs(string json, ValueShape shape)
    {
        using var document = JsonDocument.Parse(json);
        Assert.Equal(shape, ValueRules.Detect(ValueRules.Parsed(document.RootElement)));
    }

    [Fact]
    public void TextHoldingJsonOpensAsJson()
    {
        using var document = JsonDocument.Parse("\"{\\\"region\\\": \\\"North\\\", \\\"n\\\": 3}\"");
        var parsed = ValueRules.Parsed(document.RootElement);
        Assert.Equal(ValueShape.Object, ValueRules.Detect(parsed));
        Assert.Equal("JSON object · 2 keys", ValueRules.Describe(parsed, ValueShape.Object));
    }

    [Fact]
    public void ARowCardShowsAnIdAsItsDigits()
    {
        using var document = JsonDocument.Parse("[1234, \"Ada\"]");
        var values = new List<(string, JsonElement)> { ("order_id", document.RootElement[0]), ("name", document.RootElement[1]) };
        var card = Assert.Single(GridCards.Row(values, 0, "orders"));
        Assert.Contains("| order_id | 1234 |", card.Body, StringComparison.Ordinal);
        Assert.Equal("Row 1 of orders", card.Title);
    }

    [Fact]
    public void TheCompareRowSaysWhatLinesUp()
    {
        var row = Render<CompareRow>(p => p.Add(x => x.LeftName, "orders").Add(x => x.RightName, "customers"));
        Assert.Contains("orders and customers side by side", row.Markup, StringComparison.Ordinal);
        Assert.Equal("Pick keys first.", row.Find("[data-tool=cmp-outer]").GetAttribute("title"));
        var running = new GridCompare { Compare = "c1", Keys = [["customer_id", "customer_id"]], Mode = "anti", Counts = new CompareCounts { Matched = 5, LeftOnly = 2 } };
        row.Render(p => p.Add(x => x.Info, running));
        Assert.Contains("5 matched · 2 only in orders · 0 only in customers", row.Markup, StringComparison.Ordinal);
        Assert.Equal("true", row.Find("[data-tool=cmp-anti]").GetAttribute("aria-pressed"));
        Assert.Contains("Only in customers", row.Find("[data-tool=cmp-side-right]").TextContent, StringComparison.Ordinal);
    }
}
