using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

public partial class DebugPanel
{
    private readonly List<DebugBreakpoint> _marks = [];
    private readonly List<(string Expression, DebugEvaluated? Got)> _watched = [];
    private bool _open;
    private string? _kernel;
    private DebugState? _state;
    private int? _frame;
    private IReadOnlyList<DebugScope> _scopes = [];
    private string _watch = string.Empty;
    private string _line = string.Empty;
    private string _console = string.Empty;
    private ShownMenu? _menu;
    private Exception? _error;

    [Inject]
    private DebugClient Debug { get; set; } = default!;

    [Inject]
    private PythonSession Session { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    /// <summary>The script's editor: its gutter draws the breakpoints and the paused line.</summary>
    [Parameter]
    public CodeEditor? Editor { get; set; }

    /// <summary>The script's file (null: not saved).</summary>
    [Parameter]
    public string? Path { get; set; }

    /// <summary>Paused at a breakpoint: F5 continues.</summary>
    public bool Paused => _state?.State == "paused";

    public bool Active => _state?.State is "paused" or "running";

    private string StatusWords => _state?.State switch
    {
        "paused" => $"Paused{(_state.Frames.FirstOrDefault() is { } top ? $" in {top.Name}, line {top.Line}" : string.Empty)}",
        "running" => "Running…",
        "ended" => "Ended",
        _ => "Not debugging",
    };

    protected override void OnInitialized() => Live.NoticeArrived += OnNotice;

    /// <summary>Start debugging: the script as it is on screen, run under the debugger with its breakpoints.</summary>
    public async Task StartAsync(string code) => await GuardAsync(async () =>
    {
        await FollowAsync();
        _kernel = await Session.KernelForAsync(Path);
        _open = true;
        _console = string.Empty;
        await HeardAsync(await Debug.StartAsync(_kernel, Path, code, _marks));
    });

    /// <summary>A click in the gutter toggles the line's breakpoint; a right click opens Breakpoints at line N.</summary>
    public async Task GutterAsync(GutterClick click)
    {
        await FollowAsync();
        if (!click.Menu)
        {
            await SetMarkAsync(click.Line, _marks.Any(m => m.Line == click.Line) ? null : new DebugBreakpoint(click.Line));
            return;
        }
        var here = _marks.FirstOrDefault(m => m.Line == click.Line);
        var line = click.Line;
        List<MenuEntry> entries =
        [
            here is null
                ? new("Add breakpoint", "bug", () => SetMarkAsync(line, new DebugBreakpoint(line)))
                : new($"Remove {KindWords(here).ToLowerInvariant()}", "close", () => SetMarkAsync(line, null)),
            new(here?.Condition is not null ? "Edit condition…" : "Add conditional breakpoint…", "bug", async () =>
            {
                if (await AskAsync($"Break at line {line} when (Python)", here?.Condition) is { } condition)
                {
                    await SetMarkAsync(line, new DebugBreakpoint(line, Condition: condition));
                }
            }),
            new(here?.Log is not null ? "Edit log point…" : "Add log point…", "edit", async () =>
            {
                if (await AskAsync($"At line {line}, print (values in {{braces}})", here?.Log) is { } log)
                {
                    await SetMarkAsync(line, new DebugBreakpoint(line, Log: log));
                }
            }),
        ];
        _menu = new ShownMenu($"Breakpoints at line {line}", entries, click.X, click.Y);
    }

    /// <summary>Toggle breakpoint at the cursor's line.</summary>
    public async Task ToggleAtCursorAsync()
    {
        if (Editor is not null && await Editor.CursorLineAsync() is > 0 and var line)
        {
            await GutterAsync(new GutterClick(line, false, 0, 0));
        }
    }

    private static string KindWords(DebugBreakpoint mark) =>
        mark.Log is not null ? "Log point" : mark.Condition is not null ? "Conditional breakpoint" : "Breakpoint";

    private async Task<string?> AskAsync(string words, string? now)
    {
        var said = await Dialogs.AskTextAsync(words, words, words, now ?? string.Empty);
        return string.IsNullOrWhiteSpace(said) ? null : said.Trim();
    }

    private async Task SetMarkAsync(int line, DebugBreakpoint? mark)
    {
        _marks.RemoveAll(m => m.Line == line);
        if (mark is not null)
        {
            _marks.Add(mark);
        }
        _marks.Sort((a, b) => a.Line.CompareTo(b.Line));
        await DrawMarksAsync();
        if (_kernel is not null && Active)
        {
            await GuardAsync(() => Debug.BreakpointsAsync(_kernel, _marks));
        }
    }

    private Task DrawMarksAsync() => Editor?.SetBreakpointsAsync(_marks
        .Select(m => new BreakpointMark(m.Line, m.Log is not null ? "log" : m.Condition is not null ? "condition" : "plain",
            m.Log is not null ? $"Log point: {m.Log}" : m.Condition is not null ? $"Breaks when {m.Condition}" : "Breakpoint"))
        .ToList()) ?? Task.CompletedTask;

    /// <summary>The marks' lines as edits moved them (the gutter's decorations, in line order).</summary>
    private async Task FollowAsync()
    {
        if (Editor is null || _marks.Count == 0)
        {
            return;
        }
        var lines = await Editor.BreakpointLinesAsync();
        if (lines.Count == _marks.Count)
        {
            var moved = _marks.Zip(lines, (m, l) => m with { Line = l }).ToList();
            _marks.Clear();
            _marks.AddRange(moved);
        }
    }

    public Task StepAsync(string action) => !Paused || _kernel is null ? Task.CompletedTask : GuardAsync(async () =>
    {
        await (Editor?.SetExecutionLineAsync(null) ?? Task.CompletedTask);
        _state = _state! with { State = "running" };
        await Debug.StepAsync(_kernel, action);
    });

    public Task StopAsync() => _kernel is null ? Task.CompletedTask : GuardAsync(async () => await HeardAsync(await Debug.StopAsync(_kernel)));

    /// <summary>A state heard (an answer, or the debug_state notice for this kernel): drawn.</summary>
    private async Task HeardAsync(DebugState said)
    {
        if (said.Kernel != _kernel)
        {
            return;
        }
        var output = said.Output ?? (await Debug.StateAsync(_kernel).ContinueWith(t => t.IsCompletedSuccessfully ? t.Result.Output : null));
        _state = said with { Output = output };
        if (said.State == "paused")
        {
            _open = true;
            _frame = said.Frames.FirstOrDefault()?.Id;
            await (Editor?.SetExecutionLineAsync(said.Frames.FirstOrDefault(f => f.Yours)?.Line) ?? Task.CompletedTask);
            await ShowVariablesAsync();
        }
        else
        {
            await (Editor?.SetExecutionLineAsync(null) ?? Task.CompletedTask);
            (_frame, _scopes) = (null, []);
        }
        await ShowWatchesAsync();
    }

    private async Task ChooseFrameAsync(DebugFrame frame)
    {
        _frame = frame.Id;
        if (frame.Yours && Editor is not null)
        {
            await Editor.RevealLineAsync(frame.Line);
        }
        await ShowVariablesAsync();
        await ShowWatchesAsync();
    }

    private Task ShowVariablesAsync() => _kernel is null || _frame is not { } frame
        ? Task.CompletedTask
        : GuardAsync(async () => _scopes = (await Debug.ScopesAsync(_kernel, frame)).Scopes ?? []);

    private async Task ShowWatchesAsync()
    {
        var shown = new List<(string, DebugEvaluated?)>();
        foreach (var (expression, _) in _watched)
        {
            shown.Add((expression, Paused && _kernel is not null ? await EvaluateAsync(expression) : null));
        }
        _watched.Clear();
        _watched.AddRange(shown);
    }

    private async Task<DebugEvaluated> EvaluateAsync(string expression)
    {
        try
        {
            return _kernel is null ? new DebugEvaluated(Error: "Not debugging.") : await Debug.EvaluateAsync(_kernel, expression, _frame);
        }
        catch (ApiException error)
        {
            return new DebugEvaluated(Error: error.Refusal.Error);
        }
    }

    private async Task WatchKeyAsync(KeyboardEventArgs e)
    {
        if (e.Key == "Enter" && _watch.Trim().Length > 0)
        {
            _watched.Add((_watch.Trim(), null));
            _watch = string.Empty;
            await ShowWatchesAsync();
        }
    }

    private async Task RemoveWatchAsync(string expression)
    {
        _watched.RemoveAll(w => w.Expression == expression);
        await ShowWatchesAsync();
    }

    private async Task ConsoleKeyAsync(KeyboardEventArgs e)
    {
        if (e.Key != "Enter" || _line.Trim().Length == 0)
        {
            return;
        }
        var expression = _line.Trim();
        _line = string.Empty;
        var got = await EvaluateAsync(expression);
        _console += $">>> {expression}\n{got.Error ?? got.Value}\n";
    }

    private void OnNotice(Notice notice)
    {
        if (notice.Type == "debug_state" && _kernel is not null && notice.Text("kernel") == _kernel)
        {
            var said = notice.Body.Deserialize<DebugState>(ApiClient.Json);
            if (said is not null)
            {
                _ = InvokeAsync(async () =>
                {
                    await HeardAsync(said);
                    StateHasChanged();
                });
            }
        }
    }

    private async Task GuardAsync(Func<Task> action)
    {
        try
        {
            await action();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    public void Dispose() => Live.NoticeArrived -= OnNotice;
}
