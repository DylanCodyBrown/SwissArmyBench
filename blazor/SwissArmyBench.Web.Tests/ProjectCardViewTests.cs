using Bunit;

using SwissArmyBench.Web.Api.Projects;
using SwissArmyBench.Web.Pages.Home;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>A project's card on the Project Explorer (Pages/Home/ProjectCardView): the stripe of the open one, its type
/// and place as chips, how long ago it was opened, what it holds as icon counts, the end of its folder's path.
/// Made-up projects.</summary>
public sealed class ProjectCardViewTests : AppTestContext
{
    private const string Folder = "/home/made-up/work/s1/projects/larkfield_review";

    private static ProjectCard Card(bool open = false, string where = "local", ProjectCounts? counts = null, bool missing = false) => new(
        Folder, "larkfield_review", DateTimeOffset.Now.AddMinutes(-3).ToUnixTimeSeconds(), open, where, missing, "streamlit", "Streamlit app",
        DateTimeOffset.Now.AddDays(-2).ToUnixTimeSeconds(), null, counts ?? new ProjectCounts(2, 1, 1, 4), []);

    [Fact]
    public void TheCardSaysItsTypePlaceAndWhenItWasOpenedInWords()
    {
        var card = Render<ProjectCardView>(p => p.Add(c => c.Card, Card()));

        Assert.Equal("Streamlit app", card.Find("[data-fact=type]").TextContent);
        Assert.Equal("Local", card.Find("[data-fact=where]").TextContent);
        Assert.Equal("Opened 3 minutes ago", card.Find("[data-fact=opened]").TextContent);
        Assert.Contains("Changed", card.Find("[data-fact=opened]").GetAttribute("title"));
    }

    [Fact]
    public void WhatItHoldsIsIconCountsAndAnEmptyOneSaysSo()
    {
        var card = Render<ProjectCardView>(p => p.Add(c => c.Card, Card()));

        Assert.Equal(["4 tables", "2 notebooks", "1 script", "1 app"], card.FindAll(".explorer-count").Select(c => c.TextContent.Trim()));
        Assert.All(card.FindAll(".explorer-count"), c => Assert.NotNull(c.QuerySelector("svg")));

        var empty = Render<ProjectCardView>(p => p.Add(c => c.Card, Card(counts: new ProjectCounts())));
        Assert.Equal("Empty", empty.Find("[data-fact=counts]").TextContent.Trim());
    }

    [Fact]
    public void TheFoldersPathIsItsEndWithTheWholeOfItOnHover()
    {
        var card = Render<ProjectCardView>(p => p.Add(c => c.Card, Card()));

        Assert.Equal("…/work/s1/projects/larkfield_review", card.Find(".explorer-folder span").TextContent);
        Assert.Equal(Folder, card.Find(".explorer-folder").GetAttribute("title"));
    }

    [Fact]
    public void TheOpenProjectAndASharedOneAreMarkedForTheirStripe()
    {
        var open = Render<ProjectCardView>(p => p.Add(c => c.Card, Card(open: true)));
        Assert.Contains("open", open.Find(".explorer-card").ClassList);
        Assert.DoesNotContain(open.FindAll(".card-actions button"), b => b.TextContent.Trim() == "Open");

        var shared = Render<ProjectCardView>(p => p.Add(c => c.Card, Card(where: "shared")));
        Assert.Contains("shared", shared.Find(".explorer-card").ClassList);
        Assert.Equal("Shared", shared.Find("[data-fact=where]").TextContent);
    }

    [Fact]
    public void OpenAndShowInFolderAreButtonsAndAMissingProjectOffersLocate()
    {
        var card = Render<ProjectCardView>(p => p.Add(c => c.Card, Card()));
        Assert.Equal(["Open", "Show in folder"], card.FindAll(".card-actions button").Select(b => b.TextContent.Trim()));

        var missing = Render<ProjectCardView>(p => p.Add(c => c.Card, Card(missing: true)));
        Assert.Equal(["Locate…"], missing.FindAll(".card-actions button").Select(b => b.TextContent.Trim()));
    }
}
