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

    /// <summary>A row removed (a table: also deleted in Python on the tick).</summary>
    public Task RemoveAsync(string kind, string name, bool python = false) => _api.PostAsync("/environment/remove", new { kind, name, python });

    /// <summary>A table kept with the project (its rows saved on the user's tick), or no longer.</summary>
    public Task KeepAsync(string name, bool keep) => _api.PostAsync("/environment/keep", new { name, keep });

    /// <summary>What Clear… would take (a dry run), each tick's words.</summary>
    public Task<ClearChoices> ClearPlanAsync() => _api.PostAsync<ClearChoices>("/environment/clear", new { dry_run = true });

    /// <summary>The ticked kinds cleared (what is kept stays).</summary>
    public Task ClearAsync(IReadOnlyDictionary<string, bool> ticks) => _api.PostAsync("/environment/clear", ticks);

    /// <summary>A row as code (an import, a setting's reference, a table's read).</summary>
    public Task<InsertedCode> InsertAsync(string kind, string name) => _api.PostAsync<InsertedCode>("/environment/insert", new { kind, name });

    /// <summary>A table's columns with their ranges and blanks.</summary>
    public async Task<IReadOnlyList<IReadOnlyList<string>>> ColumnsAsync(string name) =>
        (await _api.GetAsync<TableColumns>($"/environment/columns?name={ApiClient.Part(name)}")).Columns;

    /// <summary>A setting's value, shown on the user's click (refused for the agent).</summary>
    public async Task<string> RevealAsync(string name) => (await _api.PostAsync<RevealedValue>("/variables/reveal", new { name })).Value;

    /// <summary>The project's own Python made now (its .venv).</summary>
    public Task MakePythonAsync() => _api.PostAsync("/environment/python", new { make = true });

    /// <summary>A notebook's older environment answered: its libraries added, or left.</summary>
    public Task AnswerOfferAsync(string document, bool add) => _api.PostAsync("/environment/python", new { offer = document, add });

    /// <summary>Every library not pinned updated to its newest version.</summary>
    public Task UpdateAllAsync() => _api.PostAsync("/environment/libraries/update", new { all = true });

    /// <summary>The key vaults (GET /connections' vaults): each its name, kind and the variables it gives.</summary>
    public async Task<IReadOnlyList<KeyVault>> VaultsAsync() =>
        (await _api.GetAsync<KeyVaults>("/connections")).Connections.Where(c => c.Connection == "vault").ToList();

    /// <summary>A row sent to the agent's inbox (its words, never a value).</summary>
    public Task SendToAgentAsync(string title, string text) => _api.PostAsync("/agent/inbox", new { kind = "code", title, text, note = string.Empty });

    /// <summary>A vault's names read again.</summary>
    public Task ReadVaultAsync(string name) => _api.PostAsync("/connections/vaults/secrets", new { name });

    /// <summary>The libraries again, the package index asked for newer versions (only when the user asks).</summary>
    public Task CheckLibrariesAsync() => _api.GetTextAsync("/environment/libraries?check=1");

    public Task PinAsync(string name, bool pinned) => _api.PostAsync("/environment/libraries/pin", new { name, pinned });

    public Task UpdateAsync(string name) => _api.PostAsync("/environment/libraries/update", new { name });

    /// <summary>A variable of this computer added or changed (PUT /variables): a plain value (shareable, or this
    /// computer only) or a secret kept in the keyring.</summary>
    public Task SetVariableAsync(string name, string value, bool secret, bool local) =>
        secret
            ? _api.PutAsync("/variables", new { name, value, from = "keyring" })
            : _api.PutAsync("/variables", new { name, value, from = "value", local });

    public Task InstallAsync(string name) => _api.PostAsync("/environment/libraries/install", new { name });
}
