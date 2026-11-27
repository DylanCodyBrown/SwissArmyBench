using Bunit;

using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Api.App;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.Layout;
using SwissArmyBench.Web.State;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>Pop out (the owner, 2026-11-27): the placeholder's words and its two buttons, the Pop out button of
/// every page, a popped-out window's own Reattach, and the keys an address shows.</summary>
public sealed class PopOutTests : AppTestContext
{
    private const string Popped = """
        {"popped": [{"key": "page:connections", "kind": "page", "name": "Connections", "address": "connections",
          "connected": true, "placeholder": "Connections is open in its own window"}], "mains": 1}
        """;

    private readonly CannedServer _server = new CannedServer()
        .Answer("GET /pop-outs", """{"popped": [], "mains": 1}""")
        .Answer("POST /pop-outs", """{"key": "page:settings", "kind": "page", "name": "Settings", "address": "settings", "connected": false, "placeholder": "Settings is open in its own window", "existing": false}""")
        .Answer("POST /pop-outs/reattach", """{"reattached": true}""")
        .Answer("POST /pop-outs/show", "{}");

    public PopOutTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
    }

    private static PopOutEntry Orders => new("table:g1", "table", "orders", "tables?grid=g1", true, "orders is open in its own window");

    [Theory]
    [InlineData("", "page:home")]
    [InlineData("connections?name=warehouse", "page:connections")]
    [InlineData("grids?grid=g1", "page:tables", "table:g1")]
    [InlineData("tables?grid=g%207&split=a,b", "page:tables", "table:g 7")]
    [InlineData("scripts?path=%2Fmade%2Fup%2Fload.py", "page:scripts", "doc:/made/up/load.py")]
    [InlineData("x-scm", "page:x-scm")]
    public void AnAddressShowsItsPageAndItsTableOrDocument(string address, params string[] keys)
    {
        Assert.Equal(keys, PopOutKeys.Of(address));
    }

    [Fact]
    public void ThePlaceholderSaysWhereItIsAndBringsItBackOrForward()
    {
        var placeholder = Render<PopOutPlaceholder>(p => p.Add(x => x.Entry, Orders));

        Assert.Equal("orders is open in its own window", placeholder.Find("p").TextContent);
        Assert.Equal(["Reattach", "Show window"], placeholder.FindAll("button").Select(b => b.TextContent.Trim()));
        Assert.Contains("empty-state", placeholder.Find("[role=status]").ClassList);

        placeholder.Find(".pop-out-show").Click();
        placeholder.WaitForAssertion(() => Assert.Contains(_server.Asked, a => a.Route == "POST /pop-outs/show" && a.Body.Contains("table:g1", StringComparison.Ordinal)));
        Assert.Equal("table:g1", JSInterop.Invocations["sab.popOut.show"].Single().Arguments[0]);

        placeholder.Find(".pop-out-reattach").Click();
        placeholder.WaitForAssertion(() => Assert.Contains(_server.Asked, a => a.Route == "POST /pop-outs/reattach" && a.Body.Contains("table:g1", StringComparison.Ordinal)));
        placeholder.WaitForAssertion(() => Assert.Equal("table:g1", JSInterop.Invocations["sab.popOut.close"].Single().Arguments[0]));
    }

    [Fact]
    public async Task ThePopOutButtonOpensThePageInFrontInItsOwnWindowAsync()
    {
        JSInterop.Setup<bool>("sab.popOut.open", _ => true).SetResult(true);
        Get<NavigationManager>().NavigateTo("settings");
        await Get<PopOuts>().StartAsync();
        var corner = Render<PopOutCorner>();

        var button = corner.Find("button");
        Assert.Equal("Pop out", button.GetAttribute("aria-label"));
        Assert.Equal("Pop out: Settings in its own window", button.GetAttribute("title"));
        button.Click();

        corner.WaitForAssertion(() => Assert.Contains(_server.Asked, a => a.Route == "POST /pop-outs" && a.Body.Contains("\"key\":\"page:settings\"", StringComparison.Ordinal) && a.Body.Contains("\"open\":false", StringComparison.Ordinal)));
        corner.WaitForAssertion(() => Assert.Equal(["page:settings", "settings"], JSInterop.Invocations["sab.popOut.open"].Single().Arguments.Take(2)));
    }

    [Fact]
    public async Task ThePlaceWhereAPoppedOutPageWasShowsThePlaceholderAndNoPopOutButtonAsync()
    {
        _server.Answer("GET /pop-outs", Popped);
        Get<NavigationManager>().NavigateTo("connections");
        await Get<PopOuts>().StartAsync();

        var gate = Render<PopOutGate>(p => p.AddChildContent("<p class=\"the-page\">the page</p>"));
        var corner = Render<PopOutCorner>();

        Assert.Equal("Connections is open in its own window", gate.Find(".pop-out-placeholder p").TextContent);
        Assert.Empty(gate.FindAll(".the-page"));
        Assert.Empty(corner.FindAll("button"));

        // Brought back (the pop_outs notice): the page is drawn again, and its Pop out button.
        Get<LiveUpdates>().Notice("""{"type": "pop_outs", "popped": [], "mains": 1}""");
        gate.WaitForAssertion(() => Assert.Single(gate.FindAll(".the-page")));
        corner.WaitForAssertion(() => Assert.Equal("Pop out", corner.Find("button").GetAttribute("aria-label")));
        // Another page of the same window is never blank.
        Assert.Null(Get<PopOuts>().Elsewhere("page:settings"));
    }

    [Fact]
    public async Task APoppedOutWindowDrawsItsPageWithReattachAndClosesOnceBroughtBackAsync()
    {
        _server.Answer("GET /pop-outs", Popped);
        JSInterop.Setup<string?>("sab.popOut.own").SetResult("page:connections");
        Get<NavigationManager>().NavigateTo("connections");
        var popOuts = Get<PopOuts>();
        await popOuts.StartAsync();

        var gate = Render<PopOutGate>(p => p.AddChildContent("<p class=\"the-page\">the page</p>"));
        var corner = Render<PopOutCorner>();

        Assert.Equal("page:connections", popOuts.Own);
        Assert.Single(gate.FindAll(".the-page"));
        Assert.Equal("page", JSInterop.Invocations["sab.popOut.mark"].Single().Arguments[0]);
        var reattach = corner.Find("button.reattach");
        Assert.Equal("Reattach", reattach.TextContent.Trim());
        Assert.Equal("Reattach: back in the main window, this window closes", reattach.GetAttribute("title"));

        // The main window closed first: Reattach says what it will do instead.
        Get<LiveUpdates>().Notice(Popped.Replace("\"mains\": 1", "\"mains\": 0", StringComparison.Ordinal).Replace("{\"popped\"", "{\"type\": \"pop_outs\", \"popped\"", StringComparison.Ordinal));
        corner.WaitForAssertion(() => Assert.Contains("the main window is closed, so it opens in a new one", corner.Find("button.reattach").GetAttribute("title"), StringComparison.Ordinal));
        corner.Find("button.reattach").Click();
        corner.WaitForAssertion(() => Assert.Equal("connections", JSInterop.Invocations["sab.popOut.toMain"].Single().Arguments[0]));
        corner.WaitForAssertion(() => Assert.Single(JSInterop.Invocations["sab.popOut.closeSelf"]));
        Assert.Contains(_server.Asked, a => a.Route == "POST /pop-outs/reattach" && a.Body.Contains("\"front\":false", StringComparison.Ordinal));
    }

    [Fact]
    public async Task APoppedOutWindowClosesItselfWhenItsPageIsReattachedElsewhereAsync()
    {
        _server.Answer("GET /pop-outs", Popped);
        JSInterop.Setup<string?>("sab.popOut.own").SetResult("page:connections");
        var saved = false;
        var popOuts = Get<PopOuts>();
        popOuts.BeforeClose = () =>
        {
            saved = true;
            return Task.CompletedTask;
        };
        await popOuts.StartAsync();
        var corner = Render<PopOutCorner>();

        Get<LiveUpdates>().Notice("""{"type": "pop_outs", "popped": [], "mains": 1}""");

        corner.WaitForAssertion(() => Assert.Single(JSInterop.Invocations["sab.popOut.closeSelf"]));
        Assert.True(saved);
    }
}
