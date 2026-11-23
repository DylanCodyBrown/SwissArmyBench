using System.Globalization;
using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Analyze;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Analyze;

public partial class BoardCardView
{
    // The board is twelve columns wide; a card spans its size's width, and is this tall per unit of its height.
    private const int BoardColumns = 12;
    private const int RowUnitPixels = 32;
    private const int DefaultWidth = 6;
    private const int DefaultHeight = 10;

    private RunMath? _math;
    private Exception? _error;

    [Inject]
    private AnalyzeClient AnalyzeApi { get; set; } = default!;

    [Inject]
    private GridsClient Grids { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Parameter, EditorRequired]
    public BoardCard Card { get; set; } = default!;

    /// <summary>Landed by the run just made (marked so the eye finds it).</summary>
    [Parameter]
    public bool Fresh { get; set; }

    [Parameter]
    public EventCallback<BoardCard> OnRemove { get; set; }

    [Parameter]
    public EventCallback<string> OnAgain { get; set; }

    /// <summary>The analysis run this card came from, when it came from one.</summary>
    private string? Run => Card.Analysis is { ValueKind: JsonValueKind.Object } analysis && analysis.TryGetProperty("run", out var run) ? run.GetString() : null;

    /// <summary>The result's next steps (Show these rows, Exclude these): each a step for the table it ran on.</summary>
    private IEnumerable<(string Label, JsonElement Step)> HandOffs =>
        Card.Analysis is { ValueKind: JsonValueKind.Object } analysis && analysis.TryGetProperty("next", out var next) && next.ValueKind == JsonValueKind.Array
            ? next.EnumerateArray()
                .Where(n => n.TryGetProperty("label", out _) && n.TryGetProperty("step", out _))
                .Select(n => (n.GetProperty("label").GetString() ?? string.Empty, n.GetProperty("step")))
            : [];

    private string Span
    {
        get
        {
            var width = Size("w", DefaultWidth);
            var height = Size("h", DefaultHeight);
            return string.Create(CultureInfo.InvariantCulture, $"grid-column: span {Math.Clamp(width, 1, BoardColumns)}; min-height: {height * RowUnitPixels}px;");
        }
    }

    private int Size(string name, int fallback) =>
        Card.Size is { ValueKind: JsonValueKind.Object } size && size.TryGetProperty(name, out var value) && value.TryGetInt32(out var number) ? number : fallback;

    private async Task MathAsync(string run) => await DoAsync(async () => _math = await AnalyzeApi.MathAsync(run));

    private Task GridAsync(string run) => DoAsync(async () =>
    {
        var made = await AnalyzeApi.OpenGridAsync(run);
        Nav.NavigateTo($"grids?grid={Uri.EscapeDataString(made.Grid ?? string.Empty)}");
    });

    private Task CodeAsync(string run) => DoAsync(async () =>
    {
        var code = await AnalyzeApi.CodeAsync(run);
        var text = string.Join("\n", code.Imports) + "\n\n" + code.Code;
        await Js.InvokeAsync<bool>("sab.copy", text);
        _ = Notes.SayAsync("Copied the analysis as Python.");
    });

    /// <summary>A hand-off: its step added to the table the analysis ran on, then that table shown.</summary>
    private Task HandOffAsync(JsonElement step) => DoAsync(async () =>
    {
        if (Card.Analysis is not { } analysis || !analysis.TryGetProperty("table", out var table) || table.GetString() is not { } grid)
        {
            return;
        }
        await Grids.AddStepAsync(grid, step.GetProperty("kind").GetString() ?? string.Empty, step.GetProperty("params"));
        Nav.NavigateTo($"grids?grid={Uri.EscapeDataString(grid)}");
    });

    private async Task DoAsync(Func<Task> action)
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
