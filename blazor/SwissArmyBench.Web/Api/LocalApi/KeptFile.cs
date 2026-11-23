namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>A file of an export edited by hand: kept, with the export's and yours.</summary>
public sealed record KeptFile(string File, string Theirs, string Yours);
