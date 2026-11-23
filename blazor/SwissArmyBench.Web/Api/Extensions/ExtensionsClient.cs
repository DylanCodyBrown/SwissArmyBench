namespace SwissArmyBench.Web.Api.Extensions;

/// <summary>The Extensions page (routes_extensions.py): the cards, Install and Remove (each handed to the update's
/// helper: the app restarts with the change; a development checkout says what to run instead).</summary>
public sealed class ExtensionsClient
{
    private readonly ApiClient _api;

    public ExtensionsClient(ApiClient api)
    {
        _api = api;
    }

    public Task<ExtensionList> ListAsync() => _api.GetAsync<ExtensionList>("/extensions");

    public Task InstallAsync(string id) => _api.PostAsync("/extensions/install", new { id });

    /// <summary>Remove, asked first: the page asks, then sends confirmed.</summary>
    public Task RemoveAsync(string id) => _api.PostAsync("/extensions/remove", new { id, confirmed = true });

    /// <summary>The cards as the page draws them (a folder extension's path, error and packages; a panel).</summary>
    public Task<ExtensionListing> CardsAsync() => _api.GetAsync<ExtensionListing>("/extensions");

    /// <summary>Install or remove: the server asks first (its question) when it would, else the change starts.</summary>
    public Task<ExtensionChange> ChangeAsync(string action, string id, bool confirmed) =>
        _api.PostAsync<ExtensionChange>($"/extensions/{action}", new { id, confirmed });

    /// <summary>A folder extension's folder shown in the file manager (the user's own).</summary>
    public Task ShowAsync(string id) => _api.PostAsync("/extensions/show", new { id });

    /// <summary>New extension: a folder with one route and one command (and a project type when named).</summary>
    public Task NewAsync(string id, string? name, string? projectType) =>
        _api.PostAsync("/extensions/new", new { id, name, project_type = projectType });

    /// <summary>Whether the server answers (an extension's install restarts it): its status code, 0 for none.</summary>
    public async Task<int> HealthAsync()
    {
        try
        {
            await _api.GetTextAsync("/health");
            return 200;
        }
        catch (ApiException error)
        {
            return error.Status;
        }
        catch (HttpRequestException)
        {
            return 0;
        }
    }
}
