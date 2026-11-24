using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Files;
using SwissArmyBench.Web.Api.Projects;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Home;

public partial class Home : IDisposable
{
    private bool _pasting;
    private (double X, double Y)? _importMenu;
    private string? _importing;
    private SyncFolder? _sync;

    private const string CustomSort = "custom";
    private const int TypingPauseMilliseconds = 200;

    /// <summary>The sorts, in the classic Explorer's order and words.</summary>
    private static readonly (string Value, string Label)[] _sorts =
    [
        ("opened", "Last opened"),
        ("name", "Name"),
        ("type", "Type"),
        ("changed", "Last changed"),
        ("created", "Created"),
        (CustomSort, "Custom"),
    ];

    private ExplorerAnswer? _listing;
    private Exception? _error;
    private bool _errorFromLoading;
    private bool _busy;
    private string _query = string.Empty;
    private string _type = string.Empty;
    private string _where = string.Empty;
    private bool _newOpen;
    private ProjectType? _newType;
    private CancellationTokenSource? _typing;

    [Inject]
    private ProjectsClient Projects { get; set; } = default!;

    [Inject]
    private ProjectState Project { get; set; } = default!;

    [Inject]
    private FileChooser Files { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private ApiClient Api { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    protected override async Task OnInitializedAsync()
    {
        await Js.InvokeVoidAsync("sab.setTitle", "Projects");
        Project.Changed += OnProjectChanged;
        _busy = true;
        await LoadAsync();
    }

    private async Task LoadAsync()
    {
        try
        {
            _listing = await Projects.ExplorerAsync(_query, _type, _where);
            // Only the listing's own failure goes when it reads again: an action's refusal stays until closed.
            if (_errorFromLoading)
            {
                _error = null;
                _errorFromLoading = false;
            }
        }
        catch (ApiException error)
        {
            _error = error;
            _errorFromLoading = true;
        }
        _busy = false;
        StateHasChanged();
        await ReadSyncAsync();
    }

    private void Failed(Exception error)
    {
        _error = error;
        StateHasChanged();
    }

    private async Task SearchAsync(ChangeEventArgs e)
    {
        _query = e.Value?.ToString() ?? string.Empty;
        _typing?.Cancel();
        _typing = new CancellationTokenSource();
        try
        {
            await Task.Delay(TypingPauseMilliseconds, _typing.Token);
        }
        catch (TaskCanceledException)
        {
            return; // more typing came: only the last pause loads
        }
        await LoadAsync();
    }

    private Task TypeAsync(ChangeEventArgs e)
    {
        _type = e.Value?.ToString() ?? string.Empty;
        return LoadAsync();
    }

    private Task WhereAsync(ChangeEventArgs e)
    {
        _where = e.Value?.ToString() ?? string.Empty;
        return LoadAsync();
    }

    private async Task SortByAsync(ChangeEventArgs e)
    {
        await GuardAsync(() => Projects.SortAsync(e.Value?.ToString() ?? "opened", _listing?.Sort.Descending ?? true));
        await LoadAsync();
    }

    private async Task FlipSortAsync()
    {
        if (_listing is { } listing)
        {
            await GuardAsync(() => Projects.SortAsync(listing.Sort.By, !listing.Sort.Descending));
            await LoadAsync();
        }
    }

    private async Task ExplainedAsync(bool explained)
    {
        await GuardAsync(() => Projects.ExplainedAsync(explained));
        await LoadAsync();
    }

    private void CreateOfType(ProjectType type)
    {
        _newType = type;
        _newOpen = true;
    }

    private async Task NewDoneAsync(bool made)
    {
        _newOpen = false;
        _newType = null;
        if (made)
        {
            await Project.RefreshAsync();
            await LoadAsync();
        }
    }

    private async Task OpenProjectAsync()
    {
        var path = await Files.ChooseAsync("folder", "Open project", _listing?.Folder, "project");
        if (path is not null)
        {
            await OpenAtAsync(path);
        }
    }

    /// <summary>Open a project's folder; with unsaved work open the server asks first (409), and so does this page.</summary>
    private async Task OpenAtAsync(string path)
    {
        await GuardAsync(() => ProjectAsks.OpenAsync(Dialogs, Project, Projects, path));
        await LoadAsync();
    }

    private async Task CloseProjectAsync()
    {
        await GuardAsync(() => ProjectAsks.CloseAsync(Dialogs, Project, Projects));
        await LoadAsync();
    }

    /// <summary>Open a file as a table (CSV, Parquet, Excel, JSON): it opens on the Tables page.</summary>
    private async Task OpenFileAsync()
    {
        var path = await Files.ChooseAsync("file", "Open a file", null, "table");
        if (path is null)
        {
            return;
        }
        var name = FilePaths.Stem(path);
        await GuardAsync(() => Api.PostAsync<System.Text.Json.JsonElement>($"/datasets/{ApiClient.Part(name)}/load", new { path }));
        if (_error is null)
        {
            Nav.NavigateTo("tables");
        }
    }

    private async Task GuardAsync(Func<Task> work)
    {
        try
        {
            await work();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    // Import… (the classic projectImport.ts, from the Workbench, the Connections layer and the Blades pane there):
    // notebooks, scripts and apps into the open project; connections and blades into this computer's library.
    private void ImportMenu(MouseEventArgs e) => _importMenu = (e.ClientX, e.ClientY + 12);

    private IReadOnlyList<MenuEntry> ImportEntries =>
    [
        new("Notebooks, scripts and apps…", "notebook", () => Importing(ImportDialog.Documents)),
        new("Connections…", "plug", () => Importing(ImportDialog.Connections)),
        new("Blades…", "code", () => Importing(ImportDialog.Blades)),
    ];

    private Task Importing(string kind)
    {
        _importing = kind;
        return Task.CompletedTask;
    }

    private async Task ImportedAsync(Imported? done)
    {
        _importing = null;
        if (done is { Documents.Count: > 0 })
        {
            await LoadAsync();
        }
    }

    // A shared card's sync words and its Pull and Push come from the Git extension when it is on (asked as the
    // cards draw; the server asks GitHub at most once a minute).
    private async Task ReadSyncAsync()
    {
        if (_listing?.Projects.Any(p => p.Where == "shared") != true)
        {
            return;
        }
        try
        {
            _sync = await Projects.SharedSyncAsync();
        }
        catch (ApiException)
        {
            _sync = null;
        }
        StateHasChanged();
    }

    private void OnProjectChanged() => _ = InvokeAsync(LoadAsync);

    public void Dispose()
    {
        Project.Changed -= OnProjectChanged;
        _typing?.Dispose();
        GC.SuppressFinalize(this);
    }
}
