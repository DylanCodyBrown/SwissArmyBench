using System.Text.Json;

namespace SwissArmyBench.Web.Api.Environment;

/// <summary>The Environment (routes_environment.py): everything the project holds, where each is used, its
/// libraries.</summary>
public sealed class EnvironmentClient
{
    private readonly ApiClient _api;

    public EnvironmentClient(ApiClient api)
    {
        _api = api;
    }

    public Task<EnvironmentAnswer> ListingAsync(string search) =>
        _api.GetAsync<EnvironmentAnswer>($"/environment{(search.Length == 0 ? string.Empty : $"?search={ApiClient.Part(search)}")}");

    /// <summary>Where a row opens (a table: a grid, its view).</summary>
    public Task<JsonElement> OpenAsync(string kind, string name) => _api.PostAsync<JsonElement>("/environment/open", new { kind, name });

    public Task<JsonElement> RenameAsync(string kind, string name, string to) => _api.PostAsync<JsonElement>("/environment/rename", new { kind, name, to });

    public Task<JsonElement> RemoveAsync(string kind, string name) => _api.PostAsync<JsonElement>("/environment/remove", new { kind, name });

    /// <summary>The libraries again, the package index asked for newer versions (only when the user asks).</summary>
    public Task<JsonElement> CheckLibrariesAsync() => _api.GetAsync<JsonElement>("/environment/libraries?check=1");

    public Task<JsonElement> PinAsync(string name, bool pinned) => _api.PostAsync<JsonElement>("/environment/libraries/pin", new { name, pinned });

    public Task<JsonElement> UpdateAsync(string name) => _api.PostAsync<JsonElement>("/environment/libraries/update", new { name });

    public Task<JsonElement> InstallAsync(string name) => _api.PostAsync<JsonElement>("/environment/libraries/install", new { name });
}
