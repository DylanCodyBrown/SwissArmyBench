namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>What fills a bound place: a column of the group's row, text, the number or the date.</summary>
public sealed record BindingValue
{
    public string? Column { get; init; }

    public string? Text { get; init; }

    public bool? Number { get; init; }

    public bool? Date { get; init; }
}
