namespace SwissArmyBench.Web.Api.Blades;

/// <summary>
/// The blade IDE and the Blades pane (routes_blades.py): a blade read, saved (its code after its header, with the
/// file's stamp), run, linted, its Properties, Save as and Copy as your own, removed, exported, shown; New blade; the
/// blade folders; import; a starter's snippet filled.
/// </summary>
public sealed class BladesClient
{
    private readonly ApiClient _api;

    public BladesClient(ApiClient api)
    {
        _api = api;
    }

    private static string At(string name) => $"/blades/{ApiClient.Part(name)}";

    public Task<BladeDetail> GetAsync(string name) => _api.GetAsync<BladeDetail>(At(name));

    public Task<BladeHeader> HeaderAsync(string name) => _api.GetAsync<BladeHeader>($"{At(name)}/header");

    public Task<BladeCode> CodeAsync(string name) => _api.GetAsync<BladeCode>($"{At(name)}/code");

    /// <summary>Save: the header's changed fields, the code (none for a secret blade) and the stamp it was read with.</summary>
    public Task<BladeMade> SaveAsync(string name, IReadOnlyDictionary<string, object?> body) => _api.PutAsync<BladeMade>(At(name), body);

    public Task<BladeRun> RunAsync(string name, string code) => _api.PostAsync<BladeRun>($"{At(name)}/run", new { code });

    public Task<BladeProblems> ProblemsAsync(string name, string code) => _api.PostAsync<BladeProblems>($"{At(name)}/problems", new { code });

    public Task OpenResultAsync(string name) => _api.PostAsync($"{At(name)}/result/open");

    public Task<NameCheck> NameCheckAsync(string name) => _api.GetAsync<NameCheck>($"/blades/name-check?name={Uri.EscapeDataString(name)}");

    public Task<NameCheck> TableCheckAsync(string table, string blade) =>
        _api.GetAsync<NameCheck>($"/blades/table-name?name={Uri.EscapeDataString(table)}&blade={Uri.EscapeDataString(blade)}");

    /// <summary>A copy as the user's own (Copy as your own, Save as…): its new name and code when given.</summary>
    public Task<BladeMade> CopyAsync(string name, string? to, string? code) =>
        _api.PostAsync<BladeMade>($"{At(name)}/copy", new Dictionary<string, object?> { ["name"] = to, ["code"] = code }.Where(p => p.Value is not null).ToDictionary());

    public Task RemoveAsync(string name) => _api.DeleteAsync(At(name));

    public Task ShowAsync(string name) => _api.PostAsync($"{At(name)}/show");

    public Task ForgetSecretAsync(string name, string secret) => _api.PutAsync($"{At(name)}/secrets", new Dictionary<string, object?> { [secret] = null });

    public Task PinAsync(string name, bool pinned) => _api.PutAsync($"{At(name)}/pin", new { pinned });

    public Task<BladeChoices> ChoicesAsync() => _api.GetAsync<BladeChoices>("/blades/new");

    public Task<BladeMade> NewAsync(string? name, string? kind, string? template) =>
        _api.PostAsync<BladeMade>("/blades/new", new Dictionary<string, object?> { ["name"] = name, ["kind"] = kind, ["template"] = template }.Where(p => p.Value is not null).ToDictionary());

    public Task<System.Text.Json.JsonElement> FoldersAsync() => _api.GetAsync<System.Text.Json.JsonElement>("/blades/folders");

    public Task<System.Text.Json.JsonElement> SetFoldersAsync(IReadOnlyList<string> folders) => _api.PutAsync<System.Text.Json.JsonElement>("/blades/folders", new { folders });

    public Task<System.Text.Json.JsonElement> ImportAsync(object body) => _api.PostAsync<System.Text.Json.JsonElement>("/blades/import", body);

    public Task<System.Text.Json.JsonElement> SnippetAsync(string name) => _api.GetAsync<System.Text.Json.JsonElement>($"{At(name)}/snippet");

    public Task<System.Text.Json.JsonElement> FillSnippetAsync(string name, IReadOnlyDictionary<string, string> values) =>
        _api.PostAsync<System.Text.Json.JsonElement>($"{At(name)}/snippet", new { values });
}
