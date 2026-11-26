using Bunit;

using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Api.Canvas;
using SwissArmyBench.Web.Api.Widgets;
using SwissArmyBench.Web.Pages.Canvas;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The Canvas full screen (the owner, 2026-11-26): its button and F11, what goes (the top bar, the bottom bar,
/// the panes), the strip left in a corner with the panes as overlays, remembered, and the way back.</summary>
public sealed class CanvasFullScreenTests : AppTestContext
{
    private const string State = """
        {"canvas": "k1", "path": "/made/up/shop/sales.canvas.json", "name": "Sales", "version": 3,
         "model": {"name": "Sales", "sizing": {"columns": 12, "rowHeight": 40, "gap": 8, "snap": true, "step": 8},
                   "pages": [{"id": "p1", "name": "Home"}]},
         "undo": 1, "redo": 0}
        """;

    private readonly CannedServer _server = new CannedServer()
        .Answer("GET /streamlit/widgets", """{"widgets": []}""")
        .Answer("GET /streamlit/widgets/context", "{}")
        .Answer("POST /streamlit/canvases", State);

    public CanvasFullScreenTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
        Services.AddScoped<CanvasClient>();
        Services.AddScoped<WidgetsClient>();
        Services.AddScoped<SwissArmyBench.Web.Api.Sharing.SharingClient>();
        JSInterop.SetupModule("./js/canvas.js").Mode = JSRuntimeMode.Loose;
    }

    private IRenderedComponent<CanvasPage> Shown()
    {
        Get<NavigationManager>().NavigateTo("canvas?path=%2Fmade%2Fup%2Fshop%2Fsales.canvas.json");
        return Render<CanvasPage>();
    }

    private IRenderedComponent<CanvasPage> Opened()
    {
        var page = Shown();
        page.WaitForElement(".cvs-bottom");
        return page;
    }

    [Fact]
    public void TheTopBarHasFullScreenWithItsKey()
    {
        var page = Opened();

        var button = page.Find(".cvs-top .cvs-full-toggle");
        Assert.Equal("Full screen (F11)", button.GetAttribute("title"));
        Assert.Empty(page.FindAll(".cvs-full-strip"));
    }

    [Fact]
    public void FullScreenLeavesTheBoardAndTheStripAlone()
    {
        var page = Opened();
        Assert.NotEmpty(page.FindAll(".dock .cvs-pane"));

        page.Find(".cvs-full-toggle").Click();

        Assert.Empty(page.FindAll(".cvs-top"));
        Assert.Empty(page.FindAll(".cvs-bottom"));
        Assert.Empty(page.FindAll(".dock .cvs-pane"));
        Assert.NotNull(page.Find("main.cvs.cvs-is-full .cvs-stage"));
        var strip = page.Find(".cvs-full-strip[role=toolbar]");
        foreach (var name in new[] { "Leave full screen", "Play", "Undo", "Redo", "Zoom out", "Zoom in", "Widgets", "Properties" })
        {
            Assert.NotNull(strip.QuerySelector($"button[aria-label='{name}']"));
        }
        Assert.False(strip.QuerySelector("button[aria-label=Undo]")!.HasAttribute("disabled"));
        Assert.True(strip.QuerySelector("button[aria-label=Redo]")!.HasAttribute("disabled"));
        var told = JSInterop.Invocations["sab.fullScreen"].Single();
        Assert.Equal([true, "cvs-full"], told.Arguments);
        Assert.Contains(JSInterop.Invocations["sab.remember"], i => i.Arguments[0] as string == "canvas.full" && i.Arguments[1] as string == "1");
    }

    [Fact]
    public void TheStripShowsOnePaneOverTheBoardAtATime()
    {
        var page = Opened();
        page.Find(".cvs-full-toggle").Click();

        page.Find(".cvs-full-strip [data-pane=widgets]").Click();
        Assert.NotNull(page.Find("aside.cvs-full-overlay[data-pane=widgets] .cvs-full-overlay-body"));
        Assert.Equal("true", page.Find(".cvs-full-strip [data-pane=widgets]").GetAttribute("aria-pressed"));

        page.Find(".cvs-full-strip [data-pane=properties]").Click();
        Assert.Single(page.FindAll("aside.cvs-full-overlay"));
        Assert.NotNull(page.Find("aside.cvs-full-overlay[data-pane=properties]"));

        page.Find("aside.cvs-full-overlay button[aria-label='Close Properties']").Click();
        Assert.Empty(page.FindAll("aside.cvs-full-overlay"));
    }

    [Fact]
    public async Task LeavingBringsEverythingBackAsync()
    {
        var page = Opened();
        page.Find(".cvs-full-toggle").Click();
        page.Find(".cvs-full-strip [data-pane=widgets]").Click();

        // Escape, the desktop app's F11 or the browser's own way out: the page's FullScreen(false).
        await page.InvokeAsync(() => page.Instance.FullScreenAsync(false));

        page.WaitForElement(".cvs-top");
        Assert.NotNull(page.Find(".cvs-bottom"));
        Assert.Empty(page.FindAll(".cvs-full-strip"));
        Assert.Empty(page.FindAll("aside.cvs-full-overlay"));
        Assert.Equal([false, "cvs-full"], JSInterop.Invocations["sab.fullScreen"].Last().Arguments);
        Assert.Contains(JSInterop.Invocations["sab.remember"], i => i.Arguments[0] as string == "canvas.full" && i.Arguments[1] as string == "0");
    }

    [Fact]
    public void LeftInFullScreenItOpensInFullScreen()
    {
        JSInterop.Setup<string?>("sab.recall", "canvas.full").SetResult("1");

        var page = Shown();

        page.WaitForElement(".cvs-full-strip");
        Assert.Empty(page.FindAll(".cvs-top"));
    }
}
