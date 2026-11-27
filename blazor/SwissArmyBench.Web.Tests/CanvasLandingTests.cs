using Bunit;

using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Api.Canvas;
using SwissArmyBench.Web.Pages.Canvas;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The Canvas landing page: the shared header with New canvas over a card per canvas (its pages, a small
/// picture of its first page, its layouts, its last launch, and Open, Play and Export). Made-up canvases.</summary>
public sealed class CanvasLandingTests : AppTestContext
{
    private const string Path = "/made/up/shop/sales.canvas.json";

    private const string Listing = """
        {"folder": "/made/up/shop",
         "canvases": [
           {"name": "sales", "path": "/made/up/shop/sales.canvas.json", "broken": false, "pages": 2, "widgets": 3,
            "layouts": ["desktop", "phone"],
            "boxes": [{"kind": "container", "x": 0.0, "y": 0, "w": 0.5, "h": 300}, {"kind": "widget", "x": 0.5, "y": 0, "w": 0.25, "h": 150}],
            "launched": {"number": 4, "builds": 4, "time": "2026-11-20T09:30:00Z", "result": "ok"}},
           {"name": "empty", "path": "/made/up/shop/empty.canvas.json", "broken": false, "pages": 1, "widgets": 0,
            "layouts": ["desktop", "phone"], "boxes": [], "launched": null}],
         "old": [{"name": "old.stapp.json", "said": "An older app file."}]}
        """;

    private readonly CannedServer _server = new CannedServer().Answer("GET /streamlit/canvases", Listing);

    public CanvasLandingTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
        Services.AddScoped<CanvasClient>();
    }

    private static CanvasFile Sales() => new()
    {
        Name = "sales",
        Path = Path,
        Pages = 2,
        Widgets = 3,
        Layouts = ["desktop", "phone"],
        Boxes = [new CanvasCardBox("container", 0, 0, 0.5, 300), new CanvasCardBox("widget", 0.5, 0, 0.25, 150)],
        Launched = new CanvasLastBuild(4, 4, "2026-11-20T09:30:00Z", "ok"),
    };

    [Fact]
    public void ACardSaysItsPagesLayoutsAndLastLaunch()
    {
        var card = Render<CanvasCard>(p => p.Add(c => c.Canvas, Sales()));

        Assert.Equal("sales", card.Find(".canvas-card-name").TextContent);
        Assert.Equal("2 pages", card.Find("[data-fact=pages]").TextContent);
        Assert.Equal("Desktop and Phone layouts", card.Find("[data-fact=layouts]").TextContent);
        Assert.StartsWith("Launched ", card.Find("[data-fact=launched]").TextContent);
        Assert.EndsWith("· build 4", card.Find("[data-fact=launched]").TextContent);
        Assert.StartsWith("Build 4 of 4 kept", card.Find("[data-fact=launched]").GetAttribute("title"));
    }

    [Fact]
    public void OpenPlayAndExportGoToTheCanvasWhichDoesWhatWasAsked()
    {
        var card = Render<CanvasCard>(p => p.Add(c => c.Canvas, Sales()));

        const string Opens = "canvas?path=%2Fmade%2Fup%2Fshop%2Fsales.canvas.json";
        var actions = card.FindAll(".card-actions a");
        Assert.Equal(["Open", "Play", "Export"], actions.Select(a => a.TextContent));
        Assert.Equal([Opens, $"{Opens}&do=play", $"{Opens}&do=export"], actions.Select(a => a.GetAttribute("href")));
        Assert.Equal(["Open sales", "Play sales", "Export sales"], actions.Select(a => a.GetAttribute("aria-label")));
    }

    [Fact]
    public void ThePictureDrawsTheFirstPagesBoxesAndAnEmptyPageSaysSo()
    {
        var card = Render<CanvasCard>(p => p.Add(c => c.Canvas, Sales()));
        var boxes = card.FindAll(".canvas-card-box");
        Assert.Equal(2, boxes.Count);
        Assert.Equal("left: 0%; width: 50%; top: 0%; height: 83.33%;", boxes[0].GetAttribute("style"));
        Assert.Contains("widget", boxes[1].ClassList);

        var empty = Render<CanvasCard>(p => p.Add(c => c.Canvas, new CanvasFile { Name = "empty", Path = "/made/up/shop/empty.canvas.json", Pages = 1, Layouts = ["desktop", "phone"] }));
        Assert.Equal("Empty page: draw a container or drag a widget", empty.Find(".canvas-card-picture.empty").TextContent.Trim());
        Assert.Equal("1 page", empty.Find("[data-fact=pages]").TextContent);
        Assert.Equal("Not launched yet", empty.Find("[data-fact=launched]").TextContent);
    }

    [Fact]
    public void AFileThatDoesNotReadKeepsOnlyOpen()
    {
        var card = Render<CanvasCard>(p => p.Add(c => c.Canvas, new CanvasFile { Name = "torn", Path = "/made/up/shop/torn.canvas.json", Broken = true }));

        Assert.Equal(["Open"], card.FindAll(".card-actions a").Select(a => a.TextContent));
        Assert.Equal("Does not read", card.Find("[data-fact=pages]").TextContent);
    }

    [Fact]
    public void TheLandingHasTheSharedHeaderAndACardPerCanvas()
    {
        var landing = Render<CanvasLanding>();
        landing.WaitForElement(".canvas-card");

        Assert.Equal("Canvas", landing.Find(".area-page-head .area-page-title").TextContent.Trim());
        Assert.Equal("New canvas", landing.Find(".area-page-actions button.primary").TextContent.Trim());
        Assert.Equal(["sales", "empty"], landing.FindAll(".canvas-card").Select(c => c.GetAttribute("data-canvas")));
        Assert.Contains("old.stapp.json: An older app file.", landing.Find(".cvs-landing-old").TextContent);
    }

    [Fact]
    public void WithNoProjectTheSharedEmptyStateSaysToOpenOne()
    {
        _server.Answer("GET /streamlit/canvases", """{"folder": null, "canvases": [], "old": []}""");

        var landing = Render<CanvasLanding>();
        landing.WaitForElement(".empty-state");

        Assert.Contains("Open a project first", landing.Find(".empty-state").TextContent);
        Assert.Empty(landing.FindAll(".area-page-actions button"));
    }
}
