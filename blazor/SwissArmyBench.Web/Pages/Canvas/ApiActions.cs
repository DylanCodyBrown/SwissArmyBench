namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>
/// The one action picker's rules for any API (the classic actionPicker.ts): an action is "GET /orders" (the
/// project's local sandbox API's endpoint) or "[Orders] GET /orders" (the library's API called Orders); grouped by
/// their API, the local sandbox API first.
/// </summary>
public static class ApiActions
{
    public const string LocalApi = "Local sandbox API";

    /// <summary>An action's API and its own words: "[Orders] GET /orders" is Orders and "GET /orders".</summary>
    public static (string Api, string Words) Parts(string reference)
    {
        if (reference.StartsWith('[') && reference.IndexOf("] ", StringComparison.Ordinal) is var close and > 1)
        {
            return (reference[1..close], reference[(close + 2)..]);
        }
        return (LocalApi, reference);
    }

    /// <summary>The actions grouped by their API (the local sandbox API first, then by name).</summary>
    public static IReadOnlyList<IGrouping<string, string>> Groups(IEnumerable<string> references) => references
        .GroupBy(r => Parts(r).Api)
        .OrderByDescending(g => g.Key == LocalApi)
        .ThenBy(g => g.Key, StringComparer.Ordinal)
        .ToList();

    /// <summary>Whether an action only reads (a GET): an In's source takes these.</summary>
    public static bool ReadsOnly(string reference) => Parts(reference).Words.StartsWith("GET ", StringComparison.Ordinal);
}
