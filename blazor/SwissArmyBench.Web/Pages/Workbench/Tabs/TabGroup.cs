namespace SwissArmyBench.Web.Pages.Workbench.Tabs;

/// <summary>A group of tabs (VS Code's editor group): its documents' keys in their order and the one in front.</summary>
public sealed class TabGroup : LayoutNode
{
    public TabGroup(int id) => Id = id;

    public int Id { get; }

    public List<int> Tabs { get; } = [];

    public int? Active { get; set; }
}
