namespace SwissArmyBench.Web.State;

/// <summary>The grid's selection in the status bar (Excel's Count, Sum and Average, the classic status bar's): the
/// Grids page sets it as the selection changes and clears it when it closes.</summary>
public sealed class GridStatus
{
    public event Action? Changed;

    /// <summary>"Count 5 · Sum 1,240 · Average 248", or null when nothing is selected.</summary>
    public string? Words { get; private set; }

    public void Set(string? words)
    {
        if (words == Words)
        {
            return;
        }
        Words = words;
        Changed?.Invoke();
    }
}
