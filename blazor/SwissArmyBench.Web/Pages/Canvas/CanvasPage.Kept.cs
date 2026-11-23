using System.Text.Json;

using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Widgets;
using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>What this browser keeps for a canvas (its layout and zoom; the panes' dock for every canvas: a
/// convenience), and the one missing-package prompt a preview pops up once.</summary>
public partial class CanvasPage
{
    /// <summary>Where the Canvas's panes are, kept in this browser (every canvas the same).</summary>
    private const string DockKey = "canvas.dock";

    private const string WidgetsPaneId = "widgets";
    private const string PropertiesPaneId = "properties";

    /// <summary>Visual Studio's places: the Widgets (the toolbox) on the left, Properties on the right.</summary>
    private static readonly DockLayout _defaultDock = new([new(WidgetsPaneId, DockSide.Left), new(PropertiesPaneId, DockSide.Right)]);

    // The one missing-package prompt pops up once a page for the same packages (Not now holds for the session).
    private readonly HashSet<string> _askedInstall = [];

    /// <summary>A preview needs a package this Python lacks: the one install prompt, by itself, once; Install now puts
    /// it where the server said (the project's Python or the app's own), then the failed previews are asked again.</summary>
    private async Task AskInstallAsync(PreviewState said)
    {
        if (said.Missing is not { } missing || !_askedInstall.Add(string.Join(' ', missing.Packages)))
        {
            return;
        }
        await InvokeAsync(() => Prompts.PromptAsync(missing, install: _ => _previews.InstallAsync(said)));
    }

    /// <summary>Play or Launch found the Python without Streamlit: the one install prompt (the user asked to run it),
    /// and the run again once it is in; Not now leaves a quiet line rather than an error.</summary>
    private async Task RunNeedsAsync(MissingPackages missing, string? place, Func<Task> again)
    {
        _error = null;
        _warning = $"{missing.Feature} will not work without {missing.Listed}.";
        StateHasChanged();
        await Prompts.PromptAsync(missing, force: true, install: m => WidgetsApi.InstallAsync(place, m.Packages), then: () => InvokeAsync(async () =>
        {
            _warning = null;
            await again();
        }));
    }

    private void OnDockChanged() => _ = InvokeAsync(StateHasChanged);

    private async Task<T?> RecallAsync<T>(string key)
        where T : class
    {
        var text = await Js.InvokeAsync<string?>("sab.recall", key);
        try
        {
            return text is null ? null : JsonSerializer.Deserialize<T>(text);
        }
        catch (JsonException)
        {
            return null;
        }
    }

    private Task RememberAsync(string key, object value) => Js.InvokeVoidAsync("sab.remember", key, JsonSerializer.Serialize(value)).AsTask();
}
