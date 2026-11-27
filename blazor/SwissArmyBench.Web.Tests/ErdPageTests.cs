using Bunit;

using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Api.Relationships;
using SwissArmyBench.Web.Pages.Erd;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The ERD with no relationships yet: the shared page header (its name, Import relationships, Manage
/// relationships) and the shared empty state (what the ERD is, Find relationships). Made-up tables.</summary>
public sealed class ErdPageTests : AppTestContext
{
    private readonly CannedServer _server = new CannedServer()
        .Answer("GET /relationships", """{"relationships": []}""")
        .Answer("GET /relationships/library", """{"models": [], "folders": [], "shared_folders": [], "problems": []}""")
        .Answer("GET /app/mode", """{"mode": {}}""");

    public ErdPageTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
        Services.AddScoped<RelationshipsClient>();
        Services.AddScoped<GridsClient>();
        Services.AddScoped<SwissArmyBench.Web.Components.PagePlugins>();
    }

    private IRenderedComponent<ErdPage> Shown(int tables)
    {
        var grids = string.Join(", ", Enumerable.Range(1, tables).Select(n => $$"""{"grid": "g{{n}}", "dataset": "made_up_{{n}}"}"""));
        _server.Answer("GET /grids", $$"""{"grids": [{{grids}}]}""");
        var page = Render<ErdPage>();
        page.WaitForElement(".empty-state");
        return page;
    }

    [Fact]
    public void TheSharedHeaderNamesThePageAndHoldsItsActions()
    {
        var page = Shown(4);

        Assert.Equal("ERD", page.Find(".area-page-head .area-page-title").TextContent.Trim());
        var actions = page.Find(".area-page-head .area-page-actions");
        Assert.Contains("Import relationships", actions.TextContent);
        Assert.Contains(actions.QuerySelectorAll("button"), b => b.TextContent.Trim() == "Manage relationships");
        Assert.DoesNotContain(actions.QuerySelectorAll("button"), b => b.TextContent.Trim() == "Fit");
    }

    [Fact]
    public void TheEmptyStateSaysWhatTheErdIsAndHowManyTablesItWillLookThrough()
    {
        var page = Shown(4);

        var empty = page.Find(".empty-state");
        Assert.Equal("No relationships yet", empty.QuerySelector("strong")!.TextContent);
        Assert.Contains("looks through the 4 open tables", empty.QuerySelector("p")!.TextContent);
        Assert.Equal("Find relationships", empty.QuerySelector("button.primary")!.TextContent.Trim());
    }

    [Fact]
    public void WithNoTableOpenItSaysToOpenSomeFirst()
    {
        var page = Shown(0);

        Assert.Contains("Open two or more tables", page.Find(".empty-state p").TextContent);
    }
}
