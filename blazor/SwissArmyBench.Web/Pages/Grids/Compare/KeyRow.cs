namespace SwissArmyBench.Web.Pages.Grids.Compare;

/// <summary>One row of the key picker: a left column = right column pair, the Key Finder's numbers for it (% of each
/// side found, the shared values, the relationship it reads as; or why it is offered: "added by hand", "known
/// relationship"...), and whether it is a known relationship (the crown).</summary>
public sealed record KeyRow(
    string Left,
    string Right,
    string LeftFound,
    string RightFound,
    string Shared,
    string Relationship,
    bool Known)
{
    public string Id => $"{Left}\u0000{Right}";
}
