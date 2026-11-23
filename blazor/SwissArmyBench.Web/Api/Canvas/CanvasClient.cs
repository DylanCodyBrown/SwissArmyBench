namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>The Canvas (the Streamlit extension's routes_canvases.py and routes_launch.py): the project's canvases,
/// one canvas's state, its versioned commands, Undo and Redo, Play, Launch, Stop, Export and the builds.</summary>
public sealed class CanvasClient
{
    private readonly ApiClient _api;

    public CanvasClient(ApiClient api)
    {
        _api = api;
    }

    public Task<CanvasListing> ListAsync() => _api.GetAsync<CanvasListing>("/streamlit/canvases");

    /// <summary>A canvas file opened (validated: a broken one opens read-only with its line).</summary>
    public Task<CanvasState> OpenAsync(string path) => _api.PostAsync<CanvasState>("/streamlit/canvases", new { path });

    /// <summary>A new canvas in the project's folder.</summary>
    public Task<CanvasState> NewAsync(string name, string folder) => _api.PostAsync<CanvasState>("/streamlit/canvases", new { name, folder });

    public Task<CanvasState> StateAsync(string canvas) => _api.GetAsync<CanvasState>(Base(canvas));

    /// <summary>One change, made on the version the page holds (another window's change refuses it with 409).</summary>
    public Task<CanvasState> CommandAsync(string canvas, IReadOnlyDictionary<string, object?> body) =>
        _api.PostAsync<CanvasState>($"{Base(canvas)}/command", body);

    public Task<CanvasState> UndoAsync(string canvas, bool redo, string window) =>
        _api.PostAsync<CanvasState>($"{Base(canvas)}/{(redo ? "redo" : "undo")}", new { window });

    public Task<RunAnswer> PlayAsync(string canvas, string page) => _api.PostAsync<RunAnswer>($"{Base(canvas)}/play", new { page });

    /// <summary>Stop the page playing, or (run "launch") the launched app.</summary>
    public Task StopAsync(string canvas, string? run = null) =>
        _api.PostAsync($"{Base(canvas)}/stop", run is null ? new Dictionary<string, object>() : new { run });

    public Task<RunAnswer> LaunchAsync(string canvas, bool analyzer) =>
        _api.PostAsync<RunAnswer>($"{Base(canvas)}/launch", analyzer ? new { analyzer = true } : new Dictionary<string, object>());

    public Task<ExportAnswer> ExportAsync(string canvas, string folder) => _api.PostAsync<ExportAnswer>($"{Base(canvas)}/export", new { folder });

    public Task<BuildList> BuildsAsync(string canvas) => _api.GetAsync<BuildList>($"{Base(canvas)}/builds");

    /// <summary>Two builds compared, or one (b null) against the canvas as it is now.</summary>
    public Task<BuildCompare> CompareAsync(string canvas, int a, int? b) =>
        _api.GetAsync<BuildCompare>($"{Base(canvas)}/builds/compare?a={a}{(b is { } other ? $"&b={other}" : string.Empty)}");

    public Task<BuildFiles> BuildAsync(string canvas, int number) => _api.GetAsync<BuildFiles>($"{Base(canvas)}/builds/{number}");

    public Task<RunAnswer> RelaunchAsync(string canvas, int number) => _api.PostAsync<RunAnswer>($"{Base(canvas)}/builds/{number}/launch");

    /// <summary>A build's canvas back (one change: Undo takes it back).</summary>
    public Task<CanvasState> RestoreAsync(string canvas, int number) => _api.PostAsync<CanvasState>($"{Base(canvas)}/builds/{number}/restore");

    /// <summary>The Performance Analyzer's session for the canvas's launch.</summary>
    public Task<PerfSession> PerfAsync(string canvas) => _api.GetAsync<PerfSession>($"{Base(canvas)}/perf");

    /// <summary>Attach (recording), Pause or Record (on), and Clear (clear).</summary>
    public Task PerfAttachAsync(string canvas, bool? on = null, bool clear = false)
    {
        var body = new Dictionary<string, object>();
        if (on is { } recording)
        {
            body["on"] = recording;
        }
        if (clear)
        {
            body["clear"] = true;
        }
        return _api.PostAsync($"{Base(canvas)}/perf", body);
    }

    /// <summary>The window closed: nothing more is recorded.</summary>
    public Task PerfDetachAsync(string canvas) => _api.DeleteAsync($"{Base(canvas)}/perf");

    public Task<SavedFile> PerfSaveAsync(string canvas) => _api.PostAsync<SavedFile>($"{Base(canvas)}/perf/save");

    public Task<PerfSession> SavedPerfAsync(string canvas, int build, string file) =>
        _api.GetAsync<PerfSession>($"{Base(canvas)}/builds/{build}/perf/{ApiClient.Part(file)}");

    private static string Base(string canvas) => $"/streamlit/canvases/{ApiClient.Part(canvas)}";
}
