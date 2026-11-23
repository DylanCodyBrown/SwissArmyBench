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
}
