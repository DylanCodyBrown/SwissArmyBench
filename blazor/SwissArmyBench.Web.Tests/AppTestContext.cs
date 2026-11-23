using Bunit;

using Microsoft.Extensions.DependencyInjection;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.App;
using SwissArmyBench.Web.Api.Files;
using SwissArmyBench.Web.Api.Projects;
using SwissArmyBench.Web.Api.Settings;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Tests;

/// <summary>
/// A bUnit context with the app's services as Program.cs registers them, over a server that is not there (no test
/// here reaches it: the components are drawn from their parameters and the state services' values). JavaScript
/// calls answer their defaults (loose mode).
/// </summary>
public abstract class AppTestContext : BunitContext
{
    protected AppTestContext()
    {
        JSInterop.Mode = JSRuntimeMode.Loose;
        Services.AddScoped(_ => new HttpClient { BaseAddress = new Uri("http://127.0.0.1:9/") });
        Services.AddScoped<ApiClient>();
        Services.AddScoped<AppClient>();
        Services.AddScoped<ProjectsClient>();
        Services.AddScoped<SettingsClient>();
        Services.AddScoped<LiveUpdates>();
        Services.AddScoped<ProjectState>();
        Services.AddScoped<RailState>();
        Services.AddScoped<ThemeState>();
        Services.AddScoped<Notes>();
        Services.AddScoped<Dialogs>();
        Services.AddScoped<GridStatus>();
        Services.AddScoped<SettingsClient>();
        Services.AddScoped<BetaState>();
        Services.AddScoped<FileChooser>();
        Services.AddScoped<PackagePrompts>();
        Services.AddScoped<VariableAsks>();
        Services.AddScoped<TourState>();
        Services.AddScoped<FilePicks>();
        Services.AddScoped<Api.Environment.EnvironmentClient>();
        Services.AddScoped<Api.Variables.VariablesClient>();
    }

    /// <summary>How many handlers an event of a service holds now (a field-like event's own delegate).</summary>
    protected static int Subscribers(object service, string eventName)
    {
        var field = service.GetType().GetField(eventName, System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);
        return (field?.GetValue(service) as Delegate)?.GetInvocationList().Length ?? 0;
    }

    protected T Get<T>()
        where T : notnull => Services.GetRequiredService<T>();

    protected IJSRuntime Js => Get<IJSRuntime>();
}
