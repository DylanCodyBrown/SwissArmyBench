using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Widgets;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>
/// The widgets' rendered previews (the classic canvasGallery.ts [PREVIEWS]): one per widget file and theme
/// (server/previews.py), asked for as a box shows it (the board's first), looked at again while it is coming, a
/// failure asked again once the server's back-off is over. Each box draws what is known and listens to Changed.
/// </summary>
public sealed class WidgetPreviews : IDisposable
{
    // The slow look while a preview is coming (its notice usually comes first), growing to six seconds.
    private const int FirstWaitMs = 2000;
    private const int WaitGrowsMs = 1000;
    private const int LongestWaitMs = 6000;
    private const int FailedAgainSeconds = 30;

    private readonly WidgetsClient _widgets;
    private readonly Dictionary<string, PreviewState> _known = [];
    private readonly HashSet<string> _asking = [];
    private readonly CancellationTokenSource _stop = new();

    public WidgetPreviews(WidgetsClient widgets)
    {
        _widgets = widgets;
    }

    public event Action? Changed;

    /// <summary>A preview needs a package this Python lacks: the page asks once (the one missing-package prompt).</summary>
    public Func<PreviewState, Task>? OnMissing { get; set; }

    /// <summary>The theme the pictures are drawn in ("light" or "dark").</summary>
    public string Theme { get; set; } = "light";

    public PreviewState? Of(string name) => _known.GetValueOrDefault(Key(name));

    /// <summary>A box shows this widget: its preview asked for unless it is known (board: one the board shows first).</summary>
    public void Want(string name, bool board, bool retry = false)
    {
        var key = Key(name);
        if (name.Length == 0 || (!retry && _known.TryGetValue(key, out var known) && known.State != "coming") || (!retry && _asking.Contains(key)))
        {
            return;
        }
        if (retry)
        {
            _known[key] = new PreviewState { State = "coming" };
            Changed?.Invoke();
        }
        _ = AskAsync(name, key, board, retry);
    }

    /// <summary>The server's word: one made or failed (asked again), or every failure may be tried again.</summary>
    public void Heard(string type, string? name, string? theme)
    {
        if (type == "widget_preview" && name is not null && theme == Theme)
        {
            _known[Key(name)] = new PreviewState { State = "coming" };
            Want(name, board: false);
        }
        else if (type == "widget_previews")
        {
            RetryFailed();
        }
    }

    /// <summary>What a preview needs, installed (the project's Python when the server says so, else the app's own),
    /// then every failed preview asked for again.</summary>
    public async Task InstallAsync(PreviewState said)
    {
        if (said.Missing is not { } missing)
        {
            return;
        }
        if (said.Install == "project")
        {
            await _widgets.InstallIntoProjectAsync(missing.Packages);
        }
        else
        {
            await _widgets.InstallIntoAppAsync(missing.Packages);
        }
        RetryFailed();
    }

    /// <summary>Every failed preview asked for again (an install just ended).</summary>
    public void RetryFailed()
    {
        var failed = _known.Where(k => k.Key.StartsWith(Theme + "\0", StringComparison.Ordinal) && k.Value.State == "failed").Select(k => k.Key[(Theme.Length + 1)..]).ToList();
        failed.ForEach(name => Want(name, board: false, retry: true));
    }

    /// <summary>Every preview forgotten (the widgets changed: each is asked for again as its box shows).</summary>
    public void Clear()
    {
        _known.Clear();
        Changed?.Invoke();
    }

    public void Dispose()
    {
        _stop.Cancel();
        _stop.Dispose();
    }

    private string Key(string name) => $"{Theme}\0{name}";

    private async Task AskAsync(string name, string key, bool board, bool retry)
    {
        _asking.Add(key);
        try
        {
            var wait = FirstWaitMs;
            var again = retry;
            while (!_stop.IsCancellationRequested)
            {
                PreviewState said;
                try
                {
                    said = await _widgets.PreviewAsync(name, Theme, board, again);
                }
                catch (ApiException)
                {
                    said = new PreviewState { State = "failed", Said = "The preview could not be asked for.", Kind = "setup", RetryIn = FailedAgainSeconds / 2 };
                }
                again = false;
                if (!key.StartsWith(Theme + "\0", StringComparison.Ordinal))
                {
                    return; // the theme changed meanwhile: the new theme's is asked for
                }
                _known[key] = said;
                Changed?.Invoke();
                if (said.State == "failed")
                {
                    if (said.Missing is not null && OnMissing is not null)
                    {
                        await OnMissing(said);
                    }
                    _ = AgainLaterAsync(name, key, said.RetryIn ?? FailedAgainSeconds);
                    return;
                }
                if (said.State != "coming")
                {
                    return;
                }
                await Task.Delay(wait, _stop.Token);
                wait = Math.Min(LongestWaitMs, wait + WaitGrowsMs);
            }
        }
        catch (OperationCanceledException)
        {
            // the page closed
        }
        finally
        {
            _asking.Remove(key);
        }
    }

    private async Task AgainLaterAsync(string name, string key, double seconds)
    {
        try
        {
            await Task.Delay(TimeSpan.FromSeconds(Math.Max(1, seconds)), _stop.Token);
        }
        catch (OperationCanceledException)
        {
            return;
        }
        if (_known.GetValueOrDefault(key)?.State == "failed")
        {
            _known.Remove(key);
            Want(name, board: false);
        }
    }
}
