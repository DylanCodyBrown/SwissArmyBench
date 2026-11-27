namespace SwissArmyBench.Web.State;

/// <summary>
/// What the page in front shows, for the agent's app_screen (the owner, 2026-11-27: "literally just feeding the
/// state back to the agent"; read on demand, never sent every turn). A page hooks in once (<see cref="Show"/>: a
/// reader of its own part, names only, never a value) and says when what it shows may have changed
/// (<see cref="Touch"/>, as cheap as raising an event: the reader runs only when Layout/ScreenReporter next sends,
/// a few times a second at most). Its value raises one Changed.
/// </summary>
public sealed class ScreenState
{
    private readonly Dictionary<object, Func<IReadOnlyDictionary<string, object?>>> _readers = [];

    public event Action? Changed;

    /// <summary>A page's part: `read` gives its keys of the screen state (domain/screen.py's names) when asked.</summary>
    public void Show(object page, Func<IReadOnlyDictionary<string, object?>> read)
    {
        _readers[page] = read;
        Changed?.Invoke();
    }

    /// <summary>A page leaving takes its part away (another page's stays).</summary>
    public void Hide(object page)
    {
        if (_readers.Remove(page))
        {
            Changed?.Invoke();
        }
    }

    /// <summary>What a page shows may have changed (it drew again).</summary>
    public void Touch() => Changed?.Invoke();

    /// <summary>Every page's part now, as one set of keys (a key with no value left out; the later reader's wins).</summary>
    public Dictionary<string, object?> Read() =>
        _readers.Values
            .SelectMany(read => read())
            .Where(part => part.Value is not null)
            .GroupBy(part => part.Key, StringComparer.Ordinal)
            .ToDictionary(group => group.Key, group => group.Last().Value, StringComparer.Ordinal);
}
