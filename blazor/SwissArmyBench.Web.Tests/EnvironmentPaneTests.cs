using Bunit;

using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Api.Connections;
using SwissArmyBench.Web.Api.Environment;
using SwissArmyBench.Web.Pages.Environment;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The Workbench's Environment pane: its heading, Open the Environment page, Hide Environment, and the same
/// list narrower on the Variables tab, read from a made-up project.</summary>
public sealed class EnvironmentPaneTests : AppTestContext
{
    private const string Listing = """
        {"items": [
           {"id": "variable:region_total", "kind": "variable", "name": "region_total", "type": "float", "value": "1,204.5", "from": "data.ipynb"},
           {"id": "table:orders", "kind": "table", "name": "orders", "size": "50 × 3", "value": "order_id, customer_id, total"}],
         "counts": {"table": 1, "variable": 1, "structure": 0, "setting": 0, "library": 0},
         "tabs": [{"kind": "table", "name": "Tables", "columns": []}, {"kind": "variable", "name": "Variables", "columns": []}],
         "memory": "1 KB"}
        """;

    public EnvironmentPaneTests()
    {
        var server = new CannedServer().Answer("GET /environment", Listing);
        Services.AddScoped(_ => new HttpClient(server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
        Services.AddScoped<EnvironmentClient>();
        Services.AddScoped<ConnectionsClient>();
    }

    [Fact]
    public void ThePaneHasItsHeadingItsButtonsAndTheVariablesList()
    {
        var pane = Render<EnvironmentPane>();

        Assert.Equal("Environment", pane.Find(".wb-vars-head h2").TextContent);
        Assert.NotNull(pane.Find("button[aria-label='Open the Environment page']"));
        Assert.NotNull(pane.Find("button[aria-label='Hide Environment']"));
        Assert.NotNull(pane.Find(".env.env-compact"));
        pane.WaitForAssertion(() => Assert.Contains("region_total", pane.Find(".env-list").TextContent));
        Assert.DoesNotContain("orders", pane.Find(".env-list").TextContent);
        Assert.Empty(pane.FindAll("h1.area-page-title"));
    }

    [Fact]
    public void HideAndOpenDoWhatTheySay()
    {
        var hidden = false;
        var pane = Render<EnvironmentPane>(p => p.Add(a => a.OnClose, () => hidden = true));

        pane.Find("button[aria-label='Hide Environment']").Click();
        Assert.True(hidden);
        pane.Find("button[aria-label='Open the Environment page']").Click();
        Assert.EndsWith("/environment", Get<NavigationManager>().Uri, StringComparison.Ordinal);
    }
}
