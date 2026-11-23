using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Files;
using SwissArmyBench.Web.Api.PowerApps;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.CodeApp;

public partial class CodeAppPage
{
    private static readonly (string Id, string Label, bool Needs)[] _tabs =
    [
        ("project", "Project", false),
        ("connectors", "Connectors", false),
        ("live", "Run live", true),
        ("push", "Push", true),
        ("custom", "Custom connector", false),
        ("runs", "Runs", false),
    ];

    // Each run's lines as they come (the powerapps_output notice), kept for the page's life.
    private readonly Dictionary<string, List<string>> _lines = [];
    private CodeAppState? _state;
    private Exception? _error;
    private string _tab = "project";
    private string? _installing;
    private bool _signingIn;
    private bool _newOpen;

    [Inject]
    private CodeAppClient CodeApps { get; set; } = default!;

    [Inject]
    private FileChooser Files { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    protected override async Task OnInitializedAsync()
    {
        Live.NoticeArrived += OnNotice;
        await Js.InvokeVoidAsync("sab.setTitle", "Code App");
        await LoadAsync();
    }

    /// <summary>.NET is only how the Power Platform CLI is installed: shown while that is missing.</summary>
    private static IEnumerable<CodeAppTool> Tools(CodeAppState state) =>
        state.Tools.Tools.Where(t => !(t.Id == "dotnet" && state.Tools.Tools.Any(p => p.Id == "pac" && p.Ok)));

    public async Task LoadAsync()
    {
        try
        {
            _state = await CodeApps.StateAsync();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        StateHasChanged();
    }

    /// <summary>A call whose refusal is the error toast (a missing tool's words carry its Install).</summary>
    public async Task<T?> CallAsync<T>(Func<Task<T>> call)
        where T : class
    {
        try
        {
            return await call();
        }
        catch (ApiException error)
        {
            Notes.Error(error);
            return null;
        }
    }

    private async Task InstallAsync(CodeAppTool tool)
    {
        _installing = tool.Id;
        try
        {
            await CodeApps.InstallAsync(tool.Id);
            await Notes.SayAsync($"{tool.Name} is installed.");
            await LoadAsync();
        }
        catch (ApiException error)
        {
            Notes.Error(error);
        }
        finally
        {
            _installing = null;
        }
    }

    private async Task AccountAsync()
    {
        if (await CallAsync(CodeApps.AccountAsync) is { } account && _state is not null)
        {
            _state = _state with { Account = account };
        }
    }

    private async Task SignInAsync()
    {
        _signingIn = true;
        await Notes.SayAsync("Sign in in the browser window that opens.");
        if (await CallAsync(CodeApps.SignInAsync) is { } account && _state is not null)
        {
            _state = _state with { Account = account };
        }
        _signingIn = false;
    }

    public async Task OpenAsync(string? folder)
    {
        var chosen = folder ?? await Files.ChooseAsync("folder", "A code app's folder (it has power.config.json)");
        if (chosen is not null && await CallAsync(() => CodeApps.OpenAsync(chosen)) is not null)
        {
            await LoadAsync();
        }
    }

    private async Task CloseAsync()
    {
        if (await CallAsync(CodeApps.CloseAsync) is not null)
        {
            await LoadAsync();
        }
    }

    private async Task MadeAsync(string name)
    {
        _newOpen = false;
        _tab = "project";
        await Notes.SayAsync($"Made {name}.");
        await LoadAsync();
    }

    /// <summary>The Connectors tab, from the Project's Add a connector.</summary>
    public void ShowConnectors()
    {
        _tab = "connectors";
        StateHasChanged();
    }

    /// <summary>A code app's file or its data notebook in the Workbench's window (the classic Workbench: its
    /// TypeScript editor with Monaco's language service, and the notebook's Deno cells).</summary>
    public async Task OpenInWorkbenchAsync(string path, bool notebook = false)
    {
        var page = notebook ? "notebooks" : "scripts";
        var key = notebook ? "open" : "codefile";
        var module = await Js.InvokeAsync<IJSObjectReference>("import", "./js/canvas.js");
        var opened = await module.InvokeAsync<bool>("openPage", $"/{page}#{key}={Uri.EscapeDataString(path)}", "swissarmybench-codeapp-workbench", string.Empty);
        if (!opened)
        {
            Notes.Error(new InvalidOperationException("The browser blocked the new window: allow pop-ups for this address."));
        }
    }

    private void OnNotice(Notice notice)
    {
        if (notice.Type == "powerapps_output" && notice.Text("run") is { } run && notice.Text("line") is { } line)
        {
            if (!_lines.TryGetValue(run, out var lines))
            {
                lines = [];
                _lines[run] = lines;
            }
            lines.Add(line);
            if (_tab == "runs")
            {
                _ = InvokeAsync(StateHasChanged);
            }
        }
        else if (notice.Type is "powerapps_project" or "powerapps_live" && _tab is "project" or "live")
        {
            _ = InvokeAsync(async () => { await LoadAsync(); StateHasChanged(); });
        }
    }

    public void Dispose() => Live.NoticeArrived -= OnNotice;
}
