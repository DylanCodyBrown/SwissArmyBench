using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench.Ide;

public partial class SearchScripts
{
    // The search waits for typing to settle this long.
    private const int SettleMs = 250;

    private string _query = string.Empty;
    private string _to = string.Empty;
    private bool _regex;
    private bool _case;
    private bool _word;
    private IdeSearch? _found;
    private IdePlan? _plan;
    private Exception? _error;
    private CancellationTokenSource? _later;

    [Inject]
    private ScriptIdeClient Ide { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Parameter]
    public EventCallback OnClose { get; set; }

    /// <summary>A result's line: its file opened there (the dialog closes first).</summary>
    [Parameter]
    public EventCallback<IdePlace> OnGo { get; set; }

    private static List<IdePlace> Places(IdeSearch found) => found.Results
        .SelectMany(r => r.Matches.Select(m => new IdePlace(r.Path, m.Line, m.Column, string.Empty, Text: m.Text.Trim())))
        .ToList();

    private async Task LaterAsync()
    {
        _later?.Cancel();
        _later = new CancellationTokenSource();
        var token = _later.Token;
        try
        {
            await Task.Delay(SettleMs, token);
            await FindAsync();
        }
        catch (TaskCanceledException)
        {
            // typing went on: the later search runs instead
        }
    }

    private async Task FindAsync()
    {
        _plan = null;
        if (_query.Length == 0)
        {
            _found = null;
            return;
        }
        await GuardAsync(async () => _found = await Ide.SearchAsync(_query, _regex, _case, _word));
    }

    private Task PlanAsync() => GuardAsync(async () => _plan = await Ide.ReplacePlanAsync(_query, _regex, _case, _word, _to));

    private Task ApplyAsync() => GuardAsync(async () =>
    {
        var done = await Ide.ReplaceAsync(_query, _regex, _case, _word, _to);
        await OnClose.InvokeAsync();
        await Notes.SayAsync($"Replaced in {done.Written.Count} file(s).");
    });

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
}
