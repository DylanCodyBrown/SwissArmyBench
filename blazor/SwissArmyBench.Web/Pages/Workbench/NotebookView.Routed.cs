using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.App;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

// The cells another kernel runs (the classic workbenchNotebook.ts "cells another kernel runs"): a TypeScript cell, a
// DuckDB SQL cell where the mode runs SQL in its kernel, a TSX cell drawn; a table result's Open as grid; the route's
// declarations given once to the editor's TypeScript service. The routes are the mode's data (MODE cell_routes).
public partial class NotebookView
{
    private RoutedRunner? _routedRunner;
    private bool _typesKnown;

    [Inject]
    private RoutedCellsClient RoutedCells { get; set; } = default!;

    [Inject]
    private PackagePrompts Prompts { get; set; } = default!;

    /// <summary>The cell kinds another kernel runs, as the open project's mode declares them (none: Python only).</summary>
    [Parameter]
    public IReadOnlyDictionary<string, CellRoute> Routes { get; set; } = new Dictionary<string, CellRoute>();

    private RoutedRunner Routed => _routedRunner ??= new RoutedRunner(RoutedCells, Prompts);

    /// <summary>The cell runs on its route (true), or in the Python kernel (false: the caller runs it).</summary>
    private async Task<bool> RunRoutedAsync(CellModel cell)
    {
        if (RoutedRunner.RouteOf(cell, Routes) is not { } route)
        {
            return false;
        }
        if (cell.Source.Trim().Length == 0)
        {
            return true;
        }
        Task Again() => InvokeAsync(() => RunAsync(cell));
        if (cell.Kind == "tsx")
        {
            cell.Running = true;
            await Routed.PreviewAsync(cell, route, Path, Again);
            cell.Running = false;
        }
        else
        {
            await Routed.RunAsync(cell, route, Path, () => InvokeAsync(StateHasChanged), Again);
        }
        await OnChanged.InvokeAsync();
        return true;
    }

    /// <summary>A routed table result opened as a grid by its id, named after the cell when it has a name.</summary>
    private async Task OpenRoutedTableAsync((CellModel Cell, string Id) table)
    {
        if (RoutedRunner.RouteOf(table.Cell, Routes) is not { } route)
        {
            return;
        }
        try
        {
            var name = table.Cell.Name is { Length: > 0 } named ? System.Text.RegularExpressions.Regex.Replace(named, @"\W+", "_") : null;
            if (await Routed.OpenTableAsync(route, Path, table.Id, name) is { } said)
            {
                _ = Notes.SayAsync(said);
            }
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>The route's declarations known to the editor's TypeScript service, once a page.</summary>
    private async Task KnowTypesAsync()
    {
        var route = Routes.GetValueOrDefault("typescript") ?? Routes.GetValueOrDefault("tsx");
        if (_typesKnown || route is null)
        {
            return;
        }
        if (!_kept.Cells.Any(c => c.Kind is "typescript" or "tsx"))
        {
            return;
        }
        _typesKnown = true;
        if (await Routed.TypesAsync(route) is { Length: > 0 } declarations)
        {
            await CodeEditor.TypeScriptNotebookAsync(Js, declarations);
        }
    }
}
