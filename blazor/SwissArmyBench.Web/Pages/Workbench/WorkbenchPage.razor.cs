using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Connections;
using SwissArmyBench.Web.Api.Files;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

public partial class WorkbenchPage
{
    private OpenedNotebook? _notebook;
    private OpenedScript? _script;
    private string _scriptText = string.Empty;
    private string? _path;
    private double? _modified;
    private bool _newDocument;
    private bool _dirty;
    private bool _loading;
    private int _documentKey;
    private CodeTree? _tree;
    private IReadOnlyList<RecentFile> _recent = [];
    private IReadOnlyList<string> _connections = [];
    private bool _showFiles = true;
    private bool _showBlades;
    private (string Words, string Address)? _wrongPage;
    private Exception? _error;
    private NotebookView? _notebookView;
    private ScriptView? _scriptView;
    private string? _shownFor;

    [Inject]
    private WorkbenchClient Workbench { get; set; } = default!;

    [Inject]
    private ConnectionsClient ConnectionsApi { get; set; } = default!;

    [Inject]
    private FileChooser Files { get; set; } = default!;

    [Inject]
    private PythonSession Session { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    /// <summary>notebooks or scripts: the two pages share this component.</summary>
    [Parameter, EditorRequired]
    public string Page { get; set; } = "notebooks";

    [Parameter]
    public string? Path { get; set; }

    [Parameter]
    public bool New { get; set; }

    private bool IsNotebooks => Page == "notebooks";

    private string Kind => IsNotebooks ? "notebook" : "script";

    private string KindWord => IsNotebooks ? "notebook" : "script";

    private bool HasDocument => _notebook is not null || _script is not null || _newDocument;

    private string Title => _path is { } path ? System.IO.Path.GetFileName(path) : _newDocument ? $"Untitled {KindWord}" : IsNotebooks ? "Notebooks" : "Scripts";

    protected override async Task OnInitializedAsync()
    {
        Session.Changed += Redraw;
        _showFiles = await Js.InvokeAsync<string?>("sab.recall", $"{Page}.files") != "0";
        _showBlades = await Js.InvokeAsync<string?>("sab.recall", $"{Page}.blades") == "1";
        await Task.WhenAll(LoadTreeAsync(), LoadConnectionsAsync());
    }

    protected override async Task OnParametersSetAsync()
    {
        var wanted = $"{Path}|{New}";
        if (wanted == _shownFor)
        {
            return;
        }
        _shownFor = wanted;
        _wrongPage = null;
        if (Path is { Length: > 0 } path)
        {
            await OpenPathAsync(path);
        }
        else
        {
            Reset(New);
            _recent = await RecentAsync();
        }
        await Js.InvokeVoidAsync("sab.setTitle", Title);
    }

    private async Task OpenPathAsync(string path)
    {
        var notebook = path.EndsWith(".ipynb", StringComparison.OrdinalIgnoreCase);
        if (notebook != IsNotebooks)
        {
            // A file opens on its kind's page (the classic workbench_pages.py's one line).
            var page = notebook ? "notebooks" : "scripts";
            _wrongPage = ($"{System.IO.Path.GetFileName(path)} is a {(notebook ? "notebook" : "script")}: it opens on the {(notebook ? "Notebooks" : "Scripts")} page.", $"{page}?path={Uri.EscapeDataString(path)}");
            Reset(false);
            return;
        }
        _loading = true;
        try
        {
            Reset(false);
            if (notebook)
            {
                _notebook = await Workbench.OpenNotebookAsync(path);
                (_path, _modified) = (_notebook.Path, _notebook.Modified);
            }
            else
            {
                _script = await Workbench.OpenScriptAsync(path);
                (_path, _modified, _scriptText) = (_script.Path, _script.Modified, _script.Text);
            }
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _loading = false;
    }

    private void Reset(bool newDocument)
    {
        _notebook = null;
        _script = null;
        _scriptText = string.Empty;
        _path = null;
        _modified = null;
        _dirty = false;
        _newDocument = newDocument;
        _documentKey++;
    }

    private async Task<IReadOnlyList<RecentFile>> RecentAsync()
    {
        try
        {
            return (await Workbench.HomeAsync()).Recent;
        }
        catch (ApiException)
        {
            return [];
        }
    }

    private async Task LoadTreeAsync()
    {
        try
        {
            _tree = await Workbench.TreeAsync(Page);
        }
        catch (ApiException)
        {
            _tree = new CodeTree(null, null, []); // the pane says no project is open
        }
    }

    private async Task LoadConnectionsAsync()
    {
        try
        {
            _connections = (await ConnectionsApi.CardsAsync())
                .Select(c => c.Name)
                .OrderBy(n => n, StringComparer.OrdinalIgnoreCase)
                .ToList();
        }
        catch (ApiException)
        {
            _connections = []; // a SQL cell still runs on DuckDB's open tables
        }
    }

    private void MarkDirty() => _dirty = true;

    private void ScriptChanged(string text)
    {
        _dirty = _dirty || text != _scriptText;
        _scriptText = text;
    }

    private Task NewAsync()
    {
        Nav.NavigateTo($"{Page}?new=1");
        return Task.CompletedTask;
    }

    private async Task OpenAsync()
    {
        var home = await Workbench.HomeAsync();
        if (await Files.ChooseAsync("open", $"Open a {KindWord}", home.Folder, Kind) is { } path)
        {
            Nav.NavigateTo($"{(path.EndsWith(".ipynb", StringComparison.OrdinalIgnoreCase) ? "notebooks" : "scripts")}?path={Uri.EscapeDataString(path)}");
        }
    }

    private Task PageKeyAsync(string key) => key == "saveAs" ? SaveAsAsync() : SaveAsync();

    private Task SaveAsync() => _path is null ? SaveAsAsync() : SaveToAsync(_path);

    private async Task SaveAsAsync()
    {
        var home = await Workbench.HomeAsync();
        var start = _path is null ? home.Folder : System.IO.Path.GetDirectoryName(_path);
        if (await Files.ChooseAsync("save", "Save as", start, Kind) is not { } chosen)
        {
            return;
        }
        var extension = IsNotebooks ? ".ipynb" : ".py";
        await SaveToAsync(chosen.EndsWith(extension, StringComparison.OrdinalIgnoreCase) ? chosen : chosen + extension);
    }

    private async Task SaveToAsync(string path)
    {
        try
        {
            var renamed = path != _path;
            SavedDocument saved;
            if (_notebookView is not null)
            {
                var (cells, next) = _notebookView.ToSave();
                saved = await Workbench.SaveNotebookAsync(path, cells, next, renamed ? null : _modified);
            }
            else
            {
                saved = await Workbench.SaveScriptAsync(path, _scriptText, renamed ? null : _modified);
            }
            (_path, _modified, _dirty, _newDocument) = (saved.Path, saved.Modified, false, false);
            _error = null;
            _ = Notes.SayAsync($"Saved {System.IO.Path.GetFileName(saved.Path)}.");
            if (renamed)
            {
                _shownFor = $"{saved.Path}|False"; // the address follows without opening the file again
                Nav.NavigateTo($"{Page}?path={Uri.EscapeDataString(saved.Path)}", replace: true);
            }
            await LoadTreeAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private Task InsertAsync(string line) =>
        _notebookView?.InsertAsync(line) ?? _scriptView?.InsertAsync(line) ?? Task.CompletedTask;

    private Task InterruptAsync() => ActAsync(Session.InterruptAsync);

    private Task RestartAsync() => ActAsync(Session.RestartAsync);

    private async Task ActAsync(Func<Task> action)
    {
        try
        {
            await action();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task ToggleFilesAsync()
    {
        _showFiles = !_showFiles;
        await Js.InvokeVoidAsync("sab.remember", $"{Page}.files", _showFiles ? "1" : "0");
    }

    private async Task ToggleBladesAsync()
    {
        _showBlades = !_showBlades;
        await Js.InvokeVoidAsync("sab.remember", $"{Page}.blades", _showBlades ? "1" : "0");
    }

    private void Redraw() => _ = InvokeAsync(StateHasChanged);

    public void Dispose() => Session.Changed -= Redraw;
}
