using System.Globalization;
using System.Net;
using System.Text.RegularExpressions;

using SwissArmyBench.Web.Api.Collaboration;
using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Layout.Collaboration;

/// <summary>The Collaboration panel's words: when, who, a message's Markdown with its references and pictures, an
/// the filters and the quick reactions.</summary>
public static partial class CollabWords
{
    public const string GoneWords = "no longer in the project";

    private const int MinutesAnHour = 60;
    private const int HoursADay = 24;

    /// <summary>The filters in the panel's order: the server's name and the words on the chip.</summary>
    public static readonly IReadOnlyList<(string Filter, string Label)> Filters =
    [
        ("all", "All"),
        ("mentions", "Mentions"),
        ("page", "This page"),
        ("unresolved", "Unresolved"),
    ];

    /// <summary>The quick reactions (the composer's `:` finds the rest by name).</summary>
    public static readonly IReadOnlyList<string> QuickReactions = ["👍", "🎉", "👀", "✅", "❤️", "😄", "🙏", "🚀"];

    /// <summary>A time from the server (UTC) in words: now, minutes, today's clock, a day.</summary>
    public static string When(string time, DateTimeOffset now)
    {
        if (!DateTimeOffset.TryParse(time, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var at))
        {
            return time;
        }
        var ago = now - at;
        var local = at.ToLocalTime();
        return ago.TotalMinutes switch
        {
            < 1 => "just now",
            < MinutesAnHour => $"{(int)ago.TotalMinutes} min ago",
            _ when ago.TotalHours < HoursADay && local.Date == now.ToLocalTime().Date => local.ToString("HH:mm", CultureInfo.InvariantCulture),
            _ => local.ToString("d MMM, HH:mm", CultureInfo.InvariantCulture),
        };
    }

    /// <summary>A name's initials for its round mark ("Avery Lin": AL).</summary>
    public static string Initials(string name)
    {
        var parts = name.Split(' ', StringSplitOptions.RemoveEmptyEntries).Where(p => char.IsLetterOrDigit(p[0])).ToList();
        return parts.Count switch
        {
            0 => "?",
            1 => parts[0][..1].ToUpperInvariant(),
            _ => $"{parts[0][0]}{parts[^1][0]}".ToUpperInvariant(),
        };
    }

    /// <summary>A message's Markdown as markup: each reference a link to where its object lives (struck through when it
    /// is gone), each picture its image.</summary>
    public static string Body(CollabMessage message) =>
        Mentioned(MarkdownText.ToHtml(message.Body, Links(message.Thread, message.References)), message.Mentions);

    /// <summary>Each person a message mentions marked in its words (never inside a tag or code).</summary>
    public static string Mentioned(string html, IReadOnlyList<string> mentions)
    {
        if (mentions.Count == 0)
        {
            return html;
        }
        var people = string.Join('|', mentions.Select(Regex.Escape));
        var mention = new Regex($@"(?<![\w@/])@({people})\b");
        var inCode = 0;
        return string.Concat(Tags().Split(html).Select(part =>
        {
            if (part.StartsWith('<'))
            {
                inCode += part.StartsWith("<code", StringComparison.Ordinal) ? 1 : part.StartsWith("</code", StringComparison.Ordinal) ? -1 : 0;
                return part;
            }
            return inCode > 0 ? part : mention.Replace(part, "<span class=\"collab-mention\">@$1</span>");
        }));
    }

    public static MarkdownLinks Links(string thread, IReadOnlyList<CollabReference> references)
    {
        var known = references
            .GroupBy(r => Key(r.Kind, r.Path, r.Id))
            .ToDictionary(g => g.Key, g => g.First());
        string Reference(string label, string kind, string path, string id) =>
            Chip(known.GetValueOrDefault(Key(kind, path, id)), label);
        string Picture(string alt, string name) =>
            $"<img class=\"collab-picture\" src=\"{WebUtility.HtmlEncode(CollaborationClient.ImageAddress(thread, name))}\" alt=\"{WebUtility.HtmlEncode(alt)}\" loading=\"lazy\">";
        return new MarkdownLinks(Reference, Picture);
    }

    /// <summary>A reference as a chip: a link where its object opens, struck through when it is gone, plain words for a
    /// change (it shows in the panel).</summary>
    public static string Chip(CollabReference? reference, string label)
    {
        var words = WebUtility.HtmlEncode($"@{label}");
        if (reference is { Gone: true })
        {
            return $"<span class=\"collab-ref gone\" title=\"{GoneWords}\"><s>{words}</s> <span class=\"collab-gone\">({GoneWords})</span></span>";
        }
        if (reference?.Href is { Length: > 0 } href)
        {
            var kind = WebUtility.HtmlEncode(reference.Kind);
            return $"<a class=\"collab-ref\" data-kind=\"{kind}\" href=\"{WebUtility.HtmlEncode(href)}\" title=\"Open it\">{words}</a>";
        }
        return $"<span class=\"collab-ref\">{words}</span>";
    }

    /// <summary>Where a thread is, for its line: "#general", or the object it is on.</summary>
    public static string Place(CollabItem item) => item.Anchor is { } anchor ? $"@{anchor.Text}" : item.Where ?? string.Empty;

    private static string Key(string kind, string path, string id) => $"{kind}:{path}#{id}";

    [GeneratedRegex("(<[^>]+>)")]
    private static partial Regex Tags();
}
