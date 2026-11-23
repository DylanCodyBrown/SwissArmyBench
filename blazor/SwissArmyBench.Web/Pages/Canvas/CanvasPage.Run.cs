using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Canvas;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>The Canvas's Play, Launch, Export and their menus (the classic canvasRun.ts and canvasMenus.ts): Play (F5)
/// shows the page live in place; Launch (Ctrl+F5) a build in its own window; with the Performance Analyzer
/// (Ctrl+Shift+F5) its window beside; Builds…; Export… (Ctrl+Shift+E); Stop while it runs. One run at a time.</summary>
public partial class CanvasPage
{
    private const string LaunchFeatures = "popup,width=1300,height=860";
    private const string AnalyzerFeatures = "popup,width=1200,height=820";

    private string? _playUrl;
    private bool _launched;
    private string? _busyWords;

    private string PlayTitle => Running ? (_playUrl is not null ? "Stop playing (Esc)" : "Stop the launched app") : "Play (F5)";

    private string PlayFrameStyle => FormattableString.Invariant($"width: {_view.PreviewWidth[_view.Layout]}px; max-width: 100%; align-self: center;");

    private ShareTarget? Shareable => _view.State is { } state ? new ShareTarget("streamlit", state.Canvas, state.Name) : null;

    private Task PlayOrStopAsync() => Running ? StopRunningAsync() : PlayAsync();

    private Task StopRunningAsync() => _playUrl is not null ? StopPlayAsync() : StopLaunchAsync();

    private void MoreWaysAsync(Microsoft.AspNetCore.Components.Web.MouseEventArgs e) =>
        _menu = new OpenMenu(e.ClientX - e.OffsetX, e.ClientY - e.OffsetY + 30, LaunchEntries(group: false));

    private void LiveMenu(Microsoft.AspNetCore.Components.Web.MouseEventArgs e) => _menu = new OpenMenu(e.ClientX, e.ClientY, RunGroup(after: false));

    /// <summary>Play's ▾ (and the run group's middle): Launch, or Stop while launched; the analyzer; Share… while
    /// launched; Builds….</summary>
    public IReadOnlyList<CanvasMenuItem> LaunchEntries(bool group)
    {
        var entries = new List<CanvasMenuItem>
        {
            _launched
                ? new("Stop the launched app", StopLaunchAsync, Group: group)
                : new("Launch", () => LaunchAsync(false), "Ctrl+F5", group),
            _launched
                ? new("Performance Analyzer", OpenAnalyzerAsync)
                : new("Launch with the Performance Analyzer", () => LaunchAsync(true), "Ctrl+Shift+F5"),
        };
        if (_launched)
        {
            entries.Add(new("Share…", () => { _sharing = true; return Task.CompletedTask; }));
        }
        entries.Add(new("Builds…", () => { _buildsOpen = true; return Task.CompletedTask; }, Disabled: _view.State is null));
        return entries;
    }

    /// <summary>The run group at the bottom of every right-click menu: Play (Stop playing while it plays), the
    /// launch entries, Export….</summary>
    public IReadOnlyList<CanvasMenuItem> RunGroup(bool after) =>
    [
        _playUrl is not null
            ? new("Stop playing", StopPlayAsync, "Esc", after)
            : new("Play", PlayAsync, "F5", after),
        .. LaunchEntries(group: false),
        new("Export…", ExportAsync, "Ctrl+Shift+E"),
    ];

    private async Task GatedAsync(string words, Func<Task> work)
    {
        if (_busyWords is not null)
        {
            return;
        }
        _busyWords = words;
        StateHasChanged();
        try
        {
            await work();
        }
        finally
        {
            _busyWords = null;
            StateHasChanged();
        }
    }

    private async Task PlayAsync()
    {
        if (_view.State is not { } state)
        {
            return;
        }
        var broken = WiringRules.BrokenWords(state.Wiring);
        if (broken.Length > 0)
        {
            Say(broken); // listed before Play: the page runs, each broken In on its starting value
        }
        await GatedAsync("Starting the page…", async () =>
        {
            try
            {
                var said = await Canvases.PlayAsync(state.Canvas, _view.Page);
                if (said.Problem?.Missing is { } missing)
                {
                    _ = RunNeedsAsync(missing, said.Problem.Install, PlayAsync);
                    return;
                }
                if (!said.Ok || said.Url is null)
                {
                    _warning = null;
                    _error = new InvalidOperationException(said.Problem?.Message ?? "The page did not start.");
                    return;
                }
                ClearError();
                _playUrl = said.Url;
            }
            catch (ApiException error)
            {
                _error = error;
            }
        });
    }

    private async Task StopPlayAsync()
    {
        _playUrl = null;
        StateHasChanged();
        if (_view.State is { } state)
        {
            try
            {
                await Canvases.StopAsync(state.Canvas);
            }
            catch (ApiException)
            {
                // the page is back to editing either way
            }
        }
    }

    private async Task StopLaunchAsync()
    {
        if (_view.State is not { } state)
        {
            return;
        }
        _launched = false;
        try
        {
            await Canvases.StopAsync(state.Canvas, "launch");
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>Launch: a new build run in a window of its own (both windows opened now, on the key or click: a
    /// window opened after the wait would be blocked); analyzer: the Performance Analyzer's window beside.</summary>
    private async Task LaunchAsync(bool analyzer)
    {
        if (_view.State is not { } state || _module is null)
        {
            return;
        }
        var opened = await _module.InvokeAsync<IJSObjectReference?>("openWindow", $"sab-launch-{state.Canvas}", LaunchFeatures);
        var perf = analyzer ? await _module.InvokeAsync<IJSObjectReference?>("openWindow", $"sab-perf-{state.Canvas}", AnalyzerFeatures) : null;
        await GatedAsync(analyzer ? "Launching with the Performance Analyzer…" : "Launching…", async () =>
        {
            try
            {
                var said = await Canvases.LaunchAsync(state.Canvas, analyzer);
                if (said.Problem?.Missing is { } missing)
                {
                    await CloseAsync(opened, perf);
                    _ = RunNeedsAsync(missing, said.Problem.Install, () => LaunchAsync(analyzer));
                    return;
                }
                if (!said.Ok || said.Url is null)
                {
                    await CloseAsync(opened, perf);
                    _error = new InvalidOperationException(said.Problem?.Message ?? "The app did not start.");
                    return;
                }
                _launched = true;
                if (opened is not null)
                {
                    await opened.InvokeVoidAsync("go", said.Url);
                }
                else
                {
                    _error = new InvalidOperationException("The browser blocked the new window: allow pop-ups for this address.");
                }
                if (perf is not null)
                {
                    await perf.InvokeVoidAsync("go", AnalyzerAddress(state.Canvas));
                }
                await Notes.SayAsync($"{said.Title ?? "The app"} launched.");
            }
            catch (ApiException error)
            {
                await CloseAsync(opened, perf);
                _error = error;
            }
        });
    }

    private static async Task CloseAsync(params IJSObjectReference?[] windows)
    {
        foreach (var window in windows.OfType<IJSObjectReference>())
        {
            await window.InvokeVoidAsync("close");
        }
    }

    /// <summary>The Performance Analyzer's address for a canvas's launch (this front end's own page).</summary>
    private string AnalyzerAddress(string canvas) => Nav.ToAbsoluteUri($"perf?canvas={Uri.EscapeDataString(canvas)}").ToString();

    private async Task OpenAnalyzerAsync()
    {
        if (_view.State is { } state && _module is not null)
        {
            await _module.InvokeAsync<bool>("openPage", AnalyzerAddress(state.Canvas), $"sab-perf-{state.Canvas}", AnalyzerFeatures);
        }
    }

    private async Task BuildLaunchedAsync(RunAnswer said)
    {
        _launched = true;
        await Notes.SayAsync($"{said.Title ?? "The build"} launched.");
    }

    private async Task ExportAsync()
    {
        if (_view.State is not { } state)
        {
            return;
        }
        // The canvas file's folder (either separator: the server may be on Windows).
        var cut = state.Path.LastIndexOfAny(['/', '\\']);
        var folder = await Files.ChooseAsync("folder", "Export the app into", cut > 0 ? state.Path[..cut] : state.Path);
        if (folder is null)
        {
            return;
        }
        await GatedAsync("Exporting…", async () =>
        {
            try
            {
                var done = await Canvases.ExportAsync(state.Canvas, folder);
                await Notes.SayAsync($"Exported: {done.Files.Count} files in {done.Folder}");
                // It calls the local sandbox API: the variables to set where it runs (its README lists them too).
                if (done.Warnings.Count > 0)
                {
                    _error = null;
                    _warning = string.Join(' ', done.Warnings);
                }
            }
            catch (ApiException error)
            {
                _error = error;
            }
        });
    }
}
