namespace SwissArmyBench.Web.State;

/// <summary>
/// "Set it" and "New variable…" (the classic variableLinks.ts addVariable): the Add variable form over whatever is
/// open, its name filled in, so a half-filled form stays as it was. The layout's VariableAskHost draws it; the box
/// or error note that asked gets the name once it is saved (null when the user cancelled).
/// </summary>
public sealed class VariableAsks
{
    private TaskCompletionSource<string?>? _answer;

    public event Action? Changed;

    /// <summary>The name the open form starts with, or null when no form is open.</summary>
    public string? Open { get; private set; }

    public Task<string?> AddAsync(string name)
    {
        _answer?.TrySetResult(null);
        _answer = new TaskCompletionSource<string?>();
        Open = name;
        Changed?.Invoke();
        return _answer.Task;
    }

    /// <summary>The form's answer: the variable added, or null for Cancel.</summary>
    public void Answer(string? added)
    {
        Open = null;
        Changed?.Invoke();
        _answer?.TrySetResult(added);
    }
}
