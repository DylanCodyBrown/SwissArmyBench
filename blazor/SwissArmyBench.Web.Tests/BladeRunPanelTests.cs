using System.Text.Json;

using Bunit;

using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Api.Blades;
using SwissArmyBench.Web.Pages.Workbench.Blades;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>A blade's run panel: a refusal of Open as table is said in the panel, never the page's crash bar.</summary>
public sealed class BladeRunPanelTests : AppTestContext
{
    // Every route answers 404 with the server's refusal shape: the result is gone (the server restarted).
    private readonly CannedServer _server = new();

    public BladeRunPanelTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
        Services.AddScoped<BladesClient>();
    }

    [Fact]
    public void ARefusedOpenAsTableIsSaidInThePanel()
    {
        using var result = JsonDocument.Parse("""{"kind": "table", "columns": ["region"], "rows": [["North"]], "total": 1}""");
        var run = new BladeRun("made_up", true, 0.1, Result: result.RootElement.Clone());
        var panel = Render<BladeRunPanel>(p => p.Add(x => x.Run, run).Add(x => x.Name, "made_up").Add(x => x.Tab, "result"));

        panel.FindAll("button").Single(b => b.TextContent.Trim() == "Open as table").Click();

        panel.WaitForAssertion(() => Assert.Contains("Not here.", panel.Markup, StringComparison.Ordinal));
        Assert.Contains(_server.Asked, a => a.Route == "POST /blades/made_up/result/open");
    }
}
