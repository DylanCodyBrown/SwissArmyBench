namespace SwissArmyBench.Web.Api.Variables;

/// <summary>This computer's variables by name (routes_variables.py), for the `${` lists.</summary>
public sealed class VariablesClient
{
    private readonly ApiClient _api;

    public VariablesClient(ApiClient api)
    {
        _api = api;
    }

    public async Task<IReadOnlyList<OfferedVariable>> OfferedAsync() => (await _api.GetAsync<VariablesOffered>("/variables")).Variables;
}
