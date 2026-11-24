using Bunit;

using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Api.Settings;
using SwissArmyBench.Web.Pages.Settings;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The status bar's Update available (the owner, 2026-11-24: it sat on the Tour button and drew see-through):
/// a solid button of its own, never a ghost one.</summary>
public sealed class UpdateMarkTests : AppTestContext
{
    private readonly CannedServer _server = new CannedServer()
        .Answer("GET /updates", """{"current": "0.0.35", "latest": "0.0.36", "available": true, "version": "0.0.36"}""");

    public UpdateMarkTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
        Services.AddScoped<SettingsClient>();
    }

    [Fact]
    public void UpdateAvailableIsASolidButtonInTheStatusBar()
    {
        var mark = Render<UpdateFlow>(p => p.Add(u => u.Corner, true));

        var button = mark.WaitForElement("button.update-corner");
        Assert.Contains("Update available", button.TextContent, StringComparison.Ordinal);
        Assert.DoesNotContain("ghost", button.ClassList);
    }
}
