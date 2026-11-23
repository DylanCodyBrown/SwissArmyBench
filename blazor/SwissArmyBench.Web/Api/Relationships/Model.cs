namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>GET /relationships: the current model's relationships.</summary>
public sealed record Model(IReadOnlyList<Join> Relationships, bool CanUndo = false);
