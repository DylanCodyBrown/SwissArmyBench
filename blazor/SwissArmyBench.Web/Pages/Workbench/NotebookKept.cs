namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>A notebook's cells as they are on screen, kept with its document (not its view), so the notebook stays as
/// it was when its tab moves to another group or window part and its view is drawn again.</summary>
public sealed class NotebookKept
{
    public List<CellModel> Cells { get; set; } = [];

    public int NextCell { get; set; } = 1;

    /// <summary>Its cells were read from the file once; a view drawn again takes them as they are.</summary>
    public bool Started { get; set; }
}
