using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.App;
using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Widgets;

// The IDE's panel under the code (the classic widgetPage.ts over codeIde.ts runPanel: Output | Result | Problems,
// folded until wanted) and Copilot's ghost text where the open project's mode declares it (the editors' inline
// source, the widget told as a script).
public partial class WidgetsPage
{
    private string? _panelTab;
    private bool _panelUserFolded;
    private IReadOnlyList<EditorProblem> _problems = [];
    private string _runOutput = string.Empty;
    private string? _runSaid;
    private IReadOnlyList<InlineProvider> _inline = [];

    [Inject]
    private AppClient AppApi { get; set; } = default!;

    /// <summary>The lint's problems, and the failed check's line beside them (the Preview's error).</summary>
    private IReadOnlyList<EditorProblem> PanelProblems =>
        _failedLine is { } line && _failed is { } failed && !_problems.Any(p => p.Line == line)
            ? [.. _problems, new EditorProblem(line, 1, failed.Message)]
            : _problems;

    /// <summary>The ghost text's document: the widget as a script of its own.</summary>
    private object? InlineDocument() => _current is { } widget
        ? new { key = $"widget-{widget.Name}", name = $"{widget.Name}.py", kind = "script", language = "python", text = _code }
        : null;

    private async Task LoadInlineAsync()
    {
        try
        {
            _inline = (await AppApi.ModeAsync()).Mode.InlineCompletion ?? [];
        }
        catch (ApiException)
        {
            _inline = []; // no ghost text: the editor stands without it
        }
    }

    /// <summary>The lint drew again: its problems listed; a new error opens the panel on them (8.14).</summary>
    private async Task ProblemsChangedAsync(int count)
    {
        var before = _problems.Count;
        _problems = _editor is null ? [] : await _editor.ProblemsAsync();
        if (_panelTab is null && !_panelUserFolded && before == 0 && count > 0)
        {
            _panelTab = IdeRunPanel.ProblemsTab;
        }
        StateHasChanged();
    }

    private void PanelTab(string? tab)
    {
        _panelUserFolded = tab is null;
        _panelTab = tab;
    }

    /// <summary>A run began: its words in Output, the panel open on it (the user's fold forgotten).</summary>
    private void RunStarted(string name)
    {
        _panelUserFolded = false;
        _runOutput = $"Running {name} alone in the Preview…\n";
        _runSaid = null;
        _panelTab = IdeRunPanel.OutputTab;
    }

    /// <summary>A run ended: shown in the Preview, or its failure said.</summary>
    private void RunEnded(string? url, Exception? failure)
    {
        if (failure is null && url is not null)
        {
            _runOutput += $"It runs at {url}: shown in the Preview.\n";
            _runSaid = "Running";
        }
        else if (failure is not null)
        {
            _runOutput += $"{failure.Message}\n";
            _runSaid = "Failed";
        }
    }
}
