using System.Globalization;
using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Settings;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Layout;

public partial class FooterMarks : IAsyncDisposable
{
    private static readonly double[] _steps = [0.7, 0.8, 0.9, 1, 1.1, 1.25, 1.4, 1.6, 1.8, 2];

    private UpdatesStatus? _updates;
    private bool _beta;
    private double _zoom = 1;
    private (string Title, IReadOnlyList<MenuEntry> Entries, double X, double Y)? _menu;
    private IReadOnlyList<ClaudeHelp>? _missing;
    private DotNetObjectReference<FooterMarks>? _self;
    private IJSObjectReference? _keys;

    [Inject]
    private SettingsClient Settings { get; set; } = default!;

    [Inject]
    private ApiClient Api { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    protected override async Task OnInitializedAsync()
    {
        try
        {
            _updates = await Settings.UpdatesAsync();
            _beta = (await Settings.BetaAsync()).On;
        }
        catch (ApiException)
        {
            // The marks are conveniences: the footer works without them.
        }
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

    private void UpdateMenu(Microsoft.AspNetCore.Components.Web.MouseEventArgs e)
    {
        if (_updates is not { } update)
        {
            return;
        }
        List<MenuEntry> entries = [new($"Update to {update.Version}", "export", () => Settings.UpdateAsync(update.Version ?? string.Empty))];
        if (update.Url is { } url)
        {
            entries.Add(new("What's new", "info", () => Js.InvokeVoidAsync("open", url, "_blank").AsTask()));
        }
        _menu = ("Update available", entries, e.ClientX, e.ClientY - 80);
    }

    private void BetaMenu(Microsoft.AspNetCore.Components.Web.MouseEventArgs e) =>
        _menu = ("Beta mode",
        [
            new("Leave a note…", "edit", LeaveNoteAsync),
            new("Export beta log…", "export", () => { Nav.NavigateTo("settings"); return Task.CompletedTask; }),
            new("Turn off beta mode", "exclude", async () => _beta = (await Settings.SetBetaAsync(false)).On),
        ], e.ClientX, e.ClientY - 120);

    private async Task LeaveNoteAsync()
    {
        if (await Dialogs.AskTextAsync("Leave a note", "What happened, in your words (it goes in the beta log).", "Note") is { Length: > 0 } note)
        {
            await Settings.BetaNoteAsync(note);
            _ = Notes.SayAsync("Noted.");
        }
    }

    /// <summary>Launch Claude (the classic claudeLaunch.ts): the one found; a choice when both are; the install help
    /// when none is; the server's question when it asks before writing.</summary>
    private async Task LaunchAsync(string? app, double x, double y, bool confirmed = false)
    {
        JsonElement answer;
        try
        {
            answer = await Api.PostAsync<JsonElement>("/claude/launch", app is null ? (confirmed ? new { confirmed } : new { }) : new { app, confirmed });
        }
        catch (ApiException error)
        {
            Notes.Error(error);
            return;
        }
        if (answer.TryGetProperty("choose", out var choose) && choose.ValueKind == JsonValueKind.True)
        {
            _menu = ("Launch Claude", [new("Claude Code in a terminal", "claude", () => LaunchAsync("code", x, y)), new("Claude Desktop", "claude", () => LaunchAsync("desktop", x, y))], x, y - 80);
        }
        else if (answer.TryGetProperty("missing", out var missing) && missing.ValueKind == JsonValueKind.Array)
        {
            _missing = missing.Deserialize<List<ClaudeHelp>>(ApiClient.Json);
        }
        else if (answer.TryGetProperty("confirm", out var confirm) && confirm.ValueKind != JsonValueKind.Null)
        {
            if (await Dialogs.AskYesNoAsync("Launch Claude", confirm.ValueKind == JsonValueKind.String ? confirm.GetString()! : "Claude Desktop's settings get the Swiss Army Bench server (a backup first).", "OK"))
            {
                await LaunchAsync(app, x, y, confirmed: true);
            }
        }
        else if (answer.TryGetProperty("error", out var error) && error.ValueKind == JsonValueKind.String)
        {
            _ = Notes.SayAsync(error.GetString()!);
        }
        else if (answer.TryGetProperty("launched", out var launched))
        {
            var bypass = answer.TryGetProperty("bypass", out var b) && b.ValueKind == JsonValueKind.True;
            var terminal = answer.TryGetProperty("terminal", out var t) && t.ValueKind == JsonValueKind.String ? t.GetString() : "a terminal";
            var changed = answer.TryGetProperty("changed", out var c) && c.ValueKind == JsonValueKind.True;
            _ = Notes.SayAsync(launched.GetString() == "code"
                ? $"Claude Code started in {terminal}{(bypass ? " (bypass permissions)" : string.Empty)}."
                : changed ? "Claude Desktop started. If it was already open, quit it and start it again to load Swiss Army Bench." : "Claude Desktop started.");
        }
    }

    private static string Named(string kind) => kind == "code" ? "Claude Code" : "Claude Desktop";

    private async Task CopyAsync(string text)
    {
        if (await Js.InvokeAsync<bool>("sab.copy", text))
        {
            _ = Notes.SayAsync("Copied.");
        }
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
