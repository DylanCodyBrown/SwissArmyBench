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

    public Task SortAsync(string by, bool descending) => _api.PostAsync("/projects/sort", new { by, descending });

    /// <summary>A card moved one place left (-1) or right (1) in the custom order.</summary>
    public Task MoveAsync(string path, int by) => _api.PostAsync("/projects/sort", new { move = path, by });

    public Task ExplainedAsync(bool explained) => _api.PostAsync("/projects/explained", new { explained });

    public Task RenameAsync(string path, string name) => _api.PostAsync("/projects/rename", new { path, name });

    public Task RemoveAsync(string path) => _api.PostAsync("/projects/remove", new { path });

    public Task LocateAsync(string path, string to) => _api.PostAsync("/projects/locate", new { path, to });

    public Task ShowAsync(string path) => _api.PostAsync("/projects/show", new { path });

    public Task DeleteAsync(string path, string confirm) => _api.PostAsync("/projects/delete", new { path, confirm });

    public Task ShareAsync(string path) => _api.PostAsync("/projects/share", new { path });

    public Task CopyLocalAsync(string path) => _api.PostAsync("/projects/copy-local", new { path });

    /// <summary>The Local projects folder ("local") or the Shared one ("shared").</summary>
    public Task SetFolderAsync(string which, string folder) => _api.PostAsync("/projects/folder", new { which, folder });

    public Task DefaultFolderAsync() => _api.PostAsync("/projects/folder", new Dictionary<string, object> { ["default"] = true });

    public Task<ProjectAnswer> CurrentAsync() => _api.GetAsync<ProjectAnswer>("/project");

    /// <summary>New project: its name, where (a folder, or "where": "shared"), and its type's own fields (make).</summary>
    public Task<ProjectAnswer> NewAsync(IReadOnlyDictionary<string, object?> body) => _api.PostAsync<ProjectAnswer>("/project/new", body);

    public Task<ProjectAnswer> OpenAsync(string path, bool discard = false) => _api.PostAsync<ProjectAnswer>("/project/open", new { path, discard });

    public Task<ProjectAnswer> SaveAsync() => _api.PostAsync<ProjectAnswer>("/project/save");

    public Task<ProjectAnswer> CloseAsync(bool discard = false) => _api.PostAsync<ProjectAnswer>("/project/close", new { discard });

    public Task<ProjectAnswer> AutosaveAsync(bool on) => _api.PostAsync<ProjectAnswer>("/project/autosave", new { on });
}
