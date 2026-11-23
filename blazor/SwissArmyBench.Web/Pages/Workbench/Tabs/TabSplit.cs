namespace SwissArmyBench.Web.Pages.Workbench.Tabs;

/// <summary>Nodes side by side (Row) or one over another (Column), each with its share of the room.</summary>
public sealed class TabSplit : LayoutNode
{
    public TabSplit(bool row) => Row = row;

    public bool Row { get; }

    public List<LayoutNode> Children { get; } = [];

    public List<double> Sizes { get; } = [];
}
