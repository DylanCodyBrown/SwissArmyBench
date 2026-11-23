using Bunit;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Components;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The dock (Components/PaneDock): its layout's rules (hide, show, move, stack, share, widths, a kept layout
/// fitted to the page's panes) and the component (each side's panes, Hide, the menu's Move to, the toggles' state,
/// remembered, its listener gone with it).</summary>
public sealed class PaneDockTests : AppTestContext
{
    private static readonly DockLayout _defaults = new([new("library", DockSide.Left), new("properties", DockSide.Right)]);

    [Fact]
    public void APaneMovedToTheOtherSideStacksBelowTheOnesThere()
    {
        var moved = _defaults.MoveTo("library", DockSide.Right);

        Assert.Empty(moved.On(DockSide.Left));
        Assert.Equal(["properties", "library"], moved.On(DockSide.Right).Select(s => s.Id));
        Assert.Equal(DockSide.Right, moved.SideOf("library"));
        Assert.Same(_defaults, _defaults.MoveTo("nothing", DockSide.Left));
    }

    [Fact]
    public void HiddenPanesLeaveTheirSideAndComeBackWhereTheyWere()
    {
        var hidden = _defaults.Hide("properties");

        Assert.False(hidden.IsShown("properties"));
        Assert.Empty(hidden.On(DockSide.Right));
        Assert.True(hidden.Toggle("properties").IsShown("properties"));
        Assert.Equal(DockSide.Right, hidden.Show("properties").SideOf("properties"));
    }

    [Fact]
    public void TwoStackedPanesShareTheHeightWithinBounds()
    {
        var stacked = _defaults.MoveTo("properties", DockSide.Left);

        var split = stacked.Split(DockSide.Left, 0, 0.7);
        Assert.Equal(0.7, split.Share(DockSide.Left, 0), 3);
        Assert.Equal(DockLayout.SmallestShare, stacked.Split(DockSide.Left, 0, 0).Share(DockSide.Left, 0), 3);
        Assert.Equal(1 - DockLayout.SmallestShare, stacked.Split(DockSide.Left, 0, 2).Share(DockSide.Left, 0), 3);
        Assert.Same(_defaults, _defaults.Split(DockSide.Left, 0, 0.5));
    }

    [Fact]
    public void WidthsStayInRange()
    {
        Assert.Equal(DockLayout.Narrowest, _defaults.WithWidth(DockSide.Left, 10).LeftWidth);
        Assert.Equal(DockLayout.Widest, _defaults.WithWidth(DockSide.Right, 9000).RightWidth);
        Assert.Equal(333, _defaults.WithWidth(DockSide.Right, 333).RightWidth);
    }

    [Fact]
    public void AKeptLayoutIsFittedToThePanesThePageHasNow()
    {
        var kept = new DockLayout([new("gone", DockSide.Left), new("properties", DockSide.Left, Shown: false, Weight: -1)], LeftWidth: 50);

        var fitted = DockLayout.Recalled(kept, _defaults);

        Assert.Equal(["properties", "library"], fitted.Spots.Select(s => s.Id));
        Assert.False(fitted.IsShown("properties"));
        Assert.Equal(1, fitted.Spots[0].Weight);
        Assert.Equal(DockLayout.Narrowest, fitted.LeftWidth);
        Assert.Same(_defaults, DockLayout.Recalled(null, _defaults));
    }

    [Fact]
    public async Task TheDockDrawsEachSideAndItsHeaderHidesAndMovesAPaneAsync()
    {
        var state = new PaneDockState(Js, "test.dock", _defaults);
        var dock = Render<PaneDock>(p => p
            .Add(x => x.State, state)
            .Add(x => x.Panes, Panes())
            .AddChildContent("<div class=\"middle\">The work</div>"));

        Assert.Equal("left", dock.Find("[data-dock-pane=library]").GetAttribute("data-side"));
        Assert.Equal("right", dock.Find("[data-dock-pane=properties]").GetAttribute("data-side"));
        Assert.Equal("The work", dock.Find(".dock-center .middle").TextContent);
        Assert.Equal(2, dock.FindAll(".dock-grip").Count);

        dock.Find("button[aria-label='Hide Properties']").Click();
        Assert.Empty(dock.FindAll("[data-dock-pane=properties]"));
        Assert.False(state.IsShown("properties"));
        Assert.Contains(JSInterop.Invocations, i => i.Identifier == "sab.remember" && (string?)i.Arguments[0] == "test.dock");

        await dock.InvokeAsync(() => state.ShowAsync("properties"));
        dock.Find("button[aria-label='Properties pane: move or hide']").Click();
        dock.FindAll(".menu-item").Single(b => b.TextContent.Contains("Move to left")).Click();

        var left = dock.FindAll(".dock-left .dock-pane").Select(p => p.GetAttribute("data-dock-pane"));
        Assert.Equal(["library", "properties"], left);
        Assert.Single(dock.FindAll(".dock-left .dock-split"));
        Assert.Empty(dock.FindAll(".dock-right"));
    }

    [Fact]
    public async Task AKeptLayoutIsReadAndTheListenerGoesWithTheDockAsync()
    {
        JSInterop.Setup<string?>("sab.recall", "test.kept").SetResult("""{"Spots":[{"Id":"library","Side":"Right","Shown":true,"Weight":1}],"LeftWidth":280,"RightWidth":300}""");
        var state = new PaneDockState(Js, "test.kept", _defaults);
        await state.LoadAsync();

        Assert.Equal(DockSide.Right, state.Layout.SideOf("library"));
        Assert.Equal(300, state.Layout.RightWidth);

        var dock = Render<PaneDock>(p => p.Add(x => x.State, state).Add(x => x.Panes, Panes()));
        Assert.Equal(1, Subscribers(state, "Changed"));
        await DisposeComponentsAsync();
        Assert.Equal(0, Subscribers(state, "Changed"));
        Assert.NotNull(dock);
    }

    private static IReadOnlyList<DockPane> Panes() =>
    [
        new("library", "Library", Text("The widgets")),
        new("properties", "Properties", Text("A widget's properties")),
    ];

    private static RenderFragment Text(string words) => builder => builder.AddContent(0, words);
}
