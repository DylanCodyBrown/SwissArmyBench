using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Pages.Workbench;
using SwissArmyBench.Web.State;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>Notices no page followed before: a moved code file's tabs, the rail's areas after a mode change.</summary>
public sealed class NoticeFollowersTests : AppTestContext
{
    private readonly CannedServer _server = new CannedServer()
        .Answer("GET /rail", """{"labels": true}""")
        .Answer("GET /app/areas", """{"areas": []}""")
        .Answer("GET /app/modes", """{"modes": []}""");

    public NoticeFollowersTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
    }

    [Theory]
    [InlineData("/p/scripts/load.py", "/p/scripts/load.py", "/p/scripts/read.py", "/p/scripts/read.py")]
    [InlineData("/p/scripts/etl/load.py", "/p/scripts/etl", "/p/scripts/flows", "/p/scripts/flows/load.py")]
    [InlineData("C:\\p\\Scripts\\Load.py", "c:/p/scripts/load.py", "c:/p/scripts/read.py", "c:/p/scripts/read.py")]
    [InlineData("/p/scripts/load.py", "/p/scripts/load.py", null, "")]
    [InlineData("/p/scripts/loader.py", "/p/scripts/load", "/p/scripts/x", null)]
    [InlineData("/p/other.py", "/p/scripts/load.py", "/p/scripts/read.py", null)]
    public void AnOpenFileFollowsItsMovedModuleOrPackage(string path, string from, string? to, string? now)
    {
        Assert.Equal(now, MovedFiles.Follow(path, from, to));
    }

    [Fact]
    public async Task TheRailReadsItsAreasAgainWhenTheModesChangeAsync()
    {
        var rail = Get<RailState>();
        await rail.StartAsync();
        Assert.False(rail.CodeAppOn);
        _server.Answer("GET /app/modes", """{"modes": [{"type": "codeapp", "name": "Code app", "canvases": []}]}""");
        var changed = 0;
        rail.Changed += () => changed++;

        Get<LiveUpdates>().Notice("""{"type": "mode_changed"}""");

        for (var tries = 0; tries < 50 && !rail.CodeAppOn; tries++)
        {
            await Task.Delay(20, TestContext.Current.CancellationToken);
        }
        Assert.True(rail.CodeAppOn);
        Assert.True(changed > 0);
    }
}
