namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>The relationship model and the ERD (routes_relationships.py).</summary>
public sealed class RelationshipsClient
{
    private readonly ApiClient _api;

    public RelationshipsClient(ApiClient api)
    {
        _api = api;
    }

    public Task<Model> ModelAsync() => _api.GetAsync<Model>("/relationships");

    /// <summary>The ERD: the tables the open project uses ("project"), or every table ("all").</summary>
    public Task<ErdAnswer> ErdAsync(string scope) => _api.GetAsync<ErdAnswer>($"/relationships/erd?scope={ApiClient.Part(scope)}");

    public Task<FindAnswer> FindAsync(IReadOnlyList<string> tables) => _api.PostAsync<FindAnswer>("/relationships/find", new { tables });

    /// <summary>Joins merged into the current model.</summary>
    public Task AddAsync(IReadOnlyList<Join> joins) => _api.PostAsync("/relationships", new { model = new { relationships = joins } });

    public Task DeleteAsync(IReadOnlyList<Join> joins) => _api.PostAsync("/relationships/delete", new { joins });

    public Task UndoAsync() => _api.PostAsync("/relationships/undo");

    public Task<SetLibrary> LibraryAsync() => _api.GetAsync<SetLibrary>("/relationships/library");

    /// <summary>A saved set merged into the joins in use: what it changed, in words.</summary>
    public async Task<IReadOnlyList<string>> ApplySetAsync(string name) =>
        (await _api.PostAsync<ChangedWords>($"/relationships/library/{ApiClient.Part(name)}")).Changed;

    /// <summary>A set (or, with none named, the joins in use) checked against the open tables.</summary>
    public Task<CheckAnswer> CheckAsync(string? set) => _api.PostAsync<CheckAnswer>("/relationships/check", set is null ? new { } : new { set });

    public Task RenameSetAsync(string name, string to) => _api.PatchAsync<System.Text.Json.JsonElement>($"/relationships/sets/{ApiClient.Part(name)}", new { name = to });

    public Task DeleteSetAsync(string name) => _api.DeleteAsync($"/relationships/sets/{ApiClient.Part(name)}");

    /// <summary>The joins in use saved as a set (folder null: my saved sets): where it went.</summary>
    public Task<SavedWhere> SaveSetAsync(object set) => _api.PostAsync<SavedWhere>("/relationships/sets", set);

    /// <summary>A set's file read for review (apply false), or applied (and kept or shared).</summary>
    public Task<ImportReview> ReviewImportAsync(string text) => _api.PostAsync<ImportReview>("/relationships/import", new { text });

    public Task<SavedWhere> ApplyImportAsync(string text, bool save, string? folder) =>
        _api.PostAsync<SavedWhere>("/relationships/import", new { text, apply = true, save, folder });

    /// <summary>A model as JSON merged into the joins in use.</summary>
    public Task AddModelAsync(System.Text.Json.JsonElement model) => _api.PostAsync("/relationships", new { model });

    public Task AddJoinsAsync(IReadOnlyList<Join> joins, IReadOnlyDictionary<string, IReadOnlyList<string>> keys) =>
        _api.PostAsync("/relationships", new
        {
            model = new
            {
                tables = joins.Where(j => keys.ContainsKey(j.To)).DistinctBy(j => j.To).ToDictionary(j => j.To, j => new { primary_key = keys[j.To] }),
                relationships = joins,
            },
        });

    /// <summary>The kind or the Run switch of some joins changed: how many changed.</summary>
    public async Task<int> UpdateAsync(IReadOnlyList<Join> joins, string? kind, bool? active) =>
        (await _api.PostAsync<ChangedCount>("/relationships/update", new { joins = joins.Select(j => j.Ends), kind, active })).Changed;

    public async Task<int> RemoveAsync(IReadOnlyList<Join> joins) =>
        (await _api.PostAsync<RemovedCount>("/relationships/delete", new { joins = joins.Select(j => j.Ends) })).Removed;

    /// <summary>A suggestion never offered again.</summary>
    public Task RejectAsync(Join join) => _api.PostAsync("/relationships/reject", join.Ends);

    public Task<FindAnswer> FindAllAsync() => _api.PostAsync<FindAnswer>("/relationships/find", new { });

    public Task<RelationshipScope?> ScopeAsync() => _api.GetAsync<RelationshipScope?>("/relationships/scope?scope=project");

    /// <summary>The ERD of the tables named.</summary>
    public Task<ErdAnswer> ErdOfAsync(IReadOnlyList<string> tables) =>
        _api.GetAsync<ErdAnswer>($"/relationships/erd?tables={ApiClient.Part(string.Join(',', tables))}");
}
