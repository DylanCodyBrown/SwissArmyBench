using System.Text.Json;
using System.Text.RegularExpressions;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Api.Variables;
using SwissArmyBench.Web.Navigation;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Layout.Tour;

public partial class TourHost : IAsyncDisposable
{
    // How long a card waits for its control before it says it is not here; a connection's first form loads its
    // kinds first, so it waits longer.
    private const int WaitMilliseconds = 2500;
    private const int FormWaitMilliseconds = 15000;
    private const int HintMilliseconds = 8000;

    // The made-up variable the practice boxes offer, added for the tour when this computer has none of that name and
    // removed when it ends (like its tables).
    private const string PracticeVariable = "TOUR_WAREHOUSE_HOST";
    private const string PracticeValue = "warehouse.example.com";

    private static readonly Regex _namesVariable = new(@"(^|[^$])\$\{[A-Za-z_][A-Za-z0-9_]*(:-[^}]*)?\}");

    private IReadOnlyList<TourStop> _stops = [];
    private int _index;
    private int _serial;
    private bool _notHere;
    private bool _aimPending;
    private bool _shown;
    private string _startUrl = string.Empty;
    private Task<TourTables?>? _staging;
    private readonly List<string> _opened = [];
    private Task? _sorted;
    private Task<bool>? _practiceMade;
    private bool _practiceReady;
    private bool _practiceDone;
    private bool _hint;
    private string _said = string.Empty;
    private string? _reads;
    private ElementReference _root;
    private ElementReference _card;
    private ElementReference _spot;
    private ElementReference _next;
    private ElementReference _practiceBox;
    private IJSObjectReference? _module;
    private IJSObjectReference? _handle;
    private DotNetObjectReference<TourHost>? _self;

    [Inject]
    private TourState Tour { get; set; } = default!;

    [Inject]
    private RailState Rail { get; set; } = default!;

    [Inject]
    private ApiClient Api { get; set; } = default!;

    [Inject]
    private GridsClient Grids { get; set; } = default!;

    [Inject]
    private VariablesClient Variables { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    private IReadOnlyList<TourStop> Stops => _stops;

    private TourStop? Current => _index < _stops.Count ? _stops[_index] : null;

    private bool Last => _index == _stops.Count - 1;

    private bool NextBlocked => Current?.Practice is not null && !_practiceDone;

    protected override void OnInitialized() => Tour.Changed += OnTourChanged;

    private void OnTourChanged() => _ = InvokeAsync(StartOrStopAsync);

    private async Task StartOrStopAsync()
    {
        if (Tour.Open && !_shown)
        {
            _shown = true;
            _stops = TourStops.All.Where(s => s.RailOnly is null || (s.RailOnly == Areas.Canvas && Rail.CanvasOn)).ToList();
            _startUrl = Nav.Uri;
            _opened.Clear();
            _sorted = null;
            _practiceMade = null;
            _staging = TourTables.StageAsync(Api, name => _opened.Add(name));
            _index = 0;
            _aimPending = true;
            ResetPractice();
        }
        StateHasChanged();
    }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (!Tour.Open || !_aimPending)
        {
            return;
        }
        _aimPending = false;
        if (_handle is null)
        {
            _self ??= DotNetObjectReference.Create(this);
            _module ??= await Js.InvokeAsync<IJSObjectReference>("import", "./js/tour.js");
            _handle = await _module.InvokeAsync<IJSObjectReference>("start", _root, _card, _spot, _self);
        }
        await AimAsync(++_serial);
    }

    /// <summary>A key heard on the window while the tour is open (tour.js): Right or Enter, Left, Escape.</summary>
    [JSInvokable("Key")]
    public async Task KeyAsync(string key)
    {
        switch (key)
        {
            case "Escape":
                await CloseAsync();
                break;
            case "ArrowRight" or "Enter" when !NextBlocked:
                await ShowAsync(_index + 1);
                break;
            case "ArrowLeft" when _index > 0:
                await ShowAsync(_index - 1);
                break;
            default:
                break;
        }
    }

    private async Task ShowAsync(int at)
    {
        if (at >= _stops.Count)
        {
            await CloseAsync();
            return;
        }
        _index = at;
        _notHere = false;
        ResetPractice();
        _aimPending = true;
        StateHasChanged();
        await Task.CompletedTask;
    }

    // Take the user to the card's place, then light up its control (the newest card only: a slower move for an
    // earlier card is dropped).
    private async Task AimAsync(int mine)
    {
        if (Current is not { } stop || _handle is null)
        {
            return;
        }
        if (stop.Practice is not null)
        {
            await _next.FocusAsync();
            _ = PracticeAsync(mine);
        }
        else
        {
            await _next.FocusAsync();
        }
        await _handle.InvokeVoidAsync("aim", Array.Empty<string>(), 0);
        await GoToAsync(stop);
        if (mine != _serial || stop.Targets is not { } targets)
        {
            return;
        }
        var staged = _staging is null ? null : await _staging;
        var selectors = targets.Select(t => t.Replace("{orders}", staged?.Orders.Grid ?? string.Empty)).ToArray();
        var found = await _handle.InvokeAsync<bool>("aim", selectors, WaitMilliseconds);
        if (mine == _serial)
        {
            _notHere = !found;
            StateHasChanged();
        }
    }

    private async Task GoToAsync(TourStop stop)
    {
        if (stop.Area is { } area && Areas.All.FirstOrDefault(a => a.Area == area) is { } rail)
        {
            Nav.NavigateTo(rail.Route.Length == 0 ? "./" : rail.Route);
        }
        else if (stop.Form is { } kind && _handle is not null)
        {
            // A made-up connection's form, never saved: the tour's close goes back past it.
            Nav.NavigateTo($"connections?add=1&kind={ApiClient.Part(kind)}");
            await _handle.InvokeVoidAsync("typeInto", ".connection-field[data-field=\"server\"]", stop.Code ?? string.Empty, FormWaitMilliseconds);
        }
        else if (stop.Grid is { } grid && _staging is not null && await _staging is { } staged)
        {
            // The orders' sort for the Steps card, once, so there is a step to see.
            _sorted ??= SortAsync(staged.Orders.Grid);
            await _sorted;
            Nav.NavigateTo(grid == "pair"
                ? $"tables?grid={ApiClient.Part(staged.Orders.Grid)}&split={ApiClient.Part($"{staged.Orders.Grid},{staged.Customers.Grid}")}"
                : $"tables?grid={ApiClient.Part(staged.Orders.Grid)}");
        }
    }

    private async Task SortAsync(string grid)
    {
        try
        {
            await Grids.AddStepAsync(grid, "sort", new { keys = new[] { new[] { "amount", "desc" } } });
        }
        catch (ApiException)
        {
            // No sort: the Steps card shows an empty strip.
        }
    }

    // ===== the practice cards =====

    private void ResetPractice()
    {
        _practiceReady = false;
        _practiceDone = false;
        _hint = false;
        _said = string.Empty;
        _reads = null;
    }

    private async Task PracticeAsync(int mine)
    {
        _practiceMade ??= StagePracticeAsync();
        await _practiceMade;
        if (mine != _serial)
        {
            return;
        }
        _practiceReady = true;
        StateHasChanged();
        await Task.Yield();
        await _practiceBox.FocusAsync();
        await Task.Delay(HintMilliseconds);
        if (mine == _serial && !_practiceDone)
        {
            _hint = true;
            _said = Current?.Practice == "type" ? "Type a dollar sign, then an opening brace." : "Right-click inside the box.";
            StateHasChanged();
        }
    }

    private async Task<bool> StagePracticeAsync()
    {
        try
        {
            if ((await Variables.OfferedAsync()).Any(v => v.Name == PracticeVariable))
            {
                return false;
            }
            await Api.PutAsync("/variables", new { name = PracticeVariable, value = PracticeValue, from = "value" });
            return true;
        }
        catch (ApiException)
        {
            return false;
        }
    }

    private async Task PracticeTypedAsync(ChangeEventArgs e)
    {
        var text = e.Value?.ToString() ?? string.Empty;
        if (_practiceDone || !_namesVariable.IsMatch(text))
        {
            return;
        }
        _practiceDone = true;
        _hint = false;
        _said = "It worked. Here it reads:";
        try
        {
            var read = await Api.PostAsync<JsonElement>("/variables/resolve", new { text });
            _reads = read.TryGetProperty("value", out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : string.Empty;
        }
        catch (ApiException)
        {
            _reads = null;
        }
        await _next.FocusAsync();
    }

    // ===== the end =====

    private async Task CloseAsync()
    {
        if (!Tour.Open)
        {
            return;
        }
        _serial++;
        if (_handle is not null)
        {
            await _handle.InvokeVoidAsync("stop");
            await _handle.DisposeAsync();
            _handle = null;
        }
        Tour.Close();
        _shown = false;
        // Back where the tour started first, so a closed table's tab never takes the user anywhere.
        Nav.NavigateTo(_startUrl);
        if (_practiceMade is not null && await _practiceMade)
        {
            await QuietlyAsync(() => Api.DeleteAsync($"/variables/{PracticeVariable}"));
        }
        if (_staging is not null)
        {
            await _staging;
        }
        foreach (var name in _opened.ToList())
        {
            await QuietlyAsync(() => Grids.CloseAsync(name));
        }
        _opened.Clear();
    }

    private static async Task QuietlyAsync(Func<Task> work)
    {
        try
        {
            await work();
        }
        catch (ApiException)
        {
            // The tour's own made-up things: one already gone is fine.
        }
    }

    public async ValueTask DisposeAsync()
    {
        Tour.Changed -= OnTourChanged;
        if (_handle is not null)
        {
            await _handle.InvokeVoidAsync("stop");
            await _handle.DisposeAsync();
        }
        if (_module is not null)
        {
            await _module.DisposeAsync();
        }
        _self?.Dispose();
        GC.SuppressFinalize(this);
    }
}
