namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>Widgets (the Streamlit extension's routes_widgets.py): the lists, one widget (get, save, header, delete),
/// a property written into its code, copy, Upgrade to In/Out, a run alone and its headless check, the previews, the
/// live properties and the checks of a name and a value, the pickers' context.</summary>
public sealed class WidgetsClient
{
    private readonly ApiClient _api;

    public WidgetsClient(ApiClient api)
    {
        _api = api;
    }

    public Task<WidgetListing> ListAsync() => _api.GetAsync<WidgetListing>("/streamlit/widgets");

    public Task<WidgetContext> ContextAsync() => _api.GetAsync<WidgetContext>("/streamlit/widgets/context");

    public Task<WidgetFull> GetAsync(string name) => _api.GetAsync<WidgetFull>(One(name));

    public Task<WidgetFull> NewAsync() => _api.PostAsync<WidgetFull>("/streamlit/widgets");

    /// <summary>The code saved below its header (never a prebuilt one).</summary>
    public Task<WidgetFull> SaveAsync(string name, string code) => _api.PutAsync<WidgetFull>(One(name), new { code });

    /// <summary>The header alone: a new name (every canvas follows) or description.</summary>
    public Task<WidgetFull> HeaderAsync(string name, IReadOnlyDictionary<string, string> changes) => _api.PatchAsync<WidgetFull>(One(name), changes);

    public Task DeleteAsync(string name) => _api.DeleteAsync(One(name));

    public Task<WidgetFull> CopyAsync(string name, string? to) =>
        _api.PostAsync<WidgetFull>($"{One(name)}/copy", to is null ? new Dictionary<string, object>() : new { to });

    public Task<WidgetLive> PropertiesAsync(string code) => _api.PostAsync<WidgetLive>("/streamlit/widgets/properties", new { code });

    public Task<NameCheck> CheckNameAsync(string name, string own) =>
        _api.GetAsync<NameCheck>($"/streamlit/widgets/check-name?name={ApiClient.Part(name)}&own={ApiClient.Part(own)}");

    /// <summary>A value checked before it is kept: the Canvas sends the widget's name, the Widgets window its code.</summary>
    public Task<CheckedValue> CheckValueAsync(IReadOnlyDictionary<string, object?> body) => _api.PostAsync<CheckedValue>("/streamlit/widgets/check-value", body);

    /// <summary>A default written into only its own characters of the code.</summary>
    public Task<WidgetFull> SetPropertyAsync(string name, IReadOnlyDictionary<string, object?> body) => _api.PostAsync<WidgetFull>($"{One(name)}/property", body);

    public Task<UpgradePlan> UpgradePreviewAsync(string name) => _api.PostAsync<UpgradePlan>($"{One(name)}/upgrade");

    public Task<UpgradeDone> UpgradeAsync(string name) => _api.PostAsync<UpgradeDone>($"{One(name)}/upgrade", new { apply = true });

    public Task<WidgetRun> RunAsync(string name, string code, string window) => _api.PostAsync<WidgetRun>($"{One(name)}/run", new { code, window });

    public Task<WidgetCheck> CheckAsync(string name, string code) => _api.PostAsync<WidgetCheck>($"{One(name)}/check", new { code });

    public Task StopAsync(string window) => _api.PostAsync("/streamlit/widgets/stop", new { window });

    /// <summary>A widget's preview in a theme: first (a board's), retry (Try again).</summary>
    public Task<PreviewState> PreviewAsync(string name, string theme, bool first, bool retry) =>
        _api.GetAsync<PreviewState>($"{One(name)}/preview?theme={theme}{(first ? "&first=1" : string.Empty)}{(retry ? "&retry=1" : string.Empty)}");

    /// <summary>What the previews need, installed into the project's Python (the Environment's Install).</summary>
    public Task InstallIntoProjectAsync(IReadOnlyList<string> names) => _api.PostAsync("/environment/libraries/install", new { names });

    /// <summary>What the previews need, installed into the app's own Python (a blade's packages' route).</summary>
    public Task InstallIntoAppAsync(IReadOnlyList<string> packages) => _api.PostAsync("/blades/install", new { packages });

    private static string One(string name) => $"/streamlit/widgets/{ApiClient.Part(name)}";
}
