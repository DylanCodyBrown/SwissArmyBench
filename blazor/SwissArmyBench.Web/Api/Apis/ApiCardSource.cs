namespace SwissArmyBench.Web.Api.Apis;

/// <summary>Where an API's document came from: an address, a file, the form or a paste; when read; whether it is checked for changes.</summary>
public sealed record ApiCardSource(string Kind, string? Address = null, string? ReadAt = null, bool Check = false);
