namespace SwissArmyBench.Web.State;

/// <summary>
/// The page's short messages (the classic toast(): info only, a few seconds) and the error notes of background work
/// that has no place on screen (errorToast). The layout draws them in the corner.
/// </summary>
public sealed class Notes
{
    private const int ShownMilliseconds = 4000;

    private readonly List<Note> _shown = [];

    public event Action? Changed;

    public IReadOnlyList<Note> Shown => _shown;

    /// <summary>A short line that goes by itself ("Copied.", "Saved.").</summary>
    public async Task SayAsync(string words)
    {
        var note = new Note(words, null);
        _shown.Add(note);
        Changed?.Invoke();
        await Task.Delay(ShownMilliseconds);
        Dismiss(note);
    }

    /// <summary>A short line with one action ("Closed orders" with Undo): it goes by itself unless pressed.</summary>
    public async Task SayAsync(string words, string actionLabel, Func<Task> action)
    {
        var note = new Note(words, null, actionLabel, action);
        _shown.Add(note);
        Changed?.Invoke();
        await Task.Delay(ShownMilliseconds * 2);
        Dismiss(note);
    }

    /// <summary>An error from work with no place on screen: it stays until closed.</summary>
    public void Error(Exception error)
    {
        _shown.Add(new Note(null, error));
        Changed?.Invoke();
    }

    public void Dismiss(Note note)
    {
        if (_shown.Remove(note))
        {
            Changed?.Invoke();
        }
    }
}
