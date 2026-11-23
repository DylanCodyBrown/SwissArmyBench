using System.Text.Json;

namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A document's modes (routes_script_runs.py, routes_projects.py): a script's run settings, and data.ipynb's
/// data dictionary (its tables, with the descriptions it keeps).</summary>
public sealed class DocumentModesClient
{
    private readonly ApiClient _api;

    public DocumentModesClient(ApiClient api)
    {
        _api = api;
    }

    public Task<RunSettings> RunSettingsAsync(string path) => _api.GetAsync<RunSettings>($"/workbench/scripts/settings?path={ApiClient.Part(path)}");

    public Task<RunSettings> SetRunSettingsAsync(string path, string arguments, IReadOnlyList<RunVariable> variables) =>
        _api.PutAsync<RunSettings>("/workbench/scripts/settings", new { path, arguments, variables });

    public Task<DictionaryTables> DictionaryAsync(IReadOnlyList<(string Name, string Source)> tables, JsonElement descriptions) =>
        _api.PostAsync<DictionaryTables>("/projects/dictionary", new { tables = tables.Select(t => new { name = t.Name, source = t.Source }), descriptions });
}
