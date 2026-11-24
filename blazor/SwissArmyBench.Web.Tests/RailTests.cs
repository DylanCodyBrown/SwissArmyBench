using Bunit;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Layout;
using SwissArmyBench.Web.State;

using Xunit;

namespace SwissArmyBench.Web.Tests;

public sealed class RailTests : AppTestContext
{
    [Fact]
    public void TheAreasAreInTheClassicOrderAndTheCurrentOneIsMarked()
    {
        Get<NavigationManager>().NavigateTo("tables");
        var rail = Render<Rail>();

        var areas = rail.FindAll(".nav-rail-item").Select(a => a.GetAttribute("data-area")).ToList();
        Assert.Equal(["projects", "connections", "apis", "environment", "data", "grids", "erd"], areas.Take(7));
        Assert.Equal("page", rail.Find(".nav-rail-item[data-area=grids]").GetAttribute("aria-current"));
        Assert.Equal("Tables", rail.Find(".nav-rail-item[data-area=grids]").GetAttribute("aria-label"));
        // Canvas and Widgets only while a mode offers them.
        Assert.DoesNotContain("canvas", areas);
        Assert.All(rail.FindAll(".nav-rail-item"), a => Assert.False(string.IsNullOrEmpty(a.GetAttribute("aria-label"))));
    }

    [Fact]
    public void TheOldGridsAddressStillMarksTheTablesArea()
    {
        Get<NavigationManager>().NavigateTo("grids?grid=g1");
        var rail = Render<Rail>();

        Assert.Equal("page", rail.Find(".nav-rail-item[data-area=grids]").GetAttribute("aria-current"));
    }

    [Fact]
    public async Task TheRailLetsGoOfItsEventsWhenItClosesAsync()
    {
        var state = Get<RailState>();
        var rail = Render<Rail>();
        Assert.Equal(1, Subscribers(state, nameof(RailState.Changed)));

        await DisposeComponentsAsync();

        Assert.Equal(0, Subscribers(state, nameof(RailState.Changed)));
        Assert.NotNull(rail);
    }
}
