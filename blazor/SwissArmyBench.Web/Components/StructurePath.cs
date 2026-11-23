using System.Text.RegularExpressions;

namespace SwissArmyBench.Web.Components;

/// <summary>A place in a structure as the app writes it (the classic structurePaths.ts): $.orders[3].amount, a key
/// that is not a plain name in brackets ($["order date"]).</summary>
public static partial class StructurePath
{
    public const string Root = "$";

    public static string Key(string parent, string key) =>
        PlainName().IsMatch(key) ? $"{parent}.{key}" : $"{parent}[{System.Text.Json.JsonSerializer.Serialize(key)}]";

    public static string Index(string parent, int index) => $"{parent}[{index}]";

    [GeneratedRegex("^[A-Za-z_][A-Za-z0-9_]*$")]
    private static partial Regex PlainName();
}
