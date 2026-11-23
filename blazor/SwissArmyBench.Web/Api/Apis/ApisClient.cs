using System.Text.Json;

namespace SwissArmyBench.Web.Api.Apis;

/// <summary>The APIs page (routes_api_explorer.py): the library's APIs as cards, one API's operations and schemas,
/// and Try it (a call sent, its answer opened in Structures).</summary>
public sealed class ApisClient
{
    private readonly ApiClient _api;

    public ApisClient(ApiClient api)
    {
        _api = api;
    }

    public Task<ApiCards> CardsAsync() => _api.GetAsync<ApiCards>("/apis");

    public Task<ApiExplorer> ExploreAsync(string name) => _api.GetAsync<ApiExplorer>($"/apis/{ApiClient.Part(name)}");

    /// <summary>Try it: the operation called with its inputs (and a body), the answer opened in Structures.</summary>
    public Task<ApiCallAnswer> CallAsync(string name, string operation, IReadOnlyDictionary<string, string> inputs, JsonElement? body) =>
        _api.PostAsync<ApiCallAnswer>($"/apis/{ApiClient.Part(name)}/calls/{ApiClient.Part(operation)}", new { inputs, body });

    public Task<ApiListing> ListingAsync() => _api.GetAsync<ApiListing>("/apis");

    public Task<ApiHits> SearchAsync(string q) => _api.GetAsync<ApiHits>($"/apis/search?q={ApiClient.Part(q)}");

    public Task<ApiRefreshed> RefreshAsync(string name) => _api.PostAsync<ApiRefreshed>($"/apis/{ApiClient.Part(name)}/refresh", new { });

    public Task ApplyRefreshAsync(string name) => _api.PostAsync($"/apis/{ApiClient.Part(name)}/refresh/apply", new { });

    public Task CheckForChangesAsync(string name, bool on) => _api.PutAsync($"/apis/{ApiClient.Part(name)}/check", new { on });

    public Task<ApiReferences> RenameAsync(string name, string to) => _api.PutAsync<ApiReferences>($"/apis/{ApiClient.Part(name)}/name", new { name = to });

    /// <summary>Delete: asked first (its references), then confirmed.</summary>
    public Task<ApiReferences> DeleteAsync(string name, bool confirm) =>
        _api.PostAsync<ApiReferences>($"/apis/{ApiClient.Part(name)}/delete", confirm ? new { confirm = true } : new { });

    public Task<MadeBlades> MakeIntoBladesAsync(string name, string? specPath) =>
        _api.PostAsync<MadeBlades>($"/apis/{ApiClient.Part(name)}/make-into-blades", specPath is null ? new { } : new { spec_path = specPath });

    public Task<AddApiChoices> ChoicesAsync() => _api.GetAsync<AddApiChoices>("/apis/choices");

    /// <summary>Add API's preview: what it would write, from the form as it is.</summary>
    public Task<AddApiPlan> PreviewAsync(IReadOnlyDictionary<string, object?> form) => _api.PostAsync<AddApiPlan>("/apis/preview", form);

    /// <summary>Try it: an operation's first rows (values typed for its variables), written nowhere.</summary>
    public Task<TriedOperation> TryAsync(IReadOnlyDictionary<string, object?> form) => _api.PostAsync<TriedOperation>("/apis/try", form);

    /// <summary>Add: API_&lt;name&gt;.py and its blades written into the library.</summary>
    public Task<AddApiPlan> AddAsync(IReadOnlyDictionary<string, object?> form) => _api.PostAsync<AddApiPlan>("/apis", form);

    /// <summary>Save as web call: the operation with its inputs (and, Return as table on, where its rows are and
    /// DuckDB's query over them) as a web call blade.</summary>
    public Task<SavedWebCall> SaveCallAsync(string name, string operation, IReadOnlyDictionary<string, object?> call) =>
        _api.PutAsync<SavedWebCall>($"/apis/{ApiClient.Part(name)}/calls/{ApiClient.Part(operation)}", call);
}
