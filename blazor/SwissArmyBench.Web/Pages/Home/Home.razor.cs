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

    private const string CustomSort = "custom";
    private const int ConflictStatus = 409;
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
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _busy = false;
        StateHasChanged();
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
        try
        {
            await Projects.OpenAsync(path);
        }
        catch (ApiException error) when (error.Status == ConflictStatus)
        {
            if (!await Dialogs.AskYesNoAsync("Open project", error.Refusal.Error, "Discard and open", danger: true))
            {
                return;
            }
            await GuardAsync(() => Projects.OpenAsync(path, discard: true));
        }
        catch (ApiException error)
        {
            _error = error;
        }
        await Project.RefreshAsync();
        await LoadAsync();
    }

    private async Task CloseProjectAsync()
    {
        try
        {
            await Projects.CloseAsync();
        }
        catch (ApiException error) when (error.Status == ConflictStatus)
        {
            if (await Dialogs.AskYesNoAsync("Close project", error.Refusal.Error, "Close without saving", danger: true))
            {
                await GuardAsync(() => Projects.CloseAsync(discard: true));
            }
        }
        catch (ApiException error)
        {
            _error = error;
        }
        await Project.RefreshAsync();
        await LoadAsync();
    }

    /// <summary>Open a file as a table (CSV, Parquet, Excel, JSON): it opens on the Grids page.</summary>
    private async Task OpenFileAsync()
    {
        var path = await Files.ChooseAsync("file", "Open a file", null, "table");
        if (path is null)
        {
            return;
        }
        var name = Path.GetFileNameWithoutExtension(path.Replace('\\', '/'));
        await GuardAsync(() => Api.PostAsync<System.Text.Json.JsonElement>($"/datasets/{ApiClient.Part(name)}/load", new { path }));
        if (_error is null)
        {
            Nav.NavigateTo("grids");
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

    private void OnProjectChanged() => _ = InvokeAsync(LoadAsync);

    public void Dispose()
    {
        Project.Changed -= OnProjectChanged;
        _typing?.Dispose();
        GC.SuppressFinalize(this);
    }
}
