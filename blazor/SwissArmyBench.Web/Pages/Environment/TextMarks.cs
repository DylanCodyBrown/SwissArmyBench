namespace SwissArmyBench.Web.Pages.Environment;

/// <summary>A text with the search's words marked (the classic environmentPage.ts marked): for each word the shortest
/// stretch whose letters and digits spell it, so "cust" marks the start of customer_id and of CustomerKey, as the
/// server matched it.</summary>
public static class TextMarks
{
    /// <summary>The text in parts, each marked or not, in order.</summary>
    public static IReadOnlyList<(string Text, bool Marked)> Of(string text, string query)
    {
        var words = query.ToLowerInvariant()
            .Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries)
            .Select(w => new string(w.Where(char.IsAsciiLetterOrDigit).ToArray()))
            .Where(w => w.Length > 0)
            .ToList();
        var spans = words
            .Select(w => Find(text, w))
            .OfType<(int Start, int End)>()
            .OrderBy(s => s.Start)
            .ToList();
        var parts = new List<(string, bool)>();
        var at = 0;
        foreach (var (start, end) in spans.Where(s => s.Start >= 0))
        {
            if (start < at)
            {
                continue;
            }
            parts.Add((text[at..start], false));
            parts.Add((text[start..end], true));
            at = end;
        }
        parts.Add((text[at..], false));
        return parts.Where(p => p.Item1.Length > 0).ToList();
    }

    /// <summary>The first stretch of `text` whose letters and digits spell `word` (any case), or null.</summary>
    private static (int Start, int End)? Find(string text, string word)
    {
        var low = text.ToLowerInvariant();
        for (var i = 0; i < low.Length; i++)
        {
            if (!char.IsAsciiLetterOrDigit(low[i]))
            {
                continue;
            }
            var (j, k) = (i, 0);
            while (j < low.Length && k < word.Length)
            {
                if (char.IsAsciiLetterOrDigit(low[j]))
                {
                    if (low[j] != word[k])
                    {
                        break;
                    }
                    k++;
                }
                j++;
            }
            if (k == word.Length)
            {
                return (i, j);
            }
        }
        return null;
    }
}
