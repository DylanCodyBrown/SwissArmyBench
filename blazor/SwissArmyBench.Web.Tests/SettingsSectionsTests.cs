using Bunit;

using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Pages.Settings;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>Settings in one column with its section list on the left: the list's lines in the page's order (the Team
/// box first after Theme), a box that is not drawn left out, the section in view marked, a click a jump.</summary>
public sealed class SettingsSectionsTests : AppTestContext
{
    private readonly CannedServer _server = new();

    public SettingsSectionsTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
        Services.AddScoped<SwissArmyBench.Web.Api.SessionLog.SessionLogClient>();
        JSInterop.SetupModule("./js/settings.js").Mode = JSRuntimeMode.Loose;
    }

    private static string[] Lines(IRenderedComponent<SettingsPage> page) => [.. page.FindAll(".settings-nav-item").Select(b => b.TextContent.Trim())];

    [Fact]
    public void TheTeamBoxStaysFirstAfterTheme() =>
        Assert.Equal(["theme", "team"], SettingsSection.All.Take(2).Select(s => s.Id));

    [Fact]
    public void TheListNamesTheSectionsInThePagesOrderWithThemeMarked()
    {
        var page = Render<SettingsPage>();

        Assert.Equal(["Theme", "Team", "Collaboration", "Session", "Claude", "Beta", "Connect an agent"], Lines(page));
        Assert.Equal("true", page.Find(".settings-nav-item.current").GetAttribute("aria-current"));
        Assert.Equal("Theme", page.Find(".settings-nav-item.current").TextContent.Trim());
        // The boxes follow the list's order in the one column.
        Assert.Equal(SettingsSection.All.Select(s => s.Id), page.FindAll(".settings-sections > .settings-section").Select(s => s.GetAttribute("data-section")));
    }

    [Fact]
    public async Task ThePageSaysWhichBoxesAreDrawnAndWhichIsInViewAsync()
    {
        var page = Render<SettingsPage>();

        await page.InvokeAsync(() => page.Instance.OnSections(["theme", "team", "updates", "beta"], "beta"));

        Assert.Equal(["Theme", "Team", "Updates", "Beta"], Lines(page));
        Assert.Equal("Beta", page.Find(".settings-nav-item.current").TextContent.Trim());
        Assert.Single(page.FindAll(".settings-nav-item[aria-current]"));
    }

    [Fact]
    public void AClickMarksItsSectionAndAsksThePageToJump()
    {
        var page = Render<SettingsPage>();

        page.Find(".settings-nav-item[data-jump=claude]").Click();

        Assert.Equal("Claude", page.Find(".settings-nav-item.current").TextContent.Trim());
    }
}
