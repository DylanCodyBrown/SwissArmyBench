using SwissArmyBench.Web.Pages.Scm;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The Source Control graph's swimlanes (VS Code's scmHistory.ts as the classic scmGraph.ts ports it): a
/// straight history keeps one lane, HEAD is a ring, a merge opens a second lane in the next colour, and the refs take
/// their lane's colour; the time in VS Code's words.</summary>
public sealed class ScmGraphTests
{
    private static GraphItem Item(string id, params string[] parents) => new(id, parents, $"subject {id}", "A Made-up Author", string.Empty, string.Empty, []);

    [Fact]
    public void A_straight_history_keeps_one_lane_and_head_is_a_ring()
    {
        var rows = ScmGraph.ViewModels([Item("c3", "c2"), Item("c2", "c1"), Item("c1")], new Dictionary<string, string?>(), "c3");
        Assert.Equal(["HEAD", "node", "node"], rows.Select(r => r.Kind));
        Assert.All(rows.Take(2), r => Assert.Single(r.Output));
        Assert.Empty(rows[2].Output);
        var circles = ScmGraph.Shapes(rows[0]).Where(s => s.Path is null).ToList();
        Assert.Equal(2, circles.Count);
        Assert.Equal(11, circles[0].Cx);
    }

    [Fact]
    public void A_merge_opens_a_lane_in_the_next_colour()
    {
        var rows = ScmGraph.ViewModels([Item("m", "a", "b"), Item("a", "base"), Item("b", "base"), Item("base")], new Dictionary<string, string?>(), null);
        Assert.Equal(["a", "b"], rows[0].Output.Select(n => n.Id));
        Assert.Equal(["scmGraph-foreground1", "scmGraph-foreground2"], rows[0].Output.Select(n => n.Color));
        Assert.Equal(2, ScmGraph.Shapes(rows[0]).Count(s => s.Path is null)); // a merge: two circles
        Assert.Equal(33, ScmGraph.Width(rows[0]));
    }

    [Fact]
    public void A_ref_named_in_the_colours_paints_its_lane()
    {
        var head = Item("c2", "c1") with { References = [new GraphRef("refs/remotes/origin/main", "origin/main", "remote")] };
        var colors = new Dictionary<string, string?> { ["refs/remotes/origin/main"] = ScmGraph.RemoteRefColor };
        var rows = ScmGraph.ViewModels([head, Item("c1")], colors, "c2");
        Assert.Equal(ScmGraph.RemoteRefColor, rows[0].Output[0].Color);
        Assert.Equal(ScmGraph.RemoteRefColor, rows[0].Item.References[0].Color);
    }

    [Fact]
    public void How_long_ago_in_vs_codes_words()
    {
        var now = new DateTimeOffset(2026, 11, 23, 12, 0, 0, TimeSpan.Zero);
        Assert.Equal("1 sec ago", ScmTime.Ago(now, now));
        Assert.Equal("3 mins ago", ScmTime.Ago(now.AddMinutes(-3), now));
        Assert.Equal("1 day ago", ScmTime.Ago(now.AddDays(-1), now));
        Assert.Equal("2 wks ago", ScmTime.Ago(now.AddDays(-14), now));
    }
}
