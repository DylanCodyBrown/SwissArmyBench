using System.Text.Json;

using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>
/// A run in the document's Python session (the classic workbenchKernel.ts run): the session's kernel found or
/// started, the code sent, and each record drawn into the cell as it arrives (outputs, the kernel asking for a
/// line, the error taken apart, a clear), then the run's number. A notebook cell and the script's console both
/// run through it.
/// </summary>
public sealed class CellRunner
{
    private readonly WorkbenchClient _workbench;
    private readonly PythonSession _session;

    public CellRunner(WorkbenchClient workbench, PythonSession session)
    {
        _workbench = workbench;
        _session = session;
    }

    /// <summary>Runs the request into the cell; `redraw` is called after each record. A refusal (no kernel, a
    /// server that stopped) is thrown to the page's error note.</summary>
    public async Task RunAsync(CellModel cell, RunRequest request, string? path, Func<Task> redraw)
    {
        var kernel = await _session.KernelForAsync(path);
        cell.Running = true;
        cell.Outputs = [];
        cell.ErrorDetail = null;
        _session.Ran(true);
        await redraw();
        var clearNext = false;
        try
        {
            await foreach (var record in _workbench.RunAsync(kernel, request))
            {
                if (record.TryGetProperty("done", out var done))
                {
                    cell.ExecutionCount = done.TryGetProperty("execution_count", out var count) && count.ValueKind == JsonValueKind.Number ? count.GetInt32() : cell.ExecutionCount;
                    break;
                }
                clearNext = Take(cell, record, clearNext);
                await redraw();
            }
        }
        finally
        {
            cell.Running = false;
            if (cell.Asking is { } unanswered)
            {
                // The run ended while its question waited: said under it (the classic "(not answered)").
                var line = $"{unanswered.Prompt} (not answered)\n";
                OutputReader.Add(cell.Outputs, JsonSerializer.SerializeToElement(new { output_type = "stream", name = "stdout", text = line }));
            }
            cell.Asking = null;
            _session.Ran(false);
            await redraw();
        }
    }

    /// <summary>The line typed for the kernel's question.</summary>
    public async Task AnswerAsync(CellModel cell, string line)
    {
        cell.Asking = null;
        if (_session.Kernel is { } kernel)
        {
            await _workbench.AnswerInputAsync(kernel, line);
        }
    }

    /// <summary>One record into the cell; whether the next output clears the ones before it (a clear that waits).</summary>
    internal static bool Take(CellModel cell, JsonElement record, bool clearNext)
    {
        if (record.TryGetProperty("input_request", out var asked))
        {
            cell.Asking = (OutputReader.Text(asked, "prompt"), asked.TryGetProperty("password", out var secret) && secret.ValueKind == JsonValueKind.True);
            return clearNext;
        }
        if (record.TryGetProperty("error_detail", out var detail))
        {
            cell.ErrorDetail = detail.Clone();
            return clearNext;
        }
        if (record.TryGetProperty("clear", out _))
        {
            var waits = record.TryGetProperty("wait", out var wait) && wait.ValueKind == JsonValueKind.True;
            if (!waits)
            {
                cell.Outputs.Clear();
            }
            return waits;
        }
        if (clearNext)
        {
            cell.Outputs.Clear();
        }
        OutputReader.Add(cell.Outputs, record);
        return false;
    }
}
