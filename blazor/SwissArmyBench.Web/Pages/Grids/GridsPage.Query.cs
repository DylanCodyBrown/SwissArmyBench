namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>
/// A new query is a new SQL file on the Scripts page (the owner, 2026-11-24: "sql authorship will have one place in
/// scripts and not on the grid menu"): the "+", Ctrl+T and Ctrl+N go there (its New file dialog asks the file's name
/// first: the owner, 2026-11-27), and an old address (tables?new=1, the
/// New query page that went) lands there too. A table a query made shows its query here with Edit in Scripts.
/// </summary>
public partial class GridsPage
{
    private bool IsNewQuery => NewParameter is not null;

    /// <summary>tables?new=1 (a bookmark, an old link): the new SQL file on the Scripts page, this address replaced.</summary>
    private bool LeftForNewQuery()
    {
        if (!IsNewQuery)
        {
            return false;
        }
        Nav.NavigateTo(Query.TablesEmpty.NewQueryAddress, replace: true);
        return true;
    }
}
