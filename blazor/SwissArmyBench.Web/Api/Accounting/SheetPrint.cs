namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>A sheet's print setup.</summary>
public sealed record SheetPrint
{
    public string? Orientation { get; init; }

    public string? Paper { get; init; }

    public bool? FitWidth { get; init; }

    public string? Header { get; init; }

    public string? Footer { get; init; }
}
