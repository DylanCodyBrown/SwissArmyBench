namespace SwissArmyBench.Web.Api.Environment;

/// <summary>POST /environment/open: where the row opened (a table: its grid), or nothing to show.</summary>
public sealed record EnvironmentOpened(EnvironmentLink? Link);
