using Bunit;

using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Api.LocalApi;
using SwissArmyBench.Web.Pages.Apis;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>API.py's Endpoints panel for the Scripts page, over a made-up project's local sandbox API: the line (Not
/// running, New endpoint…, Run), each endpoint, Run sent; with no API.py, one line.</summary>
public sealed class EndpointsPaneTests : AppTestContext
{
    private const string State = """
        {"project": "Made up", "exists": true, "file": "/made/up/API.py",
         "settings": {"name": "Made up API", "description": "", "target": "fastapi", "base_path": "/api"},
         "endpoints": [{"name": "list_orders", "method": "GET", "path": "/orders", "line": 12, "summary": "The orders",
                        "params": [], "data": ["Sandbox.orders"]}]}
        """;

    private readonly CannedServer _server = new();

    public EndpointsPaneTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
        Services.AddScoped<LocalApiClient>();
    }

    [Fact]
    public void EachEndpointAndTheLineThatRunsIt()
    {
        _server.Answer("GET /local-api", State).Answer("POST /local-api/run", "{}");
        var pane = Render<EndpointsPane>();

        pane.WaitForAssertion(() => Assert.Contains("Not running", pane.Find(".local-api-pane-bar").TextContent));
        Assert.Contains("New endpoint…", pane.Find(".local-api-pane-bar").TextContent);
        Assert.Contains("/orders", pane.Find(".local-api-endpoints").TextContent);
        pane.Find(".local-api-pane-bar button.primary").Click();
        pane.WaitForAssertion(() => Assert.Contains(_server.Asked, a => a.Route == "POST /local-api/run"));
    }

    [Fact]
    public void WithNoApiPyItSaysSo()
    {
        _server.Answer("GET /local-api", """{"project": "Made up", "exists": false}""");
        var pane = Render<EndpointsPane>();

        pane.WaitForAssertion(() => Assert.Equal("The project has no API.py yet.", pane.Find(".empty-note").TextContent));
    }

    [Fact]
    public void PayloadShapesSayEachWidgetsUseAndItsMismatch()
    {
        _server.Answer("GET /local-api/shapes", """
            {"uses": [{"canvas": "app.canvas.json", "page": "Orders", "widget": "orders_table", "event": "row_clicked",
                       "endpoint": "GET /orders", "expects": "a table", "answers": {"fields": {"order_id": "int", "total": "float"}},
                       "problems": ["total is a float; the widget expects text."]}]}
            """);
        var shapes = Render<PayloadShapesView>(p => p.Add(a => a.Version, new object()));

        shapes.WaitForAssertion(() => Assert.Equal("Payload shapes", shapes.Find("h3").TextContent));
        var row = shapes.Find("tbody tr").TextContent;
        Assert.Contains("orders_table · row_clicked", row);
        Assert.Contains("app › Orders", row);
        Assert.Contains("order_id: int, total: float", row);
        Assert.Contains("the widget expects text", shapes.Find("td.bad").TextContent);
    }

    [Fact]
    public void NoPayloadShapesWhileNoWidgetUsesAnEndpoint()
    {
        _server.Answer("GET /local-api/shapes", """{"uses": []}""");
        var shapes = Render<PayloadShapesView>(p => p.Add(a => a.Version, new object()));

        Assert.Empty(shapes.FindAll("section"));
    }
}
