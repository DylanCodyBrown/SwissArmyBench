using System.Text.Json;

using Bunit;

using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Widgets;
using SwissArmyBench.Web.Layout;
using SwissArmyBench.Web.Pages.Canvas;
using SwissArmyBench.Web.State;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>Something a widget needs that its Python lacks pops up the one install prompt (the owner, 2026-11-23:
/// "when something needs installed, pop up the user install it in the ENV"): a run's "missing" problem read as the
/// prompt's packages, a preview's Install opening the prompt, Install now going where the server said.</summary>
public sealed class WidgetInstallPromptTests : AppTestContext
{
    private const string FailedPreview = """
        {"state": "failed", "said": "No Streamlit here.", "kind": "missing", "retry_in": 30,
         "missing": {"feature": "Streamlit widgets", "packages": ["streamlit", "xlrd"], "python": "/made/up/python", "command": "uv pip install streamlit xlrd"},
         "install": "project"}
        """;

    private readonly CannedServer _server = new CannedServer()
        .Answer("GET /streamlit/widgets/status_badge/preview", FailedPreview)
        .Answer("POST /environment/libraries/install", "{\"ok\": true}")
        .Answer("POST /blades/install", "{\"ok\": true}");

    public WidgetInstallPromptTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
        Services.AddScoped<WidgetsClient>();
    }

    [Fact]
    public void ARunsMissingProblemIsThePromptsPackages()
    {
        var said = JsonSerializer.Deserialize<WidgetRun>(
            """{"ok": false, "problem": {"kind": "missing", "feature": "Streamlit widgets", "packages": ["streamlit", "xlrd"], "python": "/p", "command": "uv pip install streamlit xlrd", "install": "app"}}""",
            ApiClient.Json)!;

        var missing = said.Problem!.Missing!;
        Assert.Equal("streamlit and xlrd", missing.Listed);
        Assert.Equal("/p", missing.Python);
        Assert.Equal("app", said.Problem.Install);
        Assert.Null(new WidgetRunProblem { Kind = "failed", Message = "No." }.Missing);
    }

    [Fact]
    public async Task InstallGoesWhereTheServerSaidAsync()
    {
        var widgets = Get<WidgetsClient>();

        await widgets.InstallAsync(WidgetsClient.ProjectPlace, ["streamlit"]);
        await widgets.InstallAsync("app", ["streamlit"]);

        Assert.Equal(["POST /environment/libraries/install", "POST /blades/install"], _server.Asked.Select(a => a.Route));
    }

    [Fact]
    public async Task APreviewsInstallOpensTheOnePromptAndInstallsIntoTheProjectAsync()
    {
        var host = Render<PackagePromptHost>();
        var heard = new List<PreviewState>();
        using var previews = new WidgetPreviews(Get<WidgetsClient>())
        {
            OnMissing = said =>
            {
                heard.Add(said);
                return Task.CompletedTask;
            },
        };
        var box = Render<PreviewBox>(p => p.Add(x => x.Name, "status_badge").Add(x => x.How, "board").AddCascadingValue(previews));

        box.WaitForAssertion(() => Assert.NotNull(box.Find(".cvs-ph-again")));
        Assert.Single(heard);
        Assert.Contains("Needs streamlit, xlrd to draw.", box.Find(".cvs-ph-line").TextContent);

        await box.InvokeAsync(() => box.Find(".cvs-ph-again").Click());
        host.Render();
        Assert.Equal("Install streamlit and xlrd?", host.Find(".dialog-head h2").TextContent);
        Assert.NotNull(Get<PackagePrompts>().Open);

        await host.InvokeAsync(() => host.FindAll(".dialog-foot button").Single(b => b.TextContent.Contains("Install now")).Click());
        host.WaitForAssertion(() => Assert.Contains(_server.Asked, a => a.Route == "POST /environment/libraries/install"));
        Assert.Null(Get<PackagePrompts>().Open);
    }
}
