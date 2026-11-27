using Bunit;

using SwissArmyBench.Web.Api.Projects;
using SwissArmyBench.Web.Pages.Home;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>Home's four figure tiles (Pages/Home/SummaryFigures): the tables with their rows in memory, the
/// notebooks, the scripts and the connections with their status, each a link to where they live. Made-up project.</summary>
public sealed class SummaryFiguresTests : AppTestContext
{
    private static ProjectSummary Canned() => new(new SummaryProject("Shop", "/home/made-up/Shop", "bi", "Analysis", "local", false, Autosave: true))
    {
        Tables = [new SummaryTable("orders", "orders.csv", "file", 100_000, 4), new SummaryTable("customers", Kind: "paste", Rows: 152), new SummaryTable("regions")],
        Documents =
        [
            new SummaryDocument("data.ipynb", "data.ipynb", "/home/made-up/Shop/data.ipynb", "notebook", "notebooks"),
            new SummaryDocument("analysis.ipynb", "analysis.ipynb", "/home/made-up/Shop/analysis.ipynb", "notebook", "notebooks"),
            new SummaryDocument("checks.ipynb", "checks.ipynb", "/home/made-up/Shop/checks.ipynb", "notebook", "notebooks"),
            new SummaryDocument("API.py", "API.py", "/home/made-up/Shop/API.py", "script", "scripts", Api: true),
            new SummaryDocument("Shop.canvas.json", "Shop.canvas.json", "/home/made-up/Shop/Shop.canvas.json", "app", "canvas"),
        ],
        Connections = [new SummaryConnection("Warehouse", "DuckDB file", "Works", "#0e7c7b")],
    };

    private static string Words(AngleSharp.Dom.IElement tile) => string.Join(" ", tile.TextContent.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries));

    [Fact]
    public void EachTileSaysItsNumberAndWhatStandsBehindIt()
    {
        var figures = Render<SummaryFigures>(p => p.Add(f => f.Summary, Canned()));

        Assert.Equal(["tables", "notebooks", "scripts", "connections"], figures.FindAll(".summary-figure").Select(t => t.GetAttribute("data-figure")));
        Assert.Equal("3 tables 100,152 rows in memory", Words(figures.Find("[data-figure=tables]")));
        Assert.Equal("3 notebooks data.ipynb · analysis.ipynb · 1 more", Words(figures.Find("[data-figure=notebooks]")));
        Assert.Equal("1 script API.py", Words(figures.Find("[data-figure=scripts]")));
        Assert.Equal("1 connection Warehouse · works", Words(figures.Find("[data-figure=connections]")));
    }

    [Fact]
    public void EachTileIsALinkToWhereTheyLiveWithAWholeName()
    {
        var figures = Render<SummaryFigures>(p => p.Add(f => f.Summary, Canned()));

        Assert.Equal(["tables", "notebooks", "scripts", "connections"], figures.FindAll("a.summary-figure").Select(t => t.GetAttribute("href")));
        Assert.Equal("3 tables: 100,152 rows in memory", figures.Find("[data-figure=tables]").GetAttribute("aria-label"));
    }

    [Fact]
    public void AnEmptyProjectSaysNoneRatherThanNothing()
    {
        var empty = new ProjectSummary(new SummaryProject("Shop", "/home/made-up/Shop", "bi", "Analysis", "local", false, Autosave: true));

        var figures = Render<SummaryFigures>(p => p.Add(f => f.Summary, empty));

        Assert.Equal("0 tables None open yet", Words(figures.Find("[data-figure=tables]")));
        Assert.Equal("0 notebooks None yet", Words(figures.Find("[data-figure=notebooks]")));
        Assert.Equal("0 connections None used yet", Words(figures.Find("[data-figure=connections]")));
    }

    [Fact]
    public void TheSummaryDrawsTheTilesAboveItsSections()
    {
        var summary = Render<SummarySections>(p => p.Add(s => s.Summary, Canned()));

        Assert.Equal("summary-figures", summary.Find(".summary-sections").FirstElementChild!.ClassName);
    }
}
