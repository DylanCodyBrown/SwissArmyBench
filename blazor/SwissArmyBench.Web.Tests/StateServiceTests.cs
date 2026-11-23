using Bunit;

using SwissArmyBench.Web.Layout;
using SwissArmyBench.Web.State;

using Xunit;

namespace SwissArmyBench.Web.Tests;

public sealed class StateServiceTests : AppTestContext
{
    [Fact]
    public void GridStatusRaisesChangedOnlyWhenItsWordsChange()
    {
        var status = new GridStatus();
        var raised = 0;
        status.Changed += () => raised++;

        status.Set("Count 5");
        status.Set("Count 5");
        status.Set(null);

        Assert.Equal(2, raised);
        Assert.Null(status.Words);
    }

    [Fact]
    public async Task TheStatusBarSubscribesWhileOpenAndLetsGoWhenItClosesAsync()
    {
        var live = Get<LiveUpdates>();
        var project = Get<ProjectState>();
        var grid = Get<GridStatus>();
        Render<StatusBar>();
        Assert.Equal(1, Subscribers(grid, nameof(GridStatus.Changed)));
        Assert.Equal(1, Subscribers(live, nameof(LiveUpdates.Changed)));
        Assert.Equal(1, Subscribers(project, nameof(ProjectState.Changed)));

        await DisposeComponentsAsync();

        Assert.Equal(0, Subscribers(grid, nameof(GridStatus.Changed)));
        Assert.Equal(0, Subscribers(live, nameof(LiveUpdates.Changed)));
        Assert.Equal(0, Subscribers(project, nameof(ProjectState.Changed)));
    }

    [Fact]
    public void AStateServiceLetsGoOfTheLiveNoticesWhenDisposed()
    {
        var live = Get<LiveUpdates>();
        var project = Get<ProjectState>();
        Assert.Equal(1, Subscribers(live, nameof(LiveUpdates.NoticeArrived)));

        project.Dispose();

        Assert.Equal(0, Subscribers(live, nameof(LiveUpdates.NoticeArrived)));
    }

    [Fact]
    public void TheStatusBarShowsTheSelectionsNumbers()
    {
        var bar = Render<StatusBar>();

        Get<GridStatus>().Set("Count 3 · Sum 12.00 · Average 4.00");

        bar.WaitForAssertion(() => Assert.Contains("Sum 12.00", bar.Find(".status-selection").TextContent));
    }
}
