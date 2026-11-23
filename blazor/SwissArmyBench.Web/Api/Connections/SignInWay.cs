namespace SwissArmyBench.Web.Api.Connections;

/// <summary>One way a connection signs in: its words, the text only its code holds (Mark), its code, what only this computer has.</summary>
public sealed record SignInWay(
    string Label,
    string Mark,
    string Code,
    IReadOnlyList<LocalNote>? Local = null,
    string? Note = null);
