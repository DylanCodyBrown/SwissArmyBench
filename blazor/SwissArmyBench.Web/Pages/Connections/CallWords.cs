using SwissArmyBench.Web.Api.Connections;

namespace SwissArmyBench.Web.Pages.Connections;

/// <summary>A connection's calls in words (the classic callsWord and callFigures.ts): "12 calls · 3 min ago ·
/// usually 140 ms"; "No calls yet".</summary>
public static class CallWords
{
    private const int SecondsInMinute = 60;
    private const int SecondsInHour = 3600;

    /// <summary>The kinds of call, in the classic page's words and order.</summary>
    public static readonly IReadOnlyList<(string Kind, string Label)> Kinds =
    [
        ("catalog", "Catalog loads"),
        ("query", "Queries"),
        ("read", "Table reads"),
        ("test", "Tests"),
        ("connect", "Connects"),
    ];

    public static string Of(CallsInfo? calls)
    {
        if (calls is null || calls.Total == 0)
        {
            return "No calls yet";
        }
        var words = $"{calls.Total:N0} call{(calls.Total == 1 ? string.Empty : "s")}";
        if (calls.LastUsed is { } last)
        {
            words += $" · {Ago(last)}";
        }
        if (calls.Figures?.P50 is { } usual)
        {
            words += $" · usually {usual:0} ms";
        }
        return words;
    }

    /// <summary>How long ago a time (seconds since 1970) was: just now, 3 min ago, 2 h ago.</summary>
    public static string Ago(double seconds)
    {
        var passed = Math.Max(0, DateTimeOffset.UtcNow.ToUnixTimeSeconds() - seconds);
        if (passed < SecondsInMinute)
        {
            return "just now";
        }
        return passed < SecondsInHour ? $"{(int)(passed / SecondsInMinute)} min ago" : $"{(int)(passed / SecondsInHour)} h ago";
    }
}
