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

    /// <summary>Write rows with this call: a dry run (nothing sent) or the write.</summary>
    public Task<WriteRowsAnswer> WriteRowsAsync(string name, string operation, IReadOnlyDictionary<string, object?> write) =>
        _api.PostAsync<WriteRowsAnswer>($"/apis/{ApiClient.Part(name)}/calls/{ApiClient.Part(operation)}/write", write);

    /// <summary>The write saved as its web call blade.</summary>
    public Task<SavedBlade> SaveWriteAsync(string name, string operation, IReadOnlyDictionary<string, object?> write) =>
        _api.PutAsync<SavedBlade>($"/apis/{ApiClient.Part(name)}/calls/{ApiClient.Part(operation)}/write", write);

    /// <summary>An API's actions with what was learned of them, and since when its Discover is allowed.</summary>
    public Task<ActionListing> ActionsAsync(string api) => _api.GetAsync<ActionListing>($"/actions?api={ApiClient.Part(api)}");

    public Task<ActionDescribed> DescribeAsync(string api, string action) =>
        _api.GetAsync<ActionDescribed>($"/actions/{ApiClient.Part(api)}/{ApiClient.Part(action)}");

    public Task<ActionRun> RunActionAsync(string api, string action, IReadOnlyDictionary<string, string> inputs) =>
        _api.PostAsync<ActionRun>("/actions/run", new { api, action, inputs });

    /// <summary>Discover: one read-only call per read endpoint (the user's Allow asked once per API).</summary>
    public Task<Discovered> DiscoverAsync(string api) => _api.PostAsync<Discovered>("/actions/discover", new { api });

    /// <summary>Take back Discover's remembered Allow.</summary>
    public Task ForgetDiscoverAsync(string api) => _api.PostAsync("/actions/allow", new { api, allow = false });

    /// <summary>A rename offered once: Use it, or No.</summary>
    public Task OfferAsync(string api, string action, ActionOffer offer, bool take) =>
        _api.PostAsync("/actions/offer", new { api, action, from = offer.From, to = offer.To, take });

    /// <summary>Build: a notebook cell, a script function (into the script named) or a widget on a canvas.</summary>
    public Task<BuiltAction> BuildAsync(IReadOnlyDictionary<string, object?> build) => _api.PostAsync<BuiltAction>("/actions/build", build);

    /// <summary>The open project's scripts (where a built function may go).</summary>
    public Task<ProjectScripts> ScriptsAsync() => _api.GetAsync<ProjectScripts>("/project/documents?kind=script");
}
