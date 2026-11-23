using System.Globalization;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;


namespace SwissArmyBench.Web.Layout;

public partial class FooterMarks : IAsyncDisposable
{
    private static readonly double[] _steps = [0.7, 0.8, 0.9, 1, 1.1, 1.25, 1.4, 1.6, 1.8, 2];

    private double _zoom = 1;
    private DotNetObjectReference<FooterMarks>? _self;
    private IJSObjectReference? _keys;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    protected override async Task OnInitializedAsync()
    {
        var kept = await Js.InvokeAsync<string?>("sab.recall", "zoom");
        _zoom = double.TryParse(kept, NumberStyles.Float, CultureInfo.InvariantCulture, out var z) ? z : 1;
        await Js.InvokeVoidAsync("sab.setZoom", _zoom);
    }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (firstRender)
        {
            _self = DotNetObjectReference.Create(this);
            _keys = await Js.InvokeAsync<IJSObjectReference>("sab.zoomKeys", _self);
        }
    }

    /// <summary>Ctrl+=, Ctrl+- or Ctrl+0 (and Ctrl + wheel), from shell.js.</summary>
    [JSInvokable]
    public Task Zoom(int by) => by == 0 ? SetAsync(1) : StepAsync(by);

    private Task StepAsync(int by)
    {
        var at = Array.FindIndex(_steps, s => s >= _zoom - 0.001);
        var next = _steps[Math.Clamp((at < 0 ? _steps.Length - 1 : at) + by, 0, _steps.Length - 1)];
        return SetAsync(next);
    }

    private async Task SetAsync(double zoom)
    {
        _zoom = zoom;
        await Js.InvokeVoidAsync("sab.setZoom", zoom);
        await Js.InvokeVoidAsync("sab.remember", "zoom", zoom.ToString(CultureInfo.InvariantCulture));
        StateHasChanged();
    }

    public async ValueTask DisposeAsync()
    {
        if (_keys is not null)
        {
            await _keys.InvokeVoidAsync("stop");
            await _keys.DisposeAsync();
        }
        _self?.Dispose();
        GC.SuppressFinalize(this);
    }
}
