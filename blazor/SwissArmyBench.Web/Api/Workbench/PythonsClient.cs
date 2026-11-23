using System.Text.Json;

namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A document's Python (routes_workbench.py, routes_environment.py): the Pythons a loose document may run in,
/// New environment (its offer, and its making streamed a line at a time), the Python remembered for a document, and the
/// open project's own Python (Make it now, an older environment's libraries added or not).</summary>
public sealed class PythonsClient
{
    private readonly ApiClient _api;

    public PythonsClient(ApiClient api)
    {
        _api = api;
    }

    public Task<PythonChoices> PythonsAsync() => _api.GetAsync<PythonChoices>("/workbench/pythons");

    public Task<EnvironmentOffer> OfferAsync() => _api.GetAsync<EnvironmentOffer>("/workbench/environments");

    /// <summary>Make one: {"line"} as each step prints, the last {"done": {ok, python, error}}.</summary>
    public IAsyncEnumerable<JsonElement> MakeAsync(string folder, string? python, IReadOnlyList<string> packages, string? document, CancellationToken cancel = default) =>
        _api.PostLinesAsync("/workbench/environments", new { folder, python, packages, document }, cancel);

    public Task RememberAsync(string path, string python) => _api.PostAsync("/workbench/environment", new { path, python });

    public Task<ProjectPythonState> ProjectAsync() => _api.GetAsync<ProjectPythonState>("/environment/python");

    /// <summary>Make it now (or Try again): the project's .venv made.</summary>
    public Task<ProjectPythonState> MakeProjectAsync() => _api.PostAsync<ProjectPythonState>("/environment/python", new { make = true });

    /// <summary>An older environment's libraries added to the project's Python (or left: Not now).</summary>
    public Task<ProjectPythonState> AnswerOfferAsync(string document, bool add) => _api.PostAsync<ProjectPythonState>("/environment/python", new { offer = document, add });
}
