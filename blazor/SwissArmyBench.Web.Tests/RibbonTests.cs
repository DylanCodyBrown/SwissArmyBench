using Bunit;

using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Pages.Grids;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The Grids page's logic: which Column tools apply to the selected columns, and why not.</summary>
public sealed class RibbonTests : AppTestContext
{
    private static readonly GridInfo _orders = new()
    {
        Grid = "g1",
        Dataset = "orders",
        Title = "orders",
        Columns =
        [
            new GridColumn { Name = "amount", Type = "DOUBLE" },
            new GridColumn { Name = "status", Type = "VARCHAR" },
            new GridColumn { Name = "ordered", Type = "DATE" },
        ],
    };

    private IRenderedComponent<Ribbon> Ribbon(params string[] selected) =>
        Render<Ribbon>(p => p
            .Add(x => x.Info, _orders)
            .Add(x => x.Selection, new GridSelection(selected.Length > 0 ? "columns" : "none", null, selected)));

    private static string? Reason(IRenderedComponent<Ribbon> ribbon, string tool)
    {
        var button = ribbon.Find($"[data-tool={tool}]");
        return button.HasAttribute("disabled") ? button.GetAttribute("title") : null;
    }

    [Fact]
    public void NoColumnSelectedSaysSoOnEveryColumnTool()
    {
        var ribbon = Ribbon();

        Assert.Equal("Select a column first.", Reason(ribbon, "col-sort-asc"));
        Assert.Equal("Select a column first.", Reason(ribbon, "col-filter"));
        Assert.Null(Reason(ribbon, "filter"));
    }

    [Fact]
    public void BucketTakesOnlyANumberOrADate()
    {
        Assert.Equal("Number or date columns only.", Reason(Ribbon("status"), "col-bucket"));
        Assert.Null(Reason(Ribbon("amount"), "col-bucket"));
        Assert.Null(Reason(Ribbon("ordered"), "col-bucket"));
    }

    [Fact]
    public void SeveralColumnsSortTogetherButFilterOneAtATime()
    {
        var ribbon = Ribbon("amount", "status", "ordered");

        Assert.Null(Reason(ribbon, "col-sort-desc"));
        Assert.Equal("Select one column.", Reason(ribbon, "col-filter"));
        Assert.Equal("amount, status +1", ribbon.Find(".ribbon-target").TextContent);
    }

    [Fact]
    public void CleanTextNeedsATextColumn()
    {
        Assert.Equal("Select a text column.", Reason(Ribbon("amount"), "col-clean"));
        Assert.Null(Reason(Ribbon("amount", "status"), "col-clean"));
    }

    [Fact]
    public void EveryButtonHasAnAccessibleName()
    {
        Assert.All(Ribbon().FindAll("button"), b => Assert.False(string.IsNullOrWhiteSpace(b.GetAttribute("aria-label"))));
    }
}
