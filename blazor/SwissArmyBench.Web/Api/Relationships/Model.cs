namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>GET /relationships: the current model's name, its tables (their primary keys) and its relationships.</summary>
public sealed record Model(
    IReadOnlyList<Join> Relationships,
    bool CanUndo = false,
    string Name = "current",
    IReadOnlyDictionary<string, ModelTable>? Tables = null);
