using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

public partial class HtmlDesign
{
    /// <summary>The output an HTML cell's run gives (client/html_cells.py MIME): its names' values and marks.</summary>
    public const string HtmlMime = "application/vnd.swissarmybench.html-cell+json";

    // The classic workbenchHtml.ts limits: the pane's heights, a design's own height at most, an arrow key's step.
    private const int MinHeight = 60;
    private const int MaxHeight = 2000;
    private const int AutoMax = 640;
    private const int Step = 16;
    private const int BigStep = 80;

    private ElementReference _stage;
    private ElementReference _grip;
    private IJSObjectReference? _module;
    private IJSObjectReference? _design;
    private DotNetObjectReference<HtmlDesign>? _self;
    private int _fit = 160;
    private string _state = string.Empty;
    private IReadOnlyList<string> _notes = [];
    private string? _drawn;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private WorkbenchClient Workbench { get; set; } = default!;

    [Inject]
    private ThemeState Theme { get; set; } = default!;

    [Parameter, EditorRequired]
    public CellModel Cell { get; set; } = default!;

    /// <summary>Run: the cell runs, so its names are filled from the kernel.</summary>
    [Parameter]
    public EventCallback OnRun { get; set; }

    /// <summary>The user sized the pane (its height kept in the cell).</summary>
    [Parameter]
    public EventCallback OnResized { get; set; }

    private int Shown => Math.Clamp(Cell.Height ?? Math.Min(_fit, AutoMax), MinHeight, MaxHeight);

    private string StageStyle => string.Create(CultureInfo.InvariantCulture, $"height: {Shown}px");

    /// <summary>The names an HTML cell asks for ({{ name }}), each once.</summary>
    public static IReadOnlyList<string> Names(string html) =>
        NamePattern().Matches(html).Select(m => m.Groups[1].Value).Distinct().ToList();

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (firstRender)
        {
            _self = DotNetObjectReference.Create(this);
            _module = await Js.InvokeAsync<IJSObjectReference>("import", "./js/workbench.js");
            _design = await _module.InvokeAsync<IJSObjectReference>("design", _stage, _self);
            await _module.InvokeVoidAsync("grip", _grip, _self);
        }
        await DrawAsync();
    }

    /// <summary>The design drawn again when the HTML or its run changed: plain HTML at once, a cell with names from
    /// its last run's values (the server's filling), else its state with Run.</summary>
    private async Task DrawAsync()
    {
        var values = Values();
        var key = $"{Cell.Source}\u0000{values?.GetRawText()}\u0000{Theme.Effective}";
        if (_design is null || key == _drawn)
        {
            return;
        }
        _drawn = key;
        var names = Names(Cell.Source);
        var html = Cell.Source;
        (_state, _notes) = (string.Empty, []);
        if (names.Count > 0 && values is null)
        {
            _state = "Not run yet";
        }
        else if (names.Count > 0 && values is { } given)
        {
            try
            {
                var filled = await Workbench.FillHtmlAsync(Cell.Source, given);
                (html, _notes) = (filled.Html, filled.Notes.Concat(filled.Missing.Select(m => $"{m} is not made by the cell's run.")).ToList());
            }
            catch (ApiException error)
            {
                _notes = [error.Refusal.Error];
            }
        }
        await _design.InvokeVoidAsync("show", html, Theme.Effective is "dark" or "hc-dark");
        StateHasChanged();
    }

    private JsonElement? Values() => Cell.Outputs
        .Where(o => o.TryGetProperty("data", out var data) && data.TryGetProperty(HtmlMime, out _))
        .Select(o => o.GetProperty("data").GetProperty(HtmlMime))
        .Where(d => d.ValueKind == JsonValueKind.Object && d.TryGetProperty("values", out _))
        .Select(d => (JsonElement?)d.GetProperty("values"))
        .LastOrDefault();

    [JSInvokable]
    public Task Fits(double height)
    {
        _fit = (int)Math.Ceiling(Math.Clamp(height, MinHeight, MaxHeight));
        return InvokeAsync(StateHasChanged);
    }

    [JSInvokable]
    public Task Resized(double height) => InvokeAsync(() => SizeAsync((int)Math.Round(height)));

    private async Task SizeAsync(int? height)
    {
        Cell.Height = height is { } h ? Math.Clamp(h, MinHeight, MaxHeight) : null;
        await OnResized.InvokeAsync();
    }

    private Task GripKeyAsync(KeyboardEventArgs e)
    {
        var step = e.ShiftKey ? BigStep : Step;
        return e.Key switch
        {
            "ArrowUp" => SizeAsync(Shown - step),
            "ArrowDown" => SizeAsync(Shown + step),
            "Home" => SizeAsync(MinHeight),
            "End" => SizeAsync(MaxHeight),
            "Enter" or " " => SizeAsync(null),
            _ => Task.CompletedTask,
        };
    }

    [GeneratedRegex(@"\{\{\s*([A-Za-z_]\w*)\s*\}\}")]
    private static partial Regex NamePattern();

    public async ValueTask DisposeAsync()
    {
        try
        {
            if (_design is not null)
            {
                await _design.InvokeVoidAsync("stop");
                await _design.DisposeAsync();
            }
            if (_module is not null)
            {
                await _module.DisposeAsync();
            }
        }
        catch (JSDisconnectedException)
        {
            // the page is going
        }
        _self?.Dispose();
    }
}
