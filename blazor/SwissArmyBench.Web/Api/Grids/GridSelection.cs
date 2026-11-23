namespace SwissArmyBench.Web.Api.Grids;

/// <summary>
/// What is selected in the grid (told by agGrid.js as it changes): its kind (none, rows, columns, cells, all), the
/// server's descriptor, and the columns the Column tools act on (the selected ones, else the clicked cell's).
/// </summary>
public sealed record GridSelection(string Kind, SelectionDescriptor? Descriptor, IReadOnlyList<string> Target)
{
    public static readonly GridSelection None = new("none", null, []);
}
