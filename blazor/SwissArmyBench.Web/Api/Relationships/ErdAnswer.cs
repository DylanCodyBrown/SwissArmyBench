namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>GET /relationships/erd: the model as Mermaid erDiagram text.</summary>
public sealed record ErdAnswer(string Mermaid = "", IReadOnlyList<string>? Tables = null);
