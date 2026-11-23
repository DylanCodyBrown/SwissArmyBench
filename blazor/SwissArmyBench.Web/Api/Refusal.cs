namespace SwissArmyBench.Web.Api;

/// <summary>The server's one refusal shape (design principle 9.5, domain/refusals.py).</summary>
/// <param name="Error">What happened, in one plain sentence.</param>
/// <param name="Where">The connection, table, file or cell, by name.</param>
/// <param name="Fixes">The fixes the server knows, as buttons.</param>
/// <param name="Details">The source's own words, folded behind Details.</param>
public sealed record Refusal(string Error, string? Where = null, IReadOnlyList<Fix>? Fixes = null, string? Details = null);
