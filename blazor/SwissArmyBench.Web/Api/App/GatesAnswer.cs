namespace SwissArmyBench.Web.Api.App;

/// <summary>GET /app/gates: the areas a project type keeps closed, and Open every feature.</summary>
public sealed record GatesAnswer(IReadOnlyList<GateArea> Closed, bool Gated, bool Every, string Line = "", string? FirstOpen = null);
