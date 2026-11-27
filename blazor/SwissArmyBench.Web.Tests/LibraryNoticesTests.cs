using Bunit;

using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Layout;
using SwissArmyBench.Web.State;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>What the library says once reaches the page: taken as the main window opens, heard as it happens.</summary>
public sealed class LibraryNoticesTests : AppTestContext
{
    private readonly CannedServer _server = new CannedServer()
        .Answer("POST /library/notices", """{"notices": [{"kind": "moved", "text": "Your connections moved into the library."}]}""");

    public LibraryNoticesTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
    }

    [Fact]
    public void TheMainWindowTakesTheWaitingNoticesAndHearsNewOnes()
    {
        JSInterop.Setup<string?>("sab.windowName").SetResult(WhatsNewState.MainWindow);
        var notes = Get<Notes>();
        var host = Render<LibraryNotices>();

        host.WaitForAssertion(() => Assert.Contains(notes.Shown, n => n.Words == "Your connections moved into the library."));
        Get<LiveUpdates>().Notice("""{"type": "library_notice", "kind": "project", "text": "2 blades of made_up moved into the library."}""");

        Assert.Contains(notes.Shown, n => n.Words == "2 blades of made_up moved into the library.");
    }

    [Fact]
    public async Task AWindowPoppedOutTakesNoneAndTheHostLetsGoAsync()
    {
        JSInterop.Setup<string?>("sab.windowName").SetResult("sab-notebooks");
        var live = Get<LiveUpdates>();
        var before = Subscribers(live, nameof(LiveUpdates.NoticeArrived));
        var host = Render<LibraryNotices>();

        Assert.DoesNotContain(_server.Asked, a => a.Route == "POST /library/notices");
        Assert.NotNull(host);
        await DisposeComponentsAsync();
        Assert.Equal(before, Subscribers(live, nameof(LiveUpdates.NoticeArrived)));
    }
}
