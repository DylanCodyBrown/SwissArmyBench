using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Api.Structures;

/// <summary>Structures (routes_structures.py): the open ones and the project's files, one structure's value and
/// text, New, Open a file, Paste, the text changed, Save, Open as grid, Close.</summary>
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

    public Task CloseAsync(string id) => _api.DeleteAsync<ClosedStructure>($"/structures/{ApiClient.Part(id)}");
}
