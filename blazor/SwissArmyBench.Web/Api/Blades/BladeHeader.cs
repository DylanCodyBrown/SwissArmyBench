namespace SwissArmyBench.Web.Api.Blades;

/// <summary>GET /blades/{name}/header: the header's fields for the blade's kind.</summary>
public sealed record BladeHeader(string Name, string Kind, IReadOnlyList<BladeField> Fields);
