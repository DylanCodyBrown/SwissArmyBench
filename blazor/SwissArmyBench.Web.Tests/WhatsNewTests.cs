using Bunit;

using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Api.Settings;
using SwissArmyBench.Web.Layout;
using SwissArmyBench.Web.State;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>What's New (the owner, 2026-11-25): an overlay over the page, each release's New features and Bug fixes
/// apart, the newest unfolded; X, Escape, a click outside and Got it close it and mark the version seen; the main
/// window opens it by itself after an update and a window popped out never does.</summary>
public sealed class WhatsNewTests : AppTestContext
{
    private const string AfterUpdate = """
        {"version": "0.0.39", "seen": "0.0.37", "open": true, "releases": [
          {"version": "0.0.39", "time": "2026-11-25 14:30 UTC", "features": ["Emoji picker", "**Collaboration** panel"], "fixes": []},
          {"version": "0.0.38", "time": "2026-11-25 00:26 UTC", "features": [], "fixes": ["Fixed: sab_api install error"]}
        ]}
        """;

    private readonly CannedServer _server = new CannedServer()
        .Answer("GET /whats-new", AfterUpdate)
        .Answer("POST /whats-new/seen", """{"version": "0.0.39", "seen": "0.0.39", "open": false}""");

    public WhatsNewTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
        Services.AddScoped<SettingsClient>();
    }

    private static IReadOnlyList<WhatsNewRelease> Releases() =>
    [
        new("0.0.39", "2026-11-25 14:30 UTC", ["Emoji picker"], []),
        new("0.0.38", "2026-11-25 00:26 UTC", [], ["Fixed: sab_api install error"]),
    ];

    [Fact]
    public void NothingShowsUntilItOpens()
    {
        var host = Render<WhatsNewHost>();

        Assert.Empty(host.FindAll(".whatsnew-shade"));
    }

    [Fact]
    public void EachReleaseHasItsTwoSectionsAndOnlyTheNewestIsUnfolded()
    {
        var host = Render<WhatsNewHost>();
        Get<WhatsNewState>().Show(Releases());

        var shown = host.WaitForElement(".whatsnew[role=dialog]");
        Assert.Equal("true", shown.GetAttribute("aria-modal"));
        var releases = host.FindAll("details.whatsnew-release");
        Assert.Equal(2, releases.Count);
        Assert.True(releases[0].HasAttribute("open"));
        Assert.False(releases[1].HasAttribute("open"));
        Assert.Contains("0.0.39", releases[0].QuerySelector("summary")!.TextContent, StringComparison.Ordinal);
        Assert.Contains("2026-11-25 14:30 UTC", releases[0].TextContent, StringComparison.Ordinal);
        var features = releases[0].QuerySelector(".whatsnew-section.features")!;
        Assert.Equal("New features", features.QuerySelector("h3")!.TextContent.Trim());
        Assert.NotNull(features.QuerySelector("h3 svg"));
        Assert.Equal("Emoji picker", features.QuerySelector("li")!.TextContent);
        Assert.Contains("None.", releases[0].QuerySelector(".whatsnew-section.fixes")!.TextContent, StringComparison.Ordinal);
        Assert.Equal("Fixed: sab_api install error", releases[1].QuerySelector(".whatsnew-section.fixes li")!.TextContent);
    }

    [Theory]
    [InlineData("got-it")]
    [InlineData("close")]
    [InlineData("escape")]
    [InlineData("outside")]
    public void EveryWayOfClosingMarksItSeen(string how)
    {
        var host = Render<WhatsNewHost>();
        Get<WhatsNewState>().Show(Releases());
        host.WaitForElement(".whatsnew");

        switch (how)
        {
            case "got-it":
                host.Find(".dialog-foot .btn.primary").Click();
                break;
            case "close":
                host.Find("button[aria-label=Close]").Click();
                break;
            case "escape":
                host.Find(".whatsnew-shade").KeyDown("Escape");
                break;
            default:
                host.Find(".whatsnew-shade").Click();
                break;
        }

        host.WaitForAssertion(() => Assert.Empty(host.FindAll(".whatsnew-shade")));
        Assert.False(Get<WhatsNewState>().Open);
        Assert.Contains(_server.Asked, a => a.Route == "POST /whats-new/seen");
    }

    [Fact]
    public void AClickInsideTheWindowLeavesItOpen()
    {
        var host = Render<WhatsNewHost>();
        Get<WhatsNewState>().Show(Releases());

        var body = host.WaitForElement(".whatsnew-body");

        // The window stops the click on its way out: it never reaches the shade's close.
        Assert.Throws<MissingEventHandlerException>(() => body.Click());
        Assert.True(Get<WhatsNewState>().Open);
        Assert.DoesNotContain(_server.Asked, a => a.Route == "POST /whats-new/seen");
    }

    [Fact]
    public async Task TheMainWindowOpensItByItselfAfterAnUpdateAsync()
    {
        JSInterop.Setup<string?>("sab.windowName").SetResult(WhatsNewState.MainWindow);
        var host = Render<WhatsNewHost>();

        await Get<WhatsNewState>().StartAsync();

        host.WaitForAssertion(() => Assert.Equal(2, host.FindAll("details.whatsnew-release").Count));
        Assert.Contains("Collaboration</strong> panel", host.Markup, StringComparison.Ordinal);
    }

    [Fact]
    public async Task AWindowPoppedOutNeverOpensItAsync()
    {
        JSInterop.Setup<string?>("sab.windowName").SetResult("sab-notebooks");
        var host = Render<WhatsNewHost>();

        await Get<WhatsNewState>().StartAsync();

        Assert.Empty(host.FindAll(".whatsnew-shade"));
        Assert.DoesNotContain(_server.Asked, a => a.Route == "GET /whats-new");
    }

    [Fact]
    public void TheStateLetsGoOfTheLiveNotices()
    {
        var live = Get<LiveUpdates>();
        var news = Get<WhatsNewState>();
        Assert.Equal(1, Subscribers(live, "NoticeArrived"));

        news.Dispose();

        Assert.Equal(0, Subscribers(live, "NoticeArrived"));
    }
}
