namespace SwissArmyBench.Web.Api.Sandbox;

/// <summary>POST /sandbox/tables/variant: the variant made, its title and rows.</summary>
public sealed record MadeVariant(string Added, long Rows, string Title);
