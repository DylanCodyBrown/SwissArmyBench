using Bunit;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Pages.Workbench.Tabs;

using Xunit;

namespace SwissArmyBench.Web.Tests;

public sealed class GroupsViewTests : AppTestContext
{
    [Fact]
    public void ASplitDrawsEachGroupWithASashBetween()
    {
        var layout = new TabLayout();
        layout.Add(1);
        layout.Add(2);
        layout.Split(2, SplitSide.Right);
        RenderFragment<TabGroup> group = g => builder => builder.AddMarkupContent(0, $"<p class=\"g\">{string.Join(",", g.Tabs)}</p>");

        var view = Render<GroupsView>(p => p.Add(x => x.Node, layout.Root).Add(x => x.Group, group));

        Assert.Equal(["1", "2"], view.FindAll("p.g").Select(p => p.TextContent));
        Assert.Single(view.FindAll(".wb-gsash"));
    }
}
