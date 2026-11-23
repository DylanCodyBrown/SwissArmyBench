using System.Text.Json;

namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>
/// The Workbench (routes_workbench.py, routes_table_cells.py, routes_script_ide.py, routes_blades.py): documents
/// opened and saved, the kernel a document runs in and its runs (the outputs as they arrive), the Tables group,
/// the Files pane's tree and the Blades pane's list.
/// </summary>
public sealed class WorkbenchClient
{
    private readonly ApiClient _api;

    public WorkbenchClient(ApiClient api)
    {
        _api = api;
    }

    /// <summary>The last closed table opened again (404: none to reopen).</summary>
    public Task ReopenTableAsync() => _api.PostAsync("/grids/reopen");

    /// <summary>Open a file as a table (its name from the file's).</summary>
    public Task LoadFileAsync(string name, string path) => _api.PostAsync($"/datasets/{ApiClient.Part(name)}/load", new { path });

    public Task<WorkbenchHome> HomeAsync() => _api.GetAsync<WorkbenchHome>("/workbench/home");

    public Task<OpenedNotebook> OpenNotebookAsync(string path) => _api.PostAsync<OpenedNotebook>("/workbench/open", new { path });

    public Task<OpenedScript> OpenScriptAsync(string path) => _api.PostAsync<OpenedScript>("/workbench/open", new { path });

    /// <summary>A notebook's cells saved; `modified` is the file's time when opened (a newer file on disk is refused
    /// unless forced).</summary>
    public Task<SavedDocument> SaveNotebookAsync(string path, IReadOnlyList<NotebookCell> cells, int nextCell, double? modified, bool force = false) =>
        _api.PostAsync<SavedDocument>("/workbench/save", new { path, cells, next_cell = nextCell, modified, force });

    public Task<SavedDocument> SaveScriptAsync(string path, string text, double? modified, bool force = false) =>
        _api.PostAsync<SavedDocument>("/workbench/save", new { path, text, modified, force });

    /// <summary>The kernel a document runs in: the open project's one Python session for its documents, else one of
    /// its own (in the folder the document is in).</summary>
    public Task<StartedKernel> StartAsync(string? path, string? python = null) =>
        _api.PostAsync<StartedKernel>("/workbench/kernels", new { path, python, window = ApiClient.ClientId });

    /// <summary>A run's outputs as they arrive (nbformat's records, an input request, the error taken apart), then
    /// {"done": ...}.</summary>
    public IAsyncEnumerable<JsonElement> RunAsync(string kernel, RunRequest run, CancellationToken cancel = default) =>
        _api.PostLinesAsync($"/workbench/kernels/{ApiClient.Part(kernel)}/execute", run, cancel);

    public Task AnswerInputAsync(string kernel, string value) => _api.PostAsync($"/workbench/kernels/{ApiClient.Part(kernel)}/input", new { value });

    public Task InterruptAsync(string kernel) => _api.PostAsync($"/workbench/kernels/{ApiClient.Part(kernel)}/interrupt");

    public Task StopAsync(string kernel) => _api.DeleteAsync($"/workbench/kernels/{ApiClient.Part(kernel)}");

    public Task RestartAsync(string kernel) => _api.PostAsync($"/workbench/kernels/{ApiClient.Part(kernel)}/restart");

    /// <summary>An HTML cell's design: its names filled from its run's values (each as the kernel gave it).</summary>
    public Task<FilledHtml> FillHtmlAsync(string html, JsonElement values) => _api.PostAsync<FilledHtml>("/workbench/html/fill", new { html, values });

    /// <summary>A notebook's run order and Outline, from its cells as they are on screen.</summary>
    public Task<NotebookFlow> FlowAsync(IReadOnlyList<NotebookCell> cells) => _api.PostAsync<NotebookFlow>("/workbench/notebook/flow", new { cells });

    public Task<TableList> TablesAsync() => _api.GetAsync<TableList>("/workbench/tables");

    /// <summary>The notebook as it should be with its Tables group (the server's rules: domain/table_cells.py).</summary>
    public Task<ArrangedNotebook> ArrangeAsync(IReadOnlyList<NotebookCell> cells, IReadOnlyList<string> tables, int nextCell) =>
        _api.PostAsync<ArrangedNotebook>("/workbench/tables/arrange", new { kind = "notebook", cells, tables, next_cell = nextCell, move = true });

    /// <summary>The Files pane: the Scripts page's tree (the project's code, the library's, Generated) or the
    /// Notebooks page's.</summary>
    public Task<CodeTree> TreeAsync(string page) => _api.GetAsync<CodeTree>(page == "scripts" ? "/scripts/tree" : $"/project/tree?page={ApiClient.Part(page)}");

    public Task<BladeList> BladesAsync() => _api.GetAsync<BladeList>("/blades");

    public Task<StarterPack> StartersAsync() => _api.GetAsync<StarterPack>("/blades/starters");
}
