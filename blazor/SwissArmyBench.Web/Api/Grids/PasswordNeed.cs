namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A connection's password with no source on this computer, in words.</summary>
public sealed record PasswordNeed(string? Message = null);
