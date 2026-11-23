using System.Text.Json;

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
    public Task<JsonElement> AddAsync(IReadOnlyList<Join> joins) => _api.PostAsync<JsonElement>("/relationships", new { model = new { relationships = joins } });

    public Task<JsonElement> DeleteAsync(IReadOnlyList<Join> joins) => _api.PostAsync<JsonElement>("/relationships/delete", new { joins });

    public Task<JsonElement> UndoAsync() => _api.PostAsync<JsonElement>("/relationships/undo");
}
