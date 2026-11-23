namespace SwissArmyBench.Web.Api.Projects;

/// <summary>A connection or blade another place offers to import (into this computer's library).</summary>
public sealed record ImportItem(string Name, string? Description = null, string? Kind = null);
