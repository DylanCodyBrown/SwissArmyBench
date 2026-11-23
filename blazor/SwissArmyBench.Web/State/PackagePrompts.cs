using System.Text.Json;

using SwissArmyBench.Web.Api;

namespace SwissArmyBench.Web.State;

/// <summary>
/// A missing package, said in the user's face (the classic missingPackages.ts, the owner 2026-11-16): one prompt for
/// every place that finds one. "Install &lt;package&gt;?", the feature's sentence, Not now and Install now. Not now
/// holds for this tab's session per package and Python (no nagging); the reminder (InstallReminder) opens it again.
/// The layout's PackagePromptHost draws the one open prompt.
/// </summary>
public sealed class PackagePrompts
{
    // An install's own output is long: its last lines say what went wrong (the classic installError).
    private const int OutputLines = 8;

    private readonly ApiClient _api;
    private readonly HashSet<string> _notNow = [];
    private readonly Dictionary<string, Task<bool>> _asked = [];
    private readonly SemaphoreSlim _one = new(1, 1);
    private TaskCompletionSource<bool>? _answer;

    public PackagePrompts(ApiClient api)
    {
        _api = api;
    }

    public event Action? Changed;

    /// <summary>The prompt on screen now, or null.</summary>
    public PackagePrompt? Open { get; private set; }

    /// <summary>Not now was said for every one of these packages this session.</summary>
    public bool Dismissed(MissingPackages missing) => missing.Packages.Count > 0 && KeysOf(missing).All(_notNow.Contains);

    /// <summary>
    /// The prompt. True once the packages are installed (and <paramref name="then"/> has run); false on Not now, or at
    /// once when Not now was said for them this session (unless <paramref name="force"/>: the user asked).
    /// </summary>
    public Task<bool> PromptAsync(MissingPackages missing, bool force = false, Func<MissingPackages, Task>? install = null, Func<Task>? then = null)
    {
        if (!force && Dismissed(missing))
        {
            return Task.FromResult(false);
        }
        var key = string.Join('\u0001', KeysOf(missing));
        if (_asked.TryGetValue(key, out var already))
        {
            return already;
        }
        var shown = ShowAsync(new PackagePrompt(missing, install ?? IntoAppAsync, then), key);
        _asked[key] = shown;
        return shown;
    }

    /// <summary>An error that names missing packages: the prompt, and true when it was one (the caller says nothing
    /// more).</summary>
    public bool PromptForError(Exception? error, Func<Task>? then = null)
    {
        if (MissingPackages.Of(error) is not { } missing)
        {
            return false;
        }
        _ = PromptAsync(missing, then: then);
        return true;
    }

    /// <summary>Install now: the packages installed (the host shows the progress); an error is thrown in plain words.</summary>
    public async Task InstallAsync(PackagePrompt prompt)
    {
        try
        {
            await prompt.Install(prompt.Missing);
        }
        catch (ApiException error)
        {
            throw new InvalidOperationException(InstallError(error), error);
        }
    }

    /// <summary>The prompt answered: installed, or Not now (closed any way but Install now).</summary>
    public void Answer(bool installed)
    {
        if (Open is { } prompt && !installed)
        {
            foreach (var key in KeysOf(prompt.Missing))
            {
                _notNow.Add(key);
            }
        }
        Open = null;
        Changed?.Invoke();
        _answer?.TrySetResult(installed);
    }

    private async Task<bool> ShowAsync(PackagePrompt prompt, string key)
    {
        await _one.WaitAsync();
        try
        {
            _answer = new TaskCompletionSource<bool>();
            Open = prompt;
            Changed?.Invoke();
            return await _answer.Task;
        }
        finally
        {
            _asked.Remove(key);
            _one.Release();
        }
    }

    private Task IntoAppAsync(MissingPackages missing) => _api.PostAsync("/blades/install", new { packages = missing.Packages });

    private static IEnumerable<string> KeysOf(MissingPackages missing) =>
        missing.Packages.Select(p => $"{missing.Python}\u0000{p.ToLowerInvariant()}");

    /// <summary>An install's failure in plain words: the last lines of its output when it answered with them.</summary>
    private static string InstallError(ApiException error)
    {
        try
        {
            using var parsed = JsonDocument.Parse(error.Body);
            var said = parsed.RootElement;
            var output = said.TryGetProperty("output", out var o) && o.ValueKind == JsonValueKind.String ? o.GetString()
                : said.TryGetProperty("error", out var e) && e.ValueKind == JsonValueKind.String ? e.GetString() : null;
            return string.IsNullOrWhiteSpace(output)
                ? "The install failed."
                : string.Join('\n', output.Trim().Split('\n').TakeLast(OutputLines));
        }
        catch (JsonException)
        {
            return string.IsNullOrWhiteSpace(error.Message) ? "The install failed." : error.Message;
        }
    }
}
