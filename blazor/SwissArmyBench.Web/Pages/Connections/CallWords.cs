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
        if (calls.Figures is { Count: > 0, P50: { } usual })
        {
            words += $" · usually {Ms(usual)}";
        }
        return words;
    }

    /// <summary>140 ms, 1.2 s, 2 min.</summary>
    public static string Ms(double ms) => ms switch
    {
        < 1000 => $"{Math.Round(ms):0} ms",
        < 10_000 => $"{ms / 1000:0.0} s",
        < 60_000 => $"{ms / 1000:0} s",
        _ => $"{Math.Round(ms / 60_000):0} min",
    };

    /// <summary>Every figure in words, one a line: the card's hover.</summary>
    public static string? Title(CallFigures? f) => f is not { Count: > 0 } ? null : string.Join("\n", new[]
    {
        $"{f.Count:N0} call{(f.Count == 1 ? string.Empty : "s")} in this project",
        $"Usually {Ms(f.P50 ?? 0)}; 1 in 20 over {Ms(f.P95 ?? 0)}",
        f.WaitP95 > 0 ? $"Waited for a slot up to {Ms(f.WaitP95)}" : string.Empty,
        f.Rows > 0 ? $"Typically {f.Rows:N0} rows" : string.Empty,
        f.Pages > 1 ? $"Typically {f.Pages} pages" : string.Empty,
        f.Errors > 0 ? $"{f.Errors} failed ({Math.Round(f.ErrorRate * 100):0}%)" : string.Empty,
    }.Where(line => line.Length > 0));

    /// <summary>The figures as the detail's Calls terms.</summary>
    public static IReadOnlyList<(string Name, string Value)> Terms(CallFigures? f) => f is not { Count: > 0 } ? [] : new[]
    {
        ("Usual time", $"{Ms(f.P50 ?? 0)} (1 in 20 over {Ms(f.P95 ?? 0)})"),
        ("Typical rows", f.Rows > 0 ? $"{f.Rows:N0}" : string.Empty),
        ("Waited for a slot", f.WaitP95 > 0 ? $"up to {Ms(f.WaitP95)}" : string.Empty),
        ("Failed", f.Errors > 0 ? $"{f.Errors} of {f.Count:N0}" : string.Empty),
    }.Where(t => t.Item2.Length > 0).ToList();

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
