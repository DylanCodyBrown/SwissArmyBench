using System.Text.Json;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.App;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>
/// A notebook cell another kernel runs (the classic workbenchNotebook.ts runOnRoute and runPreview, over
/// routedCells.ts): a TypeScript cell, or a DuckDB SQL cell where the mode runs SQL in its kernel, streams its outputs
/// into the cell as the Python kernel's do; a TSX cell is drawn by its route into the design frame. A tool the route
/// needs and this computer lacks is the one missing-package prompt, its Install the route's own.
/// </summary>
public sealed class RoutedRunner
{
    private readonly RoutedCellsClient _routed;
    private readonly PackagePrompts _prompts;

    public RoutedRunner(RoutedCellsClient routed, PackagePrompts prompts)
    {
        _routed = routed;
        _prompts = prompts;
    }

    /// <summary>Where a cell runs when not in the Python kernel: a TypeScript or TSX cell by its kind, a SQL cell
    /// with no connection of its own where the mode runs SQL; null: the Python kernel.</summary>
    public static CellRoute? RouteOf(CellModel cell, IReadOnlyDictionary<string, CellRoute> routes) => cell.Kind switch
    {
        "sql" when cell.Connection is null => routes.GetValueOrDefault("sql"),
        "typescript" or "tsx" => routes.GetValueOrDefault(cell.Kind),
        _ => null,
    };

    /// <summary>The run, each output drawn as it comes; true when it ended well. A refusal is thrown to the page.</summary>
    public async Task<bool> RunAsync(CellModel cell, CellRoute route, string? path, Func<Task> redraw, Func<Task> again)
    {
        cell.Running = true;
        cell.Outputs = [];
        cell.ErrorDetail = null;
        await redraw();
        var ok = false;
        try
        {
            var clearNext = false;
            var run = new RoutedRun(path, cell.Kind == "sql" ? "sql" : "typescript", cell.Source, cell.Number);
            await foreach (var record in _routed.RunAsync(route, run))
            {
                if (record.TryGetProperty("done", out var done))
                {
                    ok = done.TryGetProperty("ok", out var good) && good.ValueKind == JsonValueKind.True;
                    cell.ExecutionCount = done.TryGetProperty("execution_count", out var count) && count.ValueKind == JsonValueKind.Number ? count.GetInt32() : null;
                    break;
                }
                clearNext = CellRunner.Take(cell, record, clearNext);
                await redraw();
            }
        }
        catch (ApiException error) when (Prompted(route, error, again))
        {
            ok = false;
        }
        finally
        {
            cell.Running = false;
            cell.Failed = !ok;
            await redraw();
        }
        return ok;
    }

    /// <summary>A TSX cell drawn with the project's own React (null: the prompt took the error).</summary>
    public async Task<bool> PreviewAsync(CellModel cell, CellRoute route, string? path, Func<Task> again)
    {
        cell.Outputs = [];
        try
        {
            cell.Preview = await _routed.PreviewAsync(route, path, cell.Source, cell.Number);
            cell.Failed = false;
            return true;
        }
        catch (ApiException error) when (Prompted(route, error, again))
        {
            return false;
        }
        catch (ApiException error)
        {
            cell.Preview = null;
            cell.Failed = true;
            OutputReader.Add(cell.Outputs, JsonSerializer.SerializeToElement(new { output_type = "stream", name = "stderr", text = error.Message }));
            return false;
        }
    }

    /// <summary>A table result opened as a grid by its id; the words to say (null: nothing to say).</summary>
    public async Task<string?> OpenTableAsync(CellRoute route, string? path, string id, string? name) =>
        await _routed.OpenTableAsync(route, path, id, name) is { } dataset ? $"{dataset} is open as a grid." : "The result is open as a grid.";

    /// <summary>The route's declarations for the editor's TypeScript service.</summary>
    public Task<string> TypesAsync(CellRoute route) => _routed.TypesAsync(route);

    /// <summary>A missing tool's answer (422 with {missing}) put in the user's face, Install going to the route's own.</summary>
    private bool Prompted(CellRoute route, ApiException error, Func<Task> again)
    {
        if (MissingPackages.Of(error) is not { } missing)
        {
            return false;
        }
        var tool = ToolOf(error.Body);
        _ = _prompts.PromptAsync(missing, install: _ => _routed.InstallAsync(route, tool), then: again);
        return true;
    }

    private static string? ToolOf(string body)
    {
        try
        {
            using var parsed = JsonDocument.Parse(body);
            return parsed.RootElement.TryGetProperty("missing", out var missing) && missing.TryGetProperty("tool", out var tool) ? tool.GetString() : null;
        }
        catch (JsonException)
        {
            return null;
        }
    }
}
