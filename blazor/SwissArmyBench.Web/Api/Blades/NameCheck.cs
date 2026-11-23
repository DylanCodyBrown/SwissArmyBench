namespace SwissArmyBench.Web.Api.Blades;

/// <summary>A live check of a name (a new blade's, a table's): available, or why not.</summary>
public sealed record NameCheck(bool Available, string Said = "");
