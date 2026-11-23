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
}
