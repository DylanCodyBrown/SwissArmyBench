using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Files;
using SwissArmyBench.Web.Api.Projects;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Home;

public partial class Home : IDisposable
{
    private bool _pasting;
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

    /// <summary>The projects page's view in the address (?view=projects), so Back returns to the summary.</summary>
    public const string ProjectsView = "projects";

    /// <summary>?view=projects: the projects page even with a project open (New project, Open project…).</summary>
    [SupplyParameterFromQuery(Name = "view")]
    public string? View { get; set; }

    /// <summary>The folder open when the projects page showed: another one opened or made there lands on its summary.</summary>
    private string? _openWhenShown;

    private bool ShowsSummary => Project.Current is not null && View != ProjectsView;

    protected override void OnInitialized() => Project.Changed += OnProjectChanged;

    protected override async Task OnParametersSetAsync()
    {
        if (ShowsSummary)
        {
            return; // the summary sets the title and reads its own answer
        }
        _openWhenShown = Project.Current?.Path;
        await Js.InvokeVoidAsync("sab.setTitle", "Projects");
        _busy = _listing is null; // read again each time it shows: the cards may have changed meanwhile
        await LoadAsync();
    }

    private void ToProjects() => Nav.NavigateTo($"./?view={ProjectsView}");

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

    private void OnProjectChanged() => _ = InvokeAsync(ProjectChangedAsync);

    private async Task ProjectChangedAsync()
    {
        if (Project.Current is { } now && View == ProjectsView && now.Path != _openWhenShown)
        {
            Nav.NavigateTo("./"); // opened or made on the projects page: its summary
            return;
        }
        if (ShowsSummary)
        {
            StateHasChanged(); // the summary reads itself
            return;
        }
        _openWhenShown = Project.Current?.Path;
        await Js.InvokeVoidAsync("sab.setTitle", "Projects");
        await LoadAsync();
    }

    public void Dispose()
    {
        Project.Changed -= OnProjectChanged;
        _typing?.Dispose();
        GC.SuppressFinalize(this);
    }
}
