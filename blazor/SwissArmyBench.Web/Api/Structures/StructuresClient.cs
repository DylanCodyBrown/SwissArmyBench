using System.Text.Json;

using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Api.Structures;

/// <summary>Structures (routes_structures.py): the open ones and the project's files, one structure's value and
/// text, New, Open a file, Paste, the text changed, Save, Open as table, Close.</summary>
public sealed class StructuresClient
{
    private readonly ApiClient _api;

    public StructuresClient(ApiClient api)
    {
        _api = api;
    }

    public Task<StructureList> ListAsync() => _api.GetAsync<StructureList>("/structures");

    public Task<StructureDocument> GetAsync(string id) => _api.GetAsync<StructureDocument>($"/structures/{ApiClient.Part(id)}");

    public Task<StructureDocument> NewAsync(string name) => _api.PostAsync<StructureDocument>("/structures", new { kind = "object", name });

    public Task<StructureDocument> OpenAsync(string path) => _api.PostAsync<StructureDocument>("/structures/open", new { path });

    public Task<StructureDocument> PasteAsync(string text) => _api.PostAsync<StructureDocument>("/structures/paste", new { text });

    /// <summary>The text as typed (kept when it does not parse: read the structure again for its TextError).</summary>
    public Task SetTextAsync(string id, string text) => _api.PutAsync<StructureDocument>($"/structures/{ApiClient.Part(id)}", new { text });

    /// <summary>To its file: never over a file changed on disk since (its hash).</summary>
    public Task SaveAsync(string id, string text, string? hash) => _api.PostAsync($"/structures/{ApiClient.Part(id)}/save", new { text, hash });

    /// <summary>A list of records at a path, as a table of its own.</summary>
    public Task<MadeTable> GridAsync(string id, string path) => _api.PostAsync<MadeTable>($"/structures/{ApiClient.Part(id)}/grid", new { path });

    /// <summary>The open structures (the tabs) and the project's files, as the Structures page reads them.</summary>
    public Task<StructureTabs> TabsAsync() => _api.GetAsync<StructureTabs>("/structures");

    public Task<StructureShown> ShownAsync(string id) => _api.GetAsync<StructureShown>($"/structures/{ApiClient.Part(id)}");

    public Task<StructureShown> OpenShownAsync(string path) => _api.PostAsync<StructureShown>("/structures/open", new { path });

    /// <summary>Pasted text, its format found (none named) and its name.</summary>
    public Task<StructureShown> PasteAsync(string text, string? format, string name) =>
        _api.PostAsync<StructureShown>("/structures/paste", new { text, format, name });

    /// <summary>One step (pick, filter, sort, flatten, add, rename, set, remove) on a structure.</summary>
    public Task<StructureShown> StepAsync(string id, IReadOnlyDictionary<string, object?> step) =>
        _api.PostAsync<StructureShown>($"/structures/{ApiClient.Part(id)}/steps", step);

    /// <summary>An action on a structure (/undo, /redo, /steps/remove, /run-again, /save, /grid): it answers again.</summary>
    public Task<JsonElement> ActAsync(string id, string path, object body) => _api.PostAsync<JsonElement>($"/structures/{ApiClient.Part(id)}{path}", body);

    /// <summary>Its format, or its text as typed (the text view, with no steps).</summary>
    public Task<StructureShown> ChangeAsync(string id, object body) => _api.PutAsync<StructureShown>($"/structures/{ApiClient.Part(id)}", body);

    public Task<SavedAs> SaveAsAsync(string id, string name, string format) =>
        _api.PostAsync<SavedAs>($"/structures/{ApiClient.Part(id)}/save-as", new { name, format });

    public Task<StructureLineage> LineageAsync(string id) => _api.GetAsync<StructureLineage>($"/structures/{ApiClient.Part(id)}/lineage");

    /// <summary>How many places name a structure file.</summary>
    public async Task<int> ReferencesAsync(string name) =>
        (await _api.GetAsync<JsonElement>($"/structures/references?name={ApiClient.Part(name)}")).GetProperty("references").GetArrayLength();

    /// <summary>An API's answer at a path made its web call's table (Return as table), or its DuckDB query saved.</summary>
    public Task<ReturnedAsTable> AsTableAsync(string api, string operation, object body) =>
        _api.PutAsync<ReturnedAsTable>($"/apis/{ApiClient.Part(api)}/calls/{ApiClient.Part(operation)}", body);

    public Task CloseAsync(string id) => _api.DeleteAsync<ClosedStructure>($"/structures/{ApiClient.Part(id)}");
}
