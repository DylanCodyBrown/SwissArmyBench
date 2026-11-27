using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Projects;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Home;

public partial class ProjectSummaryView : IDisposable
{
    /// <summary>The notices after which the summary is read again: the project, its tables, its files, its Python,
    /// its connections and the Session's log.</summary>
    private static readonly HashSet<string> _followed =
    [
        "project_changed", "project_opened", "project_closed", "project_saved",
        "grid_shown", "grid_closed", "dataset_closed", "dataset_renamed", "dataset_updated",
        "file_changed", "environment_changed", "project_python", "session_entry",
        "connection_colours_changed", "connections_changed",
        // Documents imported into the project, and the scaffold's made files (the Deliverable card's).
        "project_documents_changed", "scaffold_changed",
    ];

    private const int SettleMilliseconds = 300;

    private ProjectSummary? _summary;
    private Exception? _error;
    private CancellationTokenSource? _settling;
    private (double X, double Y)? _importMenu;
    private string? _importing;

    /// <summary>New project or Open project…: the projects page (Home's ?view=projects).</summary>
    [Parameter]
    public EventCallback OnProjects { get; set; }

    [Inject]
    private ProjectsClient Projects { get; set; } = default!;

    [Inject]
    private ProjectState Project { get; set; } = default!;

    [Inject]
    private ProjectSetup Setup { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private ExportsClient Exports { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    private string? InstallingWords => Setup.Running && Setup.Now is { } now ? now.Words : null;

    protected override async Task OnInitializedAsync()
    {
        await Js.InvokeVoidAsync("sab.setTitle", string.Empty); // the window says the project's name alone
        Live.NoticeArrived += OnNotice;
        Setup.Changed += OnSetup;
        await LoadAsync();
    }

    private async Task LoadAsync()
    {
        try
        {
            _summary = await Projects.SummaryAsync();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        StateHasChanged();
    }

    private void OnNotice(Notice notice)
    {
        if (_followed.Contains(notice.Type))
        {
            _ = InvokeAsync(SettleAsync);
        }
    }

    // Many notices come together (a project opening reads every table): one read once they settle.
    private async Task SettleAsync()
    {
        _settling?.Cancel();
        _settling = new CancellationTokenSource();
        try
        {
            await Task.Delay(SettleMilliseconds, _settling.Token);
        }
        catch (TaskCanceledException)
        {
            return;
        }
        await LoadAsync();
    }

    private void OnSetup() => _ = InvokeAsync(StateHasChanged);

    private Task SaveAsync() => GuardAsync(async () =>
    {
        await Projects.SaveAsync();
        await Project.RefreshAsync();
    });

    private Task AutosaveAsync(bool on) => GuardAsync(async () =>
    {
        await Projects.AutosaveAsync(on);
        await Project.RefreshAsync();
    });

    private Task CloseAsync() => GuardAsync(() => ProjectAsks.CloseAsync(Dialogs, Project, Projects));

    private async Task CopyPathAsync()
    {
        if (_summary?.Project is { } project && await Js.InvokeAsync<bool>("sab.copy", project.Path))
        {
            await Notes.SayAsync("The project's folder is on the clipboard");
        }
    }

    // Show in folder stays the user's click (the server refuses the agent).
    private Task ShowFolderAsync() => GuardAsync(() => _summary?.Project is { } project ? Projects.ShowAsync(project.Path) : Task.CompletedTask);

    /// <summary>ARCHITECTURE.md written at the project's top (only when its bytes change); Download saves a copy.</summary>
    private Task OutlineAsync() => GuardAsync(async () =>
    {
        var (done, words) = await OutlineExport.RunAsync(Exports, Dialogs);
        await Notes.SayAsync(words, "Download", () => Js.InvokeVoidAsync("sab.saveText", done.File, done.Text).AsTask());
    });

    // Import… (the shared import dialog): notebooks, scripts and apps into the open project; connections and blades
    // into this computer's library.
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
        if (done is not null)
        {
            await LoadAsync();
        }
    }

    private async Task GuardAsync(Func<Task> work)
    {
        try
        {
            await work();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    public void Dispose()
    {
        Live.NoticeArrived -= OnNotice;
        Setup.Changed -= OnSetup;
        _settling?.Cancel();
        _settling?.Dispose();
        GC.SuppressFinalize(this);
    }
}
