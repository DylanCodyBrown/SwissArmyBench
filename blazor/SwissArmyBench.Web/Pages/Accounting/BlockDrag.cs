namespace SwissArmyBench.Web.Pages.Accounting;

/// <summary>A block being moved (or, with Sizing, sized by its corner): where the pointer went down and where the
/// block is shown now, in cells.</summary>
public sealed record BlockDrag(
    string Id,
    bool Sizing,
    double StartX,
    double StartY,
    int Row,
    int Column,
    int W,
    int H)
{
    public bool Moved { get; init; }
}
