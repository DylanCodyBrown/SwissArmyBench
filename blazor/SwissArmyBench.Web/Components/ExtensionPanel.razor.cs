using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Panels;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Components;

public partial class ExtensionPanel : IDisposable
{
    // While the panel says it is busy, it is read again this often.
    private const int BusyLookMs = 2000;

    private readonly CancellationTokenSource _stop = new();
    private PanelData? _data;
    private string? _failed;
    private bool _posting;
    private bool _looking;
    private (string Id, IReadOnlyList<string> Tables)? _plugin;

    [Inject]
    private PanelClient Panels { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    /// <summary>The panel's route (the backend's: GET /app/areas' or GET /extensions' panel).</summary>
    [Parameter, EditorRequired]
    public string Route { get; set; } = string.Empty;

    protected override async Task OnInitializedAsync()
    {
        Live.NoticeArrived += OnNotice;
        await LoadAsync();
    }

    private static string? Tone(string? tone) => string.IsNullOrEmpty(tone) ? null : $"tone-{tone}";

    private async Task LoadAsync()
    {
        try
        {
            Take(await Panels.ReadAsync(Route));
        }
        catch (ApiException error)
        {
            _failed = error.Refusal.Error;
        }
    }

    private Task ActAsync(string action) => PostAsync(new() { ["action"] = action });

    private async Task PostAsync(Dictionary<string, object?> body)
    {
        _posting = true;
        try
        {
            Take(await Panels.PostAsync(Route, body));
        }
        catch (ApiException error)
        {
            await LoadAsync();
            _failed = error.Refusal.Error;
        }
        finally
        {
            _posting = false;
        }
    }

    /// <summary>The panel as answered; a plug-in it opens, opened; while busy, read again in a moment.</summary>
    private void Take(PanelData data)
    {
        _data = data;
        _failed = null;
        if (data.Open is { } open)
        {
            if (PluginDialog.Known.Contains(open.Plugin))
            {
                _plugin = (open.Plugin, TablesOf(open.Context));
            }
            else
            {
                _failed = "That part of the page is not here: reload the page.";
            }
        }
        if (data.Busy is not null && !_looking)
        {
            _ = LookAgainAsync();
        }
    }

    private static IReadOnlyList<string> TablesOf(JsonElement? context) =>
        context is { ValueKind: JsonValueKind.Array } list ? list.EnumerateArray().Select(t => t.GetString() ?? string.Empty).ToList() : [];

    private async Task LookAgainAsync()
    {
        _looking = true;
        try
        {
            await Task.Delay(BusyLookMs, _stop.Token);
            await InvokeAsync(async () => { await LoadAsync(); StateHasChanged(); });
        }
        catch (TaskCanceledException)
        {
            // the panel left the page
        }
        finally
        {
            _looking = false;
        }
    }

    private async Task CopyAsync(string text)
    {
        var copied = await Js.InvokeAsync<bool>("sab.copy", text);
        if (copied)
        {
            await Notes.SayAsync("Copied.");
        }
        else
        {
            Notes.Error(new InvalidOperationException("The browser blocked the clipboard."));
        }
    }

    /// <summary>The page opens (https only) on the user's click, then its next step is posted.</summary>
    private async Task OpenPageAsync(PanelCode code)
    {
        if (code.Link.StartsWith("https://", StringComparison.Ordinal))
        {
            await Js.InvokeVoidAsync("open", code.Link, "_blank", "noopener");
        }
        await ActAsync(code.Then);
    }

    private void OnNotice(Notice notice)
    {
        if (notice.Type == "extension_panel_changed")
        {
            _ = InvokeAsync(async () => { await LoadAsync(); StateHasChanged(); });
        }
    }

    public void Dispose()
    {
        Live.NoticeArrived -= OnNotice;
        _stop.Cancel();
        _stop.Dispose();
    }
}
