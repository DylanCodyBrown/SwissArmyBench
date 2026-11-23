using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Blades;

namespace SwissArmyBench.Web.Pages.Workbench.Blades;

// The blade IDE's Run (Test's child process, the code as it is on screen) and its realtime lint: Output | Result |
// Problems under the code, folded until something runs; a failure as the error panel with its line marked.
public partial class BladeIde
{
    private BladeRun? _run;
    private IReadOnlyList<BladeProblem> _problems = [];
    private string? _panel;
    private bool _running;

    private async Task RunAsync()
    {
        _code = await CodeNow();
        _running = true;
        _panel ??= "output";
        try
        {
            _run = await Blades.RunAsync(Name, _code);
            _panel = _run.Ok && _run.Result is not null ? "result" : _run.Ok ? "output" : "result";
            _problems = _run.Problems ?? _problems;
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _running = false;
    }

    private async Task RelintAsync()
    {
        if (_detail is null || Language != "python")
        {
            return;
        }
        try
        {
            _problems = (await Blades.ProblemsAsync(Name, _code)).Problems;
        }
        catch (ApiException)
        {
            // the lint said nothing this time; the next change asks again
        }
    }

    private Task GoToLineAsync(int line) => _editor?.RevealLineAsync(line) ?? Task.CompletedTask;
}
