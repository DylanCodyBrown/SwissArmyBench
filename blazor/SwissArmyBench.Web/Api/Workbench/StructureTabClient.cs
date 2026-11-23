namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A structure's tab beside the code (the classic structureDoc.ts's routes): open its file, the text kept as
/// typed (its parse the realtime linter), the tree's edits on the file, Format, the steps that make a view of it,
/// Open as grid, Save and Save as, and its file changed on disk (Reload, Keep mine).</summary>
public sealed class StructureTabClient
{
    private readonly ApiClient _api;

    public StructureTabClient(ApiClient api)
    {
        _api = api;
    }

    private static string Of(string id) => $"/structures/{ApiClient.Part(id)}";

    public Task<StructureTab> OpenAsync(string path) => _api.PostAsync<StructureTab>("/structures/open", new { path, view = "file" });

    /// <summary>The structure as the file (view file) or through its steps (view result).</summary>
    public Task<StructureTab> GetAsync(string id, bool result) => _api.GetAsync<StructureTab>($"{Of(id)}?view={(result ? "result" : "file")}");

    public Task<StructureTab> SetTextAsync(string id, string text, bool result) => _api.PutAsync<StructureTab>(Of(id), new { text, view = result ? "result" : "file" });

    /// <summary>A tree's edit on the file (set, rename, remove, add, duplicate, move): its text written again.</summary>
    public Task<StructureTab> EditAsync(string id, Dictionary<string, object?> body)
    {
        body["view"] = "file";
        return _api.PostAsync<StructureTab>($"{Of(id)}/edit", body);
    }

    public Task<StructureTab> FormatAsync(string id) => _api.PostAsync<StructureTab>($"{Of(id)}/format", new { view = "file" });

    public Task<StructureTab> ReloadAsync(string id) => _api.PostAsync<StructureTab>($"{Of(id)}/reload", new { });

    public Task<StructureTab> KeepMineAsync(string id) => _api.PostAsync<StructureTab>($"{Of(id)}/keep-mine", new { });

    public Task<StructureTab> AddStepAsync(string id, Dictionary<string, object?> step) => _api.PostAsync<StructureTab>($"{Of(id)}/steps", step);

    public Task<StructureTab> RemoveStepAsync(string id, int index) => _api.PostAsync<StructureTab>($"{Of(id)}/steps/remove", new { index });

    public Task<StructureGrid> GridAsync(string id, string path) => _api.PostAsync<StructureGrid>($"{Of(id)}/grid", new { path });

    /// <summary>Save: the text written only when its bytes change; never over a file changed on disk since (409).</summary>
    public Task<StructureTab> SaveAsync(string id, string text, string? hash) => _api.PostAsync<StructureTab>($"{Of(id)}/save", new { text, hash });

    public Task<StructureTab> SaveAsAsync(string id, string path) => _api.PostAsync<StructureTab>($"{Of(id)}/save-as", new { path, as_text = true });
}
