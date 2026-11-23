using System.Globalization;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Canvas;

namespace SwissArmyBench.Web.Pages.Canvas;

public partial class BuildsDialog
{
    private const string LaunchFeatures = "popup,width=1300,height=860";
    private const string AnalyzerFeatures = "popup,width=1200,height=820";

    private readonly List<int> _ticked = [];
    private readonly HashSet<int> _restored = [];
    private IReadOnlyList<BuildInfo>? _builds;
    private IReadOnlyList<ComparedFile>? _files;
    private ComparedFile? _picked;
    private string _title = string.Empty;
    private string? _doing;
    private Exception? _error;

    [Inject]
    private CanvasClient Canvases { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private Api.Widgets.WidgetsClient Widgets { get; set; } = default!;

    [Inject]
    private State.PackagePrompts Prompts { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Parameter, EditorRequired]
    public string Canvas { get; set; } = string.Empty;

    [Parameter]
    public EventCallback OnClose { get; set; }

    /// <summary>A relaunch's answer: the page marks the app launched.</summary>
    [Parameter]
    public EventCallback<RunAnswer> OnLaunched { get; set; }

    /// <summary>A build's canvas restored: the page draws the canvas as the answer has it.</summary>
    [Parameter]
    public EventCallback<CanvasState> OnRestored { get; set; }

    protected override async Task OnInitializedAsync()
    {
        try
        {
            _builds = (await Canvases.BuildsAsync(Canvas)).Builds;
        }
        catch (ApiException error)
        {
            _builds = [];
            _error = error;
        }
    }

    private static string When(string time) =>
        DateTimeOffset.TryParse(time, CultureInfo.InvariantCulture, DateTimeStyles.None, out var at) ? at.ToLocalTime().ToString("d MMM yyyy, HH:mm", CultureInfo.InvariantCulture) : time;

    private static string ResultWords(BuildInfo build) => build.Result == "started"
        ? build.FirstLoadMs is { } ms ? $"started · {ms.ToString("0", CultureInfo.InvariantCulture)} ms" : "started"
        : build.Result;

    private static string SessionWords(string session) =>
        session.StartsWith("perf-", StringComparison.Ordinal) ? session[5..].Replace(".json", string.Empty, StringComparison.Ordinal) : session.Replace(".json", string.Empty, StringComparison.Ordinal);

    private string RestoreWords(int number) => _doing == $"restore{number}" ? "Restoring…" : _restored.Contains(number) ? "Restored" : "Restore";

    /// <summary>At most two ticked: a third takes the oldest tick's place.</summary>
    private void Tick(int number, bool on)
    {
        _ticked.Remove(number);
        if (on)
        {
            _ticked.Add(number);
        }
        if (_ticked.Count > 2)
        {
            _ticked.RemoveAt(0);
        }
    }

    private void PickKey(KeyboardEventArgs e, ComparedFile file)
    {
        if (e.Key is "Enter" or " ")
        {
            _picked = file;
        }
    }

    private void ShowFiles(string title, IReadOnlyList<ComparedFile> files)
    {
        var shown = files.Where(f => f.Status != "same").ToList();
        _files = shown.Count > 0 ? shown : files;
        _picked = _files.FirstOrDefault();
        _title = title;
    }

    private Task CompareAsync()
    {
        var pair = _ticked.Order().ToList();
        return LoadAsync(async () => ShowFiles($"Build {pair[0]} → build {pair[1]}", (await Canvases.CompareAsync(Canvas, pair[0], pair[1])).Files));
    }

    private Task ShowNowAsync(int number) =>
        LoadAsync(async () => ShowFiles($"Build {number} → now", (await Canvases.CompareAsync(Canvas, number, null)).Files));

    private Task ShowBuildAsync(int number) => LoadAsync(async () =>
    {
        var files = (await Canvases.BuildAsync(Canvas, number)).Files
            .Select(f => new ComparedFile { File = f.Key, Status = "same", Before = f.Value, After = f.Value })
            .ToList();
        ShowFiles($"Build {number} (read-only)", files);
    });

    private async Task LoadAsync(Func<Task> work)
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

    private async Task RelaunchAsync(int number)
    {
        var module = await Js.InvokeAsync<IJSObjectReference>("import", "./js/canvas.js");
        var opened = await module.InvokeAsync<IJSObjectReference?>("openWindow", $"sab-launch-{Canvas}", LaunchFeatures);
        _doing = $"launch{number}";
        try
        {
            var said = await Canvases.RelaunchAsync(Canvas, number);
            if (said.Problem?.Missing is { } missing)
            {
                // The Python lacks Streamlit: the one install prompt, and the relaunch again once it is in.
                if (opened is not null)
                {
                    await opened.InvokeVoidAsync("close");
                }
                _doing = null;
                _ = Prompts.PromptAsync(missing, force: true, install: m => Widgets.InstallAsync(said.Problem.Install, m.Packages), then: () => InvokeAsync(() => RelaunchAsync(number)));
                return;
            }
            if (!said.Ok || said.Url is null)
            {
                throw new InvalidOperationException(said.Problem?.Message ?? "The build did not start.");
            }
            if (opened is not null)
            {
                await opened.InvokeVoidAsync("go", said.Url);
            }
            await OnLaunched.InvokeAsync(said);
        }
        catch (Exception error) when (error is ApiException or InvalidOperationException)
        {
            if (opened is not null)
            {
                await opened.InvokeVoidAsync("close");
            }
            _error = error;
        }
        _doing = null;
    }

    private async Task RestoreAsync(int number)
    {
        _doing = $"restore{number}";
        try
        {
            await OnRestored.InvokeAsync(await Canvases.RestoreAsync(Canvas, number));
            _restored.Add(number);
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _doing = null;
    }

    private async Task OpenSessionAsync(int number, string session)
    {
        var address = Nav.ToAbsoluteUri($"perf?canvas={Uri.EscapeDataString(Canvas)}&build={number}&file={Uri.EscapeDataString(session)}").ToString();
        var module = await Js.InvokeAsync<IJSObjectReference>("import", "./js/canvas.js");
        await module.InvokeAsync<bool>("openPage", address, $"sab-perf-{Canvas}-{session}", AnalyzerFeatures);
    }
}
