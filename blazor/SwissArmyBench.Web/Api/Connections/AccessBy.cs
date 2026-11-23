namespace SwissArmyBench.Web.Api.Connections;

/// <summary>What one app registration that signs the connection in reaches, when and where it was checked.</summary>
public sealed record AccessBy(
    string Registration,
    string Checked,
    string Computer,
    string Line,
    IReadOnlyList<AccessItem> Items);
