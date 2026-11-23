namespace SwissArmyBench.Web.Api.Blades;

/// <summary>GET /blades/new: New blade's choices.</summary>
public sealed record BladeChoices(IReadOnlyList<BladeChoice> Choices);
