using Bunit;

using SwissArmyBench.Web.Api.Projects;
using SwissArmyBench.Web.Api.SessionLog;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Pages.Home;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>Home's summary of the open project (Pages/Home/SummarySections) from canned answers: the head (its name,
/// type, Local or Shared, folder, saved or not, its Python) and each section with its count and links. Made-up
/// project, tables and connection.</summary>
public sealed class ProjectSummaryTests : AppTestContext
{
    private static ProjectSummary Canned(bool dirty = false) => new(new SummaryProject(
        "Captive_Unassigned", "/home/made-up/Captive_Unassigned", "bi", "Analysis", "shared", dirty, Autosave: true))
    {
        Python = new ProjectPythonState("ready", "The project's Python is ready", "/made-up/.venv/bin/python", true, null, null, null),
        Tables = [new SummaryTable("orders", "orders.csv", "file", 1200, 4), new SummaryTable("regions", Kind: "paste")],
        Documents =
        [
            new SummaryDocument("data.ipynb", "data.ipynb", "/home/made-up/Captive_Unassigned/data.ipynb", "notebook", "notebooks"),
            new SummaryDocument("load.py", "load.py", "/home/made-up/Captive_Unassigned/load.py", "script", "scripts"),
            new SummaryDocument("API.py", "API.py", "/home/made-up/Captive_Unassigned/API.py", "script", "scripts", Api: true),
        ],
        Connections = [new SummaryConnection("Warehouse", "SQLite", "Ready", "#2f6fd6")],
        Recent = [new SessionEntry(1, "2026-11-24T09:30:00+00:00", "user", "open", "Opened orders", "grids", new SessionTarget("grids", Dataset: "orders"))],
    };

    [Fact]
    public void TheHeadSaysWhichProjectIsOpenUnmistakably()
    {
        var summary = Render<SummarySections>(p => p.Add(s => s.Summary, Canned()));

        Assert.Equal("Captive_Unassigned", summary.Find(".summary-name span").TextContent);
        Assert.Equal("Analysis", summary.Find("[data-fact=type]").TextContent);
        Assert.Equal("Shared", summary.Find("[data-fact=where]").TextContent);
        // The folder's path is shortened to its end; the whole of it is the hover's (and Copy path's).
        Assert.Equal("…/made-up/Captive_Unassigned", summary.Find("[data-fact=folder] code").TextContent);
        Assert.Equal("/home/made-up/Captive_Unassigned", summary.Find("[data-fact=folder] code").GetAttribute("title"));
        Assert.Contains("Saved", summary.Find("[data-fact=saved]").TextContent);
        Assert.Contains("The project's Python is ready", summary.Find("[data-fact=python]").TextContent);
        Assert.DoesNotContain(summary.FindAll("button"), b => b.TextContent.Trim() == "Save");
    }

    [Fact]
    public void UnsavedWorkShowsTheDotAndSaveAndTheInstallsWordsWinOverThePython()
    {
        var summary = Render<SummarySections>(p => p
            .Add(s => s.Summary, Canned(dirty: true))
            .Add(s => s.Installing, "Setting up Captive_Unassigned: installing 1 of 2"));

        Assert.Contains("Unsaved changes", summary.Find("[data-fact=saved]").TextContent);
        Assert.Contains(summary.FindAll("button"), b => b.TextContent.Trim() == "Save");
        Assert.Contains("installing 1 of 2", summary.Find("[data-fact=python]").TextContent);
    }

    [Fact]
    public void EachSectionCountsItsItemsAndLinksEachToWhereItLives()
    {
        var summary = Render<SummarySections>(p => p.Add(s => s.Summary, Canned()));

        var tables = summary.Find("[data-section=tables]");
        Assert.Equal("2", tables.QuerySelector(".summary-count")!.TextContent);
        Assert.Equal("tables?table=orders", tables.QuerySelector("a.summary-link")!.GetAttribute("href"));
        Assert.Contains("1,200 rows · from orders.csv", tables.TextContent);

        var documents = summary.Find("[data-section=documents]").QuerySelectorAll("a.summary-link");
        Assert.Equal("notebooks?path=%2Fhome%2Fmade-up%2FCaptive_Unassigned%2Fdata.ipynb", documents[0].GetAttribute("href"));
        Assert.StartsWith("scripts?path=", documents[1].GetAttribute("href"));
        Assert.Contains("The local sandbox API", summary.Find("[data-section=documents]").TextContent);

        var connection = summary.Find("[data-section=connections] a.summary-link");
        Assert.Equal("connections?name=Warehouse", connection.GetAttribute("href"));
        Assert.Contains("SQLite · Ready", summary.Find("[data-section=connections]").TextContent);

        var recent = summary.Find("[data-section=recent]");
        Assert.Equal("tables?table=orders", recent.QuerySelector("a.summary-link")!.GetAttribute("href"));
        Assert.Equal("session", recent.QuerySelector(".section-head a")!.GetAttribute("href"));
        Assert.Empty(summary.FindAll("[data-section=deliverable]"));
    }

    [Fact]
    public void ATypeWithADeliverableSaysItAndItsFiles()
    {
        var canned = Canned() with { Deliverable = new SummaryDeliverable("accounting", "An Excel workbook", [new DeliverableFile("workbook.py", "The workbook's code")]) };
        var summary = Render<SummarySections>(p => p.Add(s => s.Summary, canned));

        var deliverable = summary.Find("[data-section=deliverable]");
        Assert.Contains("An Excel workbook", deliverable.TextContent);
        Assert.Contains("workbook.py", deliverable.TextContent);
        Assert.Contains("(not made yet)", deliverable.TextContent);
    }
}
