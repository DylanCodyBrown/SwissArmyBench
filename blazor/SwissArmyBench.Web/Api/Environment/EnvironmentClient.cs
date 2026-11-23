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
    public Task<EnvironmentOpened> OpenAsync(string kind, string name) => _api.PostAsync<EnvironmentOpened>("/environment/open", new { kind, name });

    public Task RenameAsync(string kind, string name, string to) => _api.PostAsync("/environment/rename", new { kind, name, to });

    public Task RemoveAsync(string kind, string name) => _api.PostAsync("/environment/remove", new { kind, name });

    /// <summary>The libraries again, the package index asked for newer versions (only when the user asks).</summary>
    public Task CheckLibrariesAsync() => _api.GetTextAsync("/environment/libraries?check=1");

    public Task PinAsync(string name, bool pinned) => _api.PostAsync("/environment/libraries/pin", new { name, pinned });

    public Task UpdateAsync(string name) => _api.PostAsync("/environment/libraries/update", new { name });

    public Task InstallAsync(string name) => _api.PostAsync("/environment/libraries/install", new { name });
}
