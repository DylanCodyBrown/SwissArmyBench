using Microsoft.AspNetCore.Components.Web;
using Microsoft.AspNetCore.Components.WebAssembly.Hosting;
using Microsoft.FluentUI.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Analyze;
using SwissArmyBench.Web.Api.Apis;
using SwissArmyBench.Web.Api.App;
using SwissArmyBench.Web.Api.Canvas;
using SwissArmyBench.Web.Api.Catalog;
using SwissArmyBench.Web.Api.Connections;
using SwissArmyBench.Web.Api.Environment;
using SwissArmyBench.Web.Api.Extensions;
using SwissArmyBench.Web.Api.Files;
using SwissArmyBench.Web.Api.Git;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Api.Panels;
using SwissArmyBench.Web.Api.PowerBi;
using SwissArmyBench.Web.Api.Projects;
using SwissArmyBench.Web.Api.Relationships;
using SwissArmyBench.Web.Api.SessionLog;
using SwissArmyBench.Web.Api.Settings;
using SwissArmyBench.Web.Api.Sharing;
using SwissArmyBench.Web.Api.Structures;
using SwissArmyBench.Web.Api.Widgets;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web;

/// <summary>
/// The composition root: the one ApiClient, a typed client per area of the server (server/routes_*.py), and the
/// small state services the pages share (each raising one Changed event).
/// </summary>
public static class Program
{
    public static async Task Main(string[] args)
    {
        var builder = WebAssemblyHostBuilder.CreateDefault(args);
        builder.RootComponents.Add<App>("#app");
        builder.RootComponents.Add<HeadOutlet>("head::after");

        // The server is this page's own origin (the app's 127.0.0.1 port): the browser adds the page's cookie.
        var origin = new Uri(new Uri(builder.HostEnvironment.BaseAddress), "/");
        builder.Services.AddScoped(_ => new HttpClient { BaseAddress = origin });
        builder.Services.AddScoped<ApiClient>();
        AddClients(builder.Services);
        AddState(builder.Services);
        builder.Services.AddFluentUIComponents();

        await builder.Build().RunAsync();
    }

    private static void AddClients(IServiceCollection services)
    {
        services.AddScoped<AppClient>();
        services.AddScoped<ProjectsClient>();
        services.AddScoped<SessionLogClient>();
        services.AddScoped<FileChooser>();
        services.AddScoped<RelationshipsClient>();
        services.AddScoped<CatalogClient>();
        services.AddScoped<EnvironmentClient>();
        services.AddScoped<SettingsClient>();
        services.AddScoped<ConnectionsClient>();
        services.AddScoped<GridsClient>();
        services.AddScoped<WorkbenchClient>();
        services.AddScoped<AnalyzeClient>();
        services.AddScoped<StructuresClient>();
        services.AddScoped<ApisClient>();
        services.AddScoped<ExtensionsClient>();
        // The extensions' pages (the Canvas, Widgets, Share…).
        services.AddScoped<CanvasClient>();
        services.AddScoped<WidgetsClient>();
        services.AddScoped<SharingClient>();
        services.AddScoped<GitClient>();
        services.AddScoped<PowerBiClient>();
        services.AddScoped<PanelClient>();
    }

    private static void AddState(IServiceCollection services)
    {
        services.AddScoped<ThemeState>();
        services.AddScoped<LiveUpdates>();
        services.AddScoped<ProjectState>();
        services.AddScoped<RailState>();
        services.AddScoped<Notes>();
        services.AddScoped<Dialogs>();
        services.AddScoped<GridStatus>();
        services.AddScoped<PythonSession>();
    }
}
