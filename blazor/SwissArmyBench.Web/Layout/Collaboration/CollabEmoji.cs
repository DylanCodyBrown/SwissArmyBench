namespace SwissArmyBench.Web.Layout.Collaboration;

/// <summary>The composer's `:` list: an emoji by its name, as Slack names them (":tada" finds 🎉).</summary>
public static class CollabEmoji
{
    private const int MostShown = 8;

    public static readonly IReadOnlyList<(string Name, string Emoji)> All =
    [
        ("+1", "👍"), ("thumbsup", "👍"), ("-1", "👎"), ("tada", "🎉"), ("eyes", "👀"), ("white_check_mark", "✅"),
        ("heavy_check_mark", "✔️"), ("x", "❌"), ("heart", "❤️"), ("smile", "😄"), ("joy", "😂"), ("thinking", "🤔"),
        ("pray", "🙏"), ("rocket", "🚀"), ("fire", "🔥"), ("warning", "⚠️"), ("bug", "🐛"), ("memo", "📝"),
        ("chart", "📈"), ("bar_chart", "📊"), ("calendar", "📅"), ("question", "❓"), ("exclamation", "❗"),
        ("clap", "👏"), ("wave", "👋"), ("ok_hand", "👌"), ("100", "💯"), ("star", "⭐"), ("bulb", "💡"),
        ("lock", "🔒"), ("hourglass", "⏳"), ("coffee", "☕"),
    ];

    /// <summary>The emojis whose name starts with the words typed after `:` (then those that hold them).</summary>
    public static IReadOnlyList<(string Name, string Emoji)> Matching(string typed)
    {
        var words = typed.ToLowerInvariant();
        return All
            .Where(e => e.Name.Contains(words, StringComparison.Ordinal))
            .OrderBy(e => e.Name.StartsWith(words, StringComparison.Ordinal) ? 0 : 1)
            .ThenBy(e => e.Name, StringComparer.Ordinal)
            .Take(MostShown)
            .ToList();
    }
}
