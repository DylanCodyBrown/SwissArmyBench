namespace SwissArmyBench.Web.Api.Connections;

/// <summary>POST /blades/fill: the code with a value written in, and its fields read again.</summary>
public sealed record FilledCode(IReadOnlyList<FormField> Settings, string Code);
