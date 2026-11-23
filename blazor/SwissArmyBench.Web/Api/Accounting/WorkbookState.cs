namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>A workbook's design as the server holds it (the Accounting extension's service.py): its file, the tables it reads, what is missing, Play's state and preview.</summary>
public sealed record WorkbookState
{
    public string Id { get; init; } = string.Empty;

    public string? Path { get; init; }

    public string Title { get; init; } = string.Empty;

    public WorkbookDesign Design { get; init; } = new();

    public IReadOnlyList<string> Tables { get; init; } = [];

    public IReadOnlyList<string> Missing { get; init; } = [];

    public IReadOnlyList<string> Problems { get; init; } = [];

    public bool Played { get; init; }

    public bool OutOfDate { get; init; }

    public string? Problem { get; init; }

    public bool Unsaved { get; init; }

    public WorkbookPreview? Preview { get; init; }

    public string? Sheet { get; init; }

    public string? Block { get; init; }

    public double? Modified { get; init; }
}
