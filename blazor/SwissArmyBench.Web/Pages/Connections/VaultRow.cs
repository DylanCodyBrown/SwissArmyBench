using System.Text.RegularExpressions;

namespace SwissArmyBench.Web.Pages.Connections;

/// <summary>One secret of a key vault on its form: whether it is used, and the variable typed for it (empty: the
/// vault's own name, EnvFor).</summary>
public sealed partial class VaultRow
{
    private const int MaxName = 128;

    public VaultRow(string secret, string variable, bool use)
    {
        Secret = secret;
        Variable = variable;
        Use = use;
    }

    public string Secret { get; }

    public string Variable { get; set; }

    public bool Use { get; set; }

    /// <summary>A secret's variable, named as in the vault (domain/blades.py env_name_for_secret): SqlPassword stays,
    /// Sql--Password as Sql__Password, warehouse-password as warehouse_password.</summary>
    public static string EnvFor(string secret)
    {
        var words = NotName().Replace(Scheme().Replace(secret.Trim(), string.Empty).Replace("--", "__", StringComparison.Ordinal), "_").Trim('_');
        words = words.Length == 0 ? "SECRET" : words[..Math.Min(words.Length, MaxName)];
        var named = char.IsDigit(words[0]) ? $"_{words}" : words;
        return named[..Math.Min(named.Length, MaxName)];
    }

    [GeneratedRegex("^[a-z][a-z0-9+.-]*://", RegexOptions.IgnoreCase)]
    private static partial Regex Scheme();

    [GeneratedRegex("[^A-Za-z0-9_]")]
    private static partial Regex NotName();
}
