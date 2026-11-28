namespace SwissArmyBench.Web.Api.Extensions;

/// <summary>The Extensions page (routes_extensions.py): the cards, and a folder extension's Install (its packages,
/// then Load again), Remove (to the trash), Show its folder and New extension. None restarts the app.</summary>
public sealed class ExtensionsClient
{
    private readonly ApiClient _api;

    public ExtensionsClient(ApiClient api)
    {
        _api = api;
    }

    public Task<ExtensionList> ListAsync() => _api.GetAsync<ExtensionList>("/extensions");

    public Task InstallAsync(string id) => _api.PostAsync("/extensions/install", new { id });

    /// <summary>The cards as the page draws them (a folder extension's path, error and packages; a panel).</summary>
    public Task<ExtensionListing> CardsAsync() => _api.GetAsync<ExtensionListing>("/extensions");

    /// <summary>Remove a folder extension: the server asks first (its question) until confirmed.</summary>
    public Task<ExtensionChange> RemoveAsync(string id, bool confirmed) =>
        _api.PostAsync<ExtensionChange>("/extensions/remove", new { id, confirmed });

    /// <summary>A folder extension's folder shown in the file manager (the user's own).</summary>
    public Task ShowAsync(string id) => _api.PostAsync("/extensions/show", new { id });

    /// <summary>New extension: a folder with one route and one command (and a project type when named).</summary>
    public Task NewAsync(string id, string? name, string? projectType) =>
        _api.PostAsync("/extensions/new", new { id, name, project_type = projectType });
}
