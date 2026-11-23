namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>One table of the relationship model: its primary key's columns.</summary>
public sealed record ModelTable(IReadOnlyList<string>? PrimaryKey = null);
