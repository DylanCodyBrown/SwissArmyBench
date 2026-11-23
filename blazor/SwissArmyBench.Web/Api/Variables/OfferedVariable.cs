namespace SwissArmyBench.Web.Api.Variables;

/// <summary>A variable as a `${` list offers it (GET /variables): its name and its source in words, never a value.</summary>
/// <param name="Name">The variable's name (SALES_REGION).</param>
/// <param name="Words">Where it comes from, in words ("Plain value", "Key vault").</param>
/// <param name="Secret">A secret: its value is never shown.</param>
/// <param name="Vault">A vault's variable: the vault's own name.</param>
public sealed record OfferedVariable(string Name, string Words, bool Secret, string? Vault = null)
{
    /// <summary>The source in words, a vault's own name with it ("Key vault · Finance").</summary>
    public string Source => Vault is { Length: > 0 } vault ? $"{Words} · {vault}" : Words;
}
