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

    public static string ToHtml(string source, MarkdownLinks? links = null)
    {
        var html = new StringBuilder("<div class=\"note-body\">");
        var lines = source.Replace("\r\n", "\n").Split('\n');
        var paragraph = new List<string>();
        string? list = null;
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
            if (list is not null)
            {
                html.Append($"</{list}>");
                list = null;
            }
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
                list = OpenList(html, list, "ul");
                var done = task.Groups[1].Value is "x" or "X" ? " checked" : string.Empty;
                html.Append($"<li class=\"md-task\"><input type=\"checkbox\" disabled{done} aria-label=\"{(done.Length > 0 ? "Done" : "To do")}\"> ")
                    .Append(Inline(task.Groups[2].Value, links)).Append("</li>");
            }
            else if (Bullet().Match(line) is { Success: true } bullet)
            {
                Flush();
                list = OpenList(html, list, "ul");
                html.Append("<li>").Append(Inline(bullet.Groups[1].Value, links)).Append("</li>");
            }
            else if (Numbered().Match(line) is { Success: true } numbered)
            {
                Flush();
                list = OpenList(html, list, "ol");
                html.Append("<li>").Append(Inline(numbered.Groups[1].Value, links)).Append("</li>");
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
    private static ((string Html, int Lines) Used, bool IsBlock) Block(string[] lines, int at, MarkdownLinks? links)
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

    private static string OpenList(StringBuilder html, string? open, string wanted)
    {
        if (open == wanted)
        {
            return wanted;
        }
        if (open is not null)
        {
            html.Append($"</{open}>");
        }
        html.Append($"<{wanted}>");
        return wanted;
    }

    /// <summary>Bold, italic, struck, code, links, references, pictures and backslash escapes inside a line; the rest
    /// encoded as text.</summary>
    private static string Inline(string text, MarkdownLinks? links)
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
                ['!', ..] => Picture(token.Value, links),
                ['[', '@', ..] when ReferenceParts().Match(token.Value) is { Success: true } reference => Reference(reference, links),
                ['[', ..] => Link(token.Value, links),
                _ => $"<em>{Inline(token.Value[1..^1], links)}</em>",
            });
            last = token.Index + token.Length;
        }
        return html.Append(Plain(text[last..])).ToString();
    }

    private static string Link(string token, MarkdownLinks? links)
    {
        var link = LinkParts().Match(token);
        var href = WebUtility.HtmlEncode(link.Groups[2].Value);
        return $"<a href=\"{href}\" target=\"_blank\" rel=\"noopener noreferrer\">{Inline(link.Groups[1].Value, links)}</a>";
    }

    /// <summary>An object reference: the resolver's markup, else its words as text.</summary>
    private static string Reference(Match reference, MarkdownLinks? links)
    {
        var (label, kind) = (WebUtility.HtmlDecode(reference.Groups[1].Value), reference.Groups[2].Value);
        var path = Uri.UnescapeDataString(reference.Groups[3].Value);
        var id = Uri.UnescapeDataString(reference.Groups[4].Value);
        return links?.Reference(label, kind, path, id) ?? $"<span class=\"md-ref\">@{WebUtility.HtmlEncode(label)}</span>";
    }

    private static string Picture(string token, MarkdownLinks? links)
    {
        var picture = PictureParts().Match(token);
        var alt = WebUtility.HtmlDecode(picture.Groups[1].Value);
        return links?.Picture(alt, picture.Groups[2].Value) ?? WebUtility.HtmlEncode(alt);
    }

    // The references HTML's escaping writes (&lt; &amp;...) show as their characters, then everything is encoded.
    private static string Plain(string text) => WebUtility.HtmlEncode(WebUtility.HtmlDecode(text));

    private static string Table(IReadOnlyList<string> lines, MarkdownLinks? links)
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

    [GeneratedRegex(@"(\\[!-/:-@\[-`{-~]|\*\*(?:\\.|[^*\\])+\*\*|~~(?:\\.|[^~\\])+~~|\*(?:\\.|[^*\\])+\*|`[^`]+`|!\[[^\]\n]*\]\(sab-image:[a-z0-9-]+\.(?:png|jpg|gif|webp)\)|\[@[^\]\n]{1,200}\]\(sab:[a-z]+/[^)#\s]*(?:#[^)\s]*)?\)|\[(?:\\.|[^\]\\])+\]\(https?://[^)\s]+\))")]
    private static partial Regex InlineToken();

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
