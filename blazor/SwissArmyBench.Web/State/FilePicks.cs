using SwissArmyBench.Web.Api.Files;

namespace SwissArmyBench.Web.State;

/// <summary>
/// The page's own file picker (the classic fileChooser.ts choosePage), used when this computer's own dialog cannot
/// open: one pick at a time, drawn by the layout's FilePickerHost; the caller awaits the path (null: cancelled).
/// </summary>
public sealed class FilePicks
{
    private readonly SemaphoreSlim _one = new(1, 1);
    private TaskCompletionSource<string?>? _answer;

    public event Action? Changed;

    /// <summary>The pick on screen now, or null.</summary>
    public ChooseRequest? Open { get; private set; }

    public async Task<string?> ChooseAsync(ChooseRequest request)
    {
        await _one.WaitAsync();
        try
        {
            _answer = new TaskCompletionSource<string?>();
            Open = request;
            Changed?.Invoke();
            return await _answer.Task;
        }
        finally
        {
            _one.Release();
        }
    }

    public void Answer(string? path)
    {
        Open = null;
        Changed?.Invoke();
        _answer?.TrySetResult(path);
    }
}
