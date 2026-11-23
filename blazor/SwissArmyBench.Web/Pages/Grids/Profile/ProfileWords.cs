using System.Globalization;
using System.Text.Json;

namespace SwissArmyBench.Web.Pages.Grids.Profile;

/// <summary>How a profile says a value (the classic profileView.ts fmt): thousands separators, at most two decimals
/// (four significant digits below one), never scientific notation; a date without its midnight time; a blank as
/// "(blank)".</summary>
public static class ProfileWords
{
    private const string Midnight = " 00:00:00";

    public static string Of(JsonElement? value) => value switch
    {
        null or { ValueKind: JsonValueKind.Null or JsonValueKind.Undefined } => "(blank)",
        { ValueKind: JsonValueKind.Number } number => Of(number.GetDouble()),
        { ValueKind: JsonValueKind.String } text => Temporal(text.GetString() ?? string.Empty),
        { ValueKind: JsonValueKind.True } => "true",
        { ValueKind: JsonValueKind.False } => "false",
        { } other => other.GetRawText(),
    };

    public static string Of(double? value) => value switch
    {
        null => "(blank)",
        { } n when n == Math.Floor(n) && Math.Abs(n) < 1e15 => n.ToString("N0", CultureInfo.CurrentCulture),
        { } n when Math.Abs(n) < 1 => n.ToString("G4", CultureInfo.CurrentCulture),
        { } n => n.ToString("#,0.##", CultureInfo.CurrentCulture),
    };

    public static string Of(long? value) => value is { } n ? n.ToString("N0", CultureInfo.CurrentCulture) : "(blank)";

    /// <summary>A timestamp at midnight reads as its date; "2026-01-01T00:00:00" too.</summary>
    public static string Temporal(string text)
    {
        var plain = text.Replace('T', ' ');
        return plain.Length >= 19 && plain.EndsWith(Midnight, StringComparison.Ordinal) && char.IsDigit(plain[0]) ? plain[..10] : text;
    }
}
