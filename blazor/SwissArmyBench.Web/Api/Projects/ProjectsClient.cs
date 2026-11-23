using System.Text.Json;

namespace SwissArmyBench.Web.Api.Projects;

/// <summary>Projects: the Project Explorer (routes_project_explorer.py) and the open project (routes_sab_projects.py).</summary>
public sealed class ProjectsClient
{
    private readonly ApiClient _api;

    public ProjectsClient(ApiClient api)
    {
        _api = api;
    }

    public Task<ExplorerAnswer> ExplorerAsync(string query, string type, string where)
    {
        var address = $"/projects/explorer?q={ApiClient.Part(query)}&type={ApiClient.Part(type)}&where={ApiClient.Part(where)}";
        return _api.GetAsync<ExplorerAnswer>(address);
    }

    public Task<JsonElement> SortAsync(string by, bool descending) => _api.PostAsync<JsonElement>("/projects/sort", new { by, descending });

    /// <summary>A card moved one place left (-1) or right (1) in the custom order.</summary>
    public Task<JsonElement> MoveAsync(string path, int by) => _api.PostAsync<JsonElement>("/projects/sort", new { move = path, by });

    public Task<JsonElement> ExplainedAsync(bool explained) => _api.PostAsync<JsonElement>("/projects/explained", new { explained });

    public Task<JsonElement> RenameAsync(string path, string name) => _api.PostAsync<JsonElement>("/projects/rename", new { path, name });

    public Task<JsonElement> RemoveAsync(string path) => _api.PostAsync<JsonElement>("/projects/remove", new { path });

    public Task<JsonElement> ShowAsync(string path) => _api.PostAsync<JsonElement>("/projects/show", new { path });

    public Task<JsonElement> DeleteAsync(string path, string confirm) => _api.PostAsync<JsonElement>("/projects/delete", new { path, confirm });

    public Task<JsonElement> ShareAsync(string path) => _api.PostAsync<JsonElement>("/projects/share", new { path });

    public Task<JsonElement> CopyLocalAsync(string path) => _api.PostAsync<JsonElement>("/projects/copy-local", new { path });

    /// <summary>The Local projects folder ("local") or the Shared one ("shared").</summary>
    public Task<JsonElement> SetFolderAsync(string which, string folder) => _api.PostAsync<JsonElement>("/projects/folder", new { which, folder });

    public Task<JsonElement> DefaultFolderAsync() => _api.PostAsync<JsonElement>("/projects/folder", new Dictionary<string, object> { ["default"] = true });

    public Task<ProjectAnswer> CurrentAsync() => _api.GetAsync<ProjectAnswer>("/project");

    public Task<ProjectAnswer> NewAsync(string name, string type, string? folder) =>
        _api.PostAsync<ProjectAnswer>("/project/new", new { name, type, folder });

    public Task<ProjectAnswer> OpenAsync(string path, bool discard = false) => _api.PostAsync<ProjectAnswer>("/project/open", new { path, discard });

    public Task<ProjectAnswer> SaveAsync() => _api.PostAsync<ProjectAnswer>("/project/save");

    public Task<ProjectAnswer> CloseAsync(bool discard = false) => _api.PostAsync<ProjectAnswer>("/project/close", new { discard });

    public Task<ProjectAnswer> AutosaveAsync(bool on) => _api.PostAsync<ProjectAnswer>("/project/autosave", new { on });
}
