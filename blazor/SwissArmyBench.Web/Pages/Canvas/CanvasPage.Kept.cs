using System.Text.Json;

using Microsoft.JSInterop;

using SwissArmyBench.Web.Api.Widgets;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>What this browser keeps for a canvas (its panes, layout and zoom: a convenience), and the one
/// missing-package prompt a preview asks once.</summary>
public partial class CanvasPage
{
    private async Task AskInstallAsync(PreviewState said)
    {
        if (said.Missing is not { } missing || _askedInstall.Contains(string.Join(' ', missing.Packages)))
        {
            return;
        }
        _askedInstall.Add(string.Join(' ', missing.Packages));
        var words = $"{missing.Feature} needs {string.Join(", ", missing.Packages)}.";
        if (await Dialogs.AskYesNoAsync(words, $"{words} Install it into {missing.Python}?", "Install now"))
        {
            await _previews.InstallAsync(said);
        }
    }

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
