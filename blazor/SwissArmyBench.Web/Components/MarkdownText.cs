using System.Net;
using System.Text;
using System.Text.RegularExpressions;

namespace SwissArmyBench.Web.Components;

/// <summary>
/// A small, safe Markdown renderer (the classic markdown.ts, ported): headings, paragraphs, bullet and numbered
/// lists, task lists, GitHub tables, fenced code (its language kept for colouring), quotes, rules, **bold**, *italic*,
/// ~~struck~~, `code` and http(s) links; with <see cref="MarkdownLinks"/>, the Collaboration panel's object references
/// ([@orders](sab:table/orders)) and pasted pictures (![a chart](sab-image:1a2b-1.png)). Every piece of text is
/// HTML-encoded before a tag is put around it, so what a cell, a teammate or an agent writes never becomes markup.
/// </summary>
public static partial class MarkdownText
{
    private const int DeepestHeading = 4;

    // A list item this much further in than the one before it starts a list inside it.
    private const int NestIndent = 2;
    private const int TabIndent = 4;

    /// <summary>What a drawing is given: the Collaboration panel's links, a Markdown file's own parts, and the
    /// number the next task box gets.</summary>
    private sealed class Draw(MarkdownLinks? links, MarkdownOptions? options)
    {
        public MarkdownLinks? Links { get; } = links;

        public MarkdownOptions? Options { get; } = options;

        public int Tasks { get; set; }
    }

    public static string ToHtml(string source, MarkdownLinks? links = null, MarkdownOptions? options = null) =>
        ToHtml(source, new Draw(links, options));

    private static string ToHtml(string source, Draw links)
    {
        var html = new StringBuilder("<div class=\"note-body\">");
        var lines = source.Replace("\r\n", "\n").Split('\n');
        var paragraph = new List<string>();
        // The lists open, the outermost first: each one's indent and tag (a list inside an item nests).
        var lists = new List<(int Indent, string Tag)>();
        void Flush()
        {
            if (paragraph.Count > 0)
            {
                html.Append("<p>").Append(Inline(string.Join(' ', paragraph), links)).Append("</p>");
                paragraph.Clear();
            }
        }
        void EndList()
        {
            for (var open = lists.Count - 1; open >= 0; open--)
            {
                html.Append($"</li></{lists[open].Tag}>");
            }
            lists.Clear();
        }
        void Item(string raw, string tag, string attributes, string inner)
        {
            OpenItem(html, lists, Indent(raw), tag);
            html.Append($"<li{attributes}>").Append(inner);
        }
        for (var at = 0; at < lines.Length; at++)
        {
            var line = lines[at].TrimEnd();
            if (Block(lines, at, links) is var (used, isBlock) && isBlock)
            {
                Flush();
                EndList();
                html.Append(used.Html);
                at += used.Lines - 1;
            }
            else if (Heading().Match(line) is { Success: true } heading)
            {
                Flush();
                EndList();
                var level = Math.Min(DeepestHeading, heading.Groups[1].Length);
                html.Append($"<h{level}>").Append(Inline(heading.Groups[2].Value, links)).Append($"</h{level}>");
            }
            else if (TaskItem().Match(line) is { Success: true } task)
            {
                Flush();
                var done = task.Groups[1].Value is "x" or "X" ? " checked" : string.Empty;
                // A Markdown file's own task box is live (its number told on a click); anywhere else it only shows.
                var live = links.Options is { Tasks: true } ? $" data-task=\"{links.Tasks++}\"" : " disabled";
                Item(lines[at], "ul", " class=\"md-task\"", $"<input type=\"checkbox\"{live}{done} aria-label=\"{(done.Length > 0 ? "Done" : "To do")}\"> " + Inline(task.Groups[2].Value, links));
            }
            else if (Bullet().Match(line) is { Success: true } bullet)
            {
                Flush();
                Item(lines[at], "ul", string.Empty, Inline(bullet.Groups[1].Value, links));
            }
            else if (Numbered().Match(line) is { Success: true } numbered)
            {
                Flush();
                Item(lines[at], "ol", string.Empty, Inline(numbered.Groups[1].Value, links));
            }
            else if (line.Trim().Length == 0)
            {
                Flush();
                EndList();
            }
            else
            {
                EndList();
                paragraph.Add(line.Trim());
            }
        }
        Flush();
        EndList();
        return html.Append("</div>").ToString();
    }

    /// <summary>A block that spans lines (fenced code, a table, a quote) or a rule, at a line: its markup and how
    /// many lines it took; not a block, false.</summary>
    private static ((string Html, int Lines) Used, bool IsBlock) Block(string[] lines, int at, Draw links)
    {
        var line = lines[at].TrimEnd();
        if (Fence().Match(line) is { Success: true } fence)
        {
            var code = lines.Skip(at + 1).TakeWhile(l => !Fence().IsMatch(l)).ToList();
            var language = fence.Groups[1].Value.ToLowerInvariant();
            var lang = language.Length > 0 ? $" data-lang=\"{WebUtility.HtmlEncode(language)}\"" : string.Empty;
            return (($"<pre class=\"md-code\"><code{lang}>{WebUtility.HtmlEncode(string.Join('\n', code))}</code></pre>", code.Count + 2), true);
        }
        if (line.Contains('|') && at + 1 < lines.Length && RuleRow().IsMatch(lines[at + 1]))
        {
            var block = lines.Skip(at).TakeWhile((l, i) => i < 2 || (l.Contains('|') && l.Trim().Length > 0)).ToList();
            return ((Table(block, links), block.Count), true);
        }
        if (HorizontalRule().IsMatch(line))
        {
            return (("<hr>", 1), true);
        }
        if (Quote().IsMatch(line))
        {
            var quote = lines.Skip(at).TakeWhile(l => Quote().IsMatch(l)).Select(l => Quote().Replace(l, string.Empty, 1)).ToList();
            return (($"<blockquote>{Inline(string.Join(' ', quote), links)}</blockquote>", quote.Count), true);
        }
        return ((string.Empty, 0), false);
    }

    private static int Indent(string line) =>
        line.TakeWhile(c => c is ' ' or '\t').Sum(c => c == '\t' ? TabIndent : 1);

    /// <summary>The list an item belongs to opened (or found): further in than the item before it, a list inside
    /// that item; back out, the inner lists closed; another kind of list at the same depth, a new one.</summary>
    private static void OpenItem(StringBuilder html, List<(int Indent, string Tag)> lists, int indent, string tag)
    {
        while (lists.Count > 0 && lists[^1].Indent >= indent + NestIndent)
        {
            html.Append($"</li></{lists[^1].Tag}>");
            lists.RemoveAt(lists.Count - 1);
        }
        if (lists.Count > 0 && indent < lists[^1].Indent + NestIndent)
        {
            html.Append("</li>");
            if (lists[^1].Tag == tag)
            {
                return;
            }
            html.Append($"</{lists[^1].Tag}>");
            indent = lists[^1].Indent;
            lists.RemoveAt(lists.Count - 1);
        }
        lists.Add((indent, tag));
        html.Append($"<{tag}>");
    }

    /// <summary>Bold, italic, struck, code, links, references, pictures and backslash escapes inside a line; the rest
    /// encoded as text.</summary>
    private static string Inline(string text, Draw links)
    {
        var html = new StringBuilder();
        var last = 0;
        foreach (Match token in InlineToken().Matches(text))
        {
            html.Append(Plain(text[last..token.Index]));
            html.Append(token.Value switch
            {
                ['\\', var escaped] => WebUtility.HtmlEncode(escaped.ToString()),
                ['*', '*', ..] => $"<strong>{Inline(token.Value[2..^2], links)}</strong>",
                ['~', '~', ..] => $"<del>{Inline(token.Value[2..^2], links)}</del>",
                ['`', ..] => $"<code>{WebUtility.HtmlEncode(token.Value[1..^1])}</code>",
                ['!', ..] when PictureParts().IsMatch(token.Value) => Picture(token.Value, links),
                ['!', ..] => Image(token.Value, links),
                ['[', '@', ..] when ReferenceParts().Match(token.Value) is { Success: true } reference => Reference(reference, links),
                ['[', ..] when LinkParts().IsMatch(token.Value) => Link(token.Value, links),
                ['[', ..] => FileLink(token.Value, links),
                _ => $"<em>{Inline(token.Value[1..^1], links)}</em>",
            });
            last = token.Index + token.Length;
        }
        return html.Append(Plain(text[last..])).ToString();
    }

    private static string Link(string token, Draw links)
    {
        var link = LinkParts().Match(token);
        var href = WebUtility.HtmlEncode(link.Groups[2].Value);
        return $"<a href=\"{href}\" target=\"_blank\" rel=\"noopener noreferrer\">{Inline(link.Groups[1].Value, links)}</a>";
    }

    /// <summary>A picture by its address (a Markdown file's own: beside the file): the reader's markup, else its
    /// words as they were written.</summary>
    private static string Image(string token, Draw links)
    {
        var image = ImageParts().Match(token);
        return links.Options?.Image?.Invoke(WebUtility.HtmlDecode(image.Groups[1].Value), image.Groups[2].Value) ?? Plain(token);
    }

    /// <summary>A link that is not a web address (another file of the project): the reader's markup, else as written.</summary>
    private static string FileLink(string token, Draw links)
    {
        var link = FileLinkParts().Match(token);
        return links.Options?.Link?.Invoke(Inline(link.Groups[1].Value, links), link.Groups[2].Value)
            ?? $"[{Inline(link.Groups[1].Value, links)}]({Plain(link.Groups[2].Value)})";
    }

    /// <summary>An object reference: the resolver's markup, else its words as text.</summary>
    private static string Reference(Match reference, Draw links)
    {
        var (label, kind) = (WebUtility.HtmlDecode(reference.Groups[1].Value), reference.Groups[2].Value);
        var path = Uri.UnescapeDataString(reference.Groups[3].Value);
        var id = Uri.UnescapeDataString(reference.Groups[4].Value);
        return links.Links?.Reference(label, kind, path, id) ?? $"<span class=\"md-ref\">@{WebUtility.HtmlEncode(label)}</span>";
    }

    private static string Picture(string token, Draw links)
    {
        var picture = PictureParts().Match(token);
        var alt = WebUtility.HtmlDecode(picture.Groups[1].Value);
        return links.Links?.Picture(alt, picture.Groups[2].Value) ?? WebUtility.HtmlEncode(alt);
    }

    // The references HTML's escaping writes (&lt; &amp;...) show as their characters, then everything is encoded.
    private static string Plain(string text) => WebUtility.HtmlEncode(WebUtility.HtmlDecode(text));

    private static string Table(IReadOnlyList<string> lines, Draw links)
    {
        var head = Cells(lines[0]);
        var rows = lines.Skip(2).Select(Cells).ToList();
        var numeric = head
            .Select((_, i) => rows.Count > 0 && rows.All(r => i >= r.Count || r[i].Length == 0 || NumberCell().IsMatch(r[i].Replace("**", string.Empty))))
            .ToList();
        string Cell(string tag, string text, int i) => $"<{tag} class=\"align-{(numeric[i] ? "right" : "left")}\">{Inline(text, links)}</{tag}>";
        var header = string.Concat(head.Select((c, i) => Cell("th", c, i)));
        var body = string.Concat(rows.Select(r => $"<tr>{string.Concat(head.Select((_, i) => Cell("td", i < r.Count ? r[i] : string.Empty, i)))}</tr>"));
        return $"<div class=\"md-table-wrap\"><table class=\"md-table\"><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>";
    }

    private static List<string> Cells(string line) =>
        TableBar().Split(line.Trim().TrimStart('|').TrimEnd('|'))
            .Select(c => c.Trim().Replace("\\|", "|"))
            .ToList();

    [GeneratedRegex(@"^\s*```\s*([A-Za-z0-9_+-]*)")]
    private static partial Regex Fence();

    [GeneratedRegex(@"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")]
    private static partial Regex RuleRow();

    [GeneratedRegex(@"^\s*(---|\*\*\*|___)\s*$")]
    private static partial Regex HorizontalRule();

    [GeneratedRegex(@"^\s*>\s?")]
    private static partial Regex Quote();

    [GeneratedRegex(@"^(#{1,6})\s+(.*)$")]
    private static partial Regex Heading();

    [GeneratedRegex(@"^\s*[-*]\s+(.*)$")]
    private static partial Regex Bullet();

    [GeneratedRegex(@"^\s*[-*]\s+\[([ xX])\]\s+(.*)$")]
    private static partial Regex TaskItem();

    [GeneratedRegex(@"^\s*\d+[.)]\s+(.*)$")]
    private static partial Regex Numbered();

    [GeneratedRegex(@"(\\[!-/:-@\[-`{-~]|\*\*(?:\\.|[^*\\])+\*\*|~~(?:\\.|[^~\\])+~~|\*(?:\\.|[^*\\])+\*|`[^`]+`|!\[[^\]\n]*\]\(sab-image:[a-z0-9-]+\.(?:png|jpg|gif|webp)\)|\[@[^\]\n]{1,200}\]\(sab:[a-z]+/[^)#\s]*(?:#[^)\s]*)?\)|\[(?:\\.|[^\]\\])+\]\(https?://[^)\s]+\)|!\[[^\]\n]*\]\([^)\s]+\)|\[(?:\\.|[^\]\\])+\]\([^)\s]+\))")]
    private static partial Regex InlineToken();

    [GeneratedRegex(@"^!\[([^\]\n]*)\]\(([^)\s]+)\)$")]
    private static partial Regex ImageParts();

    [GeneratedRegex(@"^\[(.+)\]\(([^)\s]+)\)$")]
    private static partial Regex FileLinkParts();

    [GeneratedRegex(@"^\[@([^\]\n]{1,200})\]\(sab:([a-z]+)/([^)#\s]*)(?:#([^)\s]*))?\)$")]
    private static partial Regex ReferenceParts();

    [GeneratedRegex(@"^!\[([^\]\n]*)\]\(sab-image:([a-z0-9-]+\.(?:png|jpg|gif|webp))\)$")]
    private static partial Regex PictureParts();

    [GeneratedRegex(@"^\[(.+)\]\((https?://[^)\s]+)\)$")]
    private static partial Regex LinkParts();

    [GeneratedRegex(@"(?<!\\)\|")]
    private static partial Regex TableBar();

    [GeneratedRegex(@"^[-+]?[$€£]?[\d.,]+(%|[a-zA-Z]{0,3})?$")]
    private static partial Regex NumberCell();
}
