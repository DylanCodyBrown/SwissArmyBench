namespace SwissArmyBench.Web.State;

/// <summary>The grid's selection in the status bar (Excel's Count, Sum and Average, the classic status bar's): the
/// Grids page sets it as the selection changes and clears it when it closes.</summary>
public sealed class GridStatus
{
    public event Action? Changed;

    /// <summary>"Count 5 · Sum 1,240 · Average 248", or null when nothing is selected.</summary>
    public string? Words { get; private set; }

    /// <summary>The rows in the view ("120 rows", "40 rows (120 in orders)"), or null away from a grid.</summary>
    public string? Rows { get; private set; }

    /// <summary>The step previewed (the status bar's "· previewing after step N"), or null.</summary>
    public int? Preview { get; private set; }

    public void SetPreview(int? upto)
    {
        if (upto == Preview)
        {
            return;
        }
        Preview = upto;
        Changed?.Invoke();
    }

    /// <summary>The data budget's words while it is past the warning line ("2.6 GiB of 3.0 GiB of data"), else null;
    /// and the share used (the meter's width).</summary>
    public string? Budget { get; private set; }

    public int BudgetShare { get; private set; }

    public void SetBudget(string? words, int share)
    {
        if (words == Budget && share == BudgetShare)
        {
            return;
        }
        (Budget, BudgetShare) = (words, share);
        Changed?.Invoke();
    }

    public void SetRows(string? rows)
    {
        if (rows == Rows)
        {
            return;
        }
        Rows = rows;
        Changed?.Invoke();
    }

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
