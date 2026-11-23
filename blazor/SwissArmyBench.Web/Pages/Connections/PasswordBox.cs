using System.Text.RegularExpressions;

namespace SwissArmyBench.Web.Pages.Connections;

/// <summary>One password's box on a connection's form (design principle 12.7): a variable's reference, whose source
/// the Environment keeps (named in the code as secret("NAME")), or a value typed here, kept on Save as a keyring
/// variable. `Secret` is the name the code asks for now; `Label` the word the starter gave it.</summary>
public sealed partial class PasswordBox
{
    public PasswordBox(string secret)
    {
        Secret = secret;
        Label = secret;
        Text = LooksLikeVariable(secret) ? Named(secret) : string.Empty;
        Settled = Text;
    }

    public string Secret { get; set; }

    public string Label { get; }

    /// <summary>What the box holds now.</summary>
    public string Text { get; set; }

    /// <summary>The text last settled (a box left or changed settles it once).</summary>
    public string Settled { get; set; }

    /// <summary>A typed password (not a variable), to be kept in the keyring on Save.</summary>
    public bool Typed => Text.Length > 0 && !NamesVariable(Text);

    /// <summary>A reference reads as text; a typed password stays hidden.</summary>
    public string InputType => Text.Contains("${", StringComparison.Ordinal) ? "text" : "password";

    /// <summary>A variable's reference as it is typed in a box.</summary>
    public static string Named(string variable) => "$" + "{" + variable + "}";

    /// <summary>A secret's name that is already a variable's (WAREHOUSE_PASSWORD).</summary>
    public static bool LooksLikeVariable(string name) => VariableName().IsMatch(name) && name.Any(char.IsUpper);

    /// <summary>Text that names a variable somewhere in it (an escaped one is text).</summary>
    public static bool NamesVariable(string text) => Reference().IsMatch(text.Replace("$$", string.Empty, StringComparison.Ordinal));

    /// <summary>The variable a box of one reference names, else null.</summary>
    public static string? ReferenceOnly(string text) => OnlyReference().Match(text.Trim()) is { Success: true } m ? m.Groups[1].Value : null;

    /// <summary>A typed password as it is kept: a doubled dollar before a reference is the reference's text.</summary>
    public static string TypedValue(string text) => Escaped().Replace(text, "$1");

    /// <summary>The variable a typed password is kept as (domain/connections.py env_name_for): SALES_DB_PASSWORD.</summary>
    public static string VariableFor(string connection, string label)
    {
        var made = NotWord().Replace($"{connection}_{label}", "_").Trim('_').ToUpperInvariant();
        return made.Length == 0 ? "PASSWORD" : char.IsDigit(made[0]) ? $"_{made}" : made;
    }

    [GeneratedRegex("^[A-Z_][A-Z0-9_]*$")]
    private static partial Regex VariableName();

    [GeneratedRegex(@"\$\{[A-Za-z_][A-Za-z0-9_]*(:-[^}]*)?\}")]
    private static partial Regex Reference();

    [GeneratedRegex(@"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")]
    private static partial Regex OnlyReference();

    [GeneratedRegex(@"\$(\$\{[A-Za-z_][A-Za-z0-9_]*(?::-[^}]*)?\})")]
    private static partial Regex Escaped();

    [GeneratedRegex("[^A-Za-z0-9]+")]
    private static partial Regex NotWord();
}
