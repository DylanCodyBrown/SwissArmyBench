using SwissArmyBench.Web.Pages.Workbench.Tabs;
using SwissArmyBench.Web.State;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The Notebooks and Scripts pages' tab groups (the classic workbenchGroups.ts moves) and the palette's
/// matching: pure logic, no page drawn.</summary>
public sealed class WorkbenchTabsTests
{
    [Fact]
    public void TabsGoInTheFocusedGroupAfterTheOneInFront()
    {
        var layout = new TabLayout();
        layout.Add(1);
        layout.Add(2);
        layout.Show(1);
        layout.Add(3);

        Assert.Equal([1, 3, 2], layout.Focused.Tabs);
        Assert.Equal(3, layout.Current);
    }

    [Fact]
    public void ASplitNeedsAnotherTabAndMovesTheTabToANewGroup()
    {
        var layout = new TabLayout();
        layout.Add(1);

        Assert.False(layout.Split(1, SplitSide.Right)); // its group's only tab
        layout.Add(2);
        Assert.True(layout.Split(2, SplitSide.Right));

        var split = Assert.IsType<TabSplit>(layout.Root);
        Assert.True(split.Row);
        Assert.Equal(2, layout.Groups.Count);
        Assert.Equal([1], layout.Groups[0].Tabs);
        Assert.Equal([2], layout.Groups[1].Tabs);
        Assert.Equal(2, layout.Current);
    }

    [Fact]
    public void ClosingAGroupsLastTabTakesTheGroupAway()
    {
        var layout = new TabLayout();
        layout.Add(1);
        layout.Add(2);
        layout.Split(2, SplitSide.Down);

        layout.Remove(2);

        Assert.IsType<TabGroup>(layout.Root);
        Assert.Equal([1], layout.Focused.Tabs);
        Assert.Equal(1, layout.Current);
    }

    [Fact]
    public void ATabMovesToAnotherGroupAndReordersInItsRow()
    {
        var layout = new TabLayout();
        layout.Add(1);
        layout.Add(2);
        layout.Add(3);
        layout.Split(3, SplitSide.Right);
        layout.Focus(layout.Groups[0]);

        layout.MoveTo(2, layout.Groups[1]);
        layout.Reorder(2, 1);

        Assert.Equal([1], layout.Groups[0].Tabs);
        Assert.Equal([3, 2], layout.Groups[1].Tabs);
        Assert.Equal(3, layout.NextTab(1));
    }

    [Fact]
    public void ASashKeepsEachSideWithinItsLimits()
    {
        var split = new TabSplit(true);
        split.Sizes.AddRange([1, 1]);

        TabLayout.Resize(split, 1, 0.99);

        Assert.Equal(1.8, split.Sizes[0], 6);
        Assert.Equal(0.2, split.Sizes[1], 6);
    }

    [Fact]
    public async Task TheOnePaletteTakesAPagesCommandsAndPutsRecentOnesFirstAsync()
    {
        var ran = new List<string>();
        Task RunAsync(string id)
        {
            ran.Add(id);
            return Task.CompletedTask;
        }
        var palette = new Commands();
        Func<IReadOnlyList<PaletteCommand>> page = () =>
        [
            new("a", "File", "New notebook", () => RunAsync("a")),
            new("b", "Run", "Run the selected cell", () => RunAsync("b")),
            new("c", "Cell", "Delete the cell", () => RunAsync("c"), WhyNot: "No cell is selected"),
        ];
        palette.SetPageCommands(page);

        Assert.True(await palette.RunIdAsync("b"));
        Assert.False(await palette.RunIdAsync("c"));
        Assert.Equal(["b", "a", "c"], palette.All().Take(3).Select(c => c.Id));
        Assert.Equal(["b"], ran);
        // Another page going takes only its own commands back: this page's stay until it goes.
        palette.WithdrawPageCommands(() => []);
        Assert.Contains(palette.All(), c => c.Id == "a");
        palette.WithdrawPageCommands(page);
        Assert.DoesNotContain(palette.All(), c => c.Id == "a");
    }
}
