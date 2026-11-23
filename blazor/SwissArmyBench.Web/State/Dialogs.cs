namespace SwissArmyBench.Web.State;

/// <summary>
/// The app's own questions (the classic dom.ts askYesNo and askText): a page awaits the answer, the layout's
/// DialogHost draws the one open question. One at a time; a second waits for the first.
/// </summary>
public sealed class Dialogs
{
    private readonly SemaphoreSlim _one = new(1, 1);
    private TaskCompletionSource<string?>? _answer;

    public event Action? Changed;

    /// <summary>The question on screen now, or null.</summary>
    public Question? Open { get; private set; }

    /// <summary>A yes or no: true when the user pressed the yes button.</summary>
    public async Task<bool> AskYesNoAsync(string title, string words, string yes, bool danger = false) =>
        await AskAsync(new Question(title, words, yes, Danger: danger)) is not null;

    /// <summary>Words typed in a box, or null when the user cancelled.</summary>
    public Task<string?> AskTextAsync(string title, string words, string asks, string value = "", string yes = "OK") =>
        AskAsync(new Question(title, words, yes, asks, value));

    /// <summary>The dialog's answer: the text (empty for a yes), or null for Cancel.</summary>
    public void Answer(string? answer)
    {
        Open = null;
        Changed?.Invoke();
        _answer?.TrySetResult(answer);
    }

    private async Task<string?> AskAsync(Question question)
    {
        await _one.WaitAsync();
        try
        {
            _answer = new TaskCompletionSource<string?>();
            Open = question;
            Changed?.Invoke();
            return await _answer.Task;
        }
        finally
        {
            _one.Release();
        }
    }
}
