using System.Text.Json;

using SwissArmyBench.Web.Api.Analyze;

namespace SwissArmyBench.Web.Pages.Analyze;

/// <summary>
/// Page view (the classic sandboxPages.ts): the board's cards laid on pages of the chosen paper, in their order, row
/// by row on the twelve columns; a page ends where the next row would not fit, and a card marked "Start a new page
/// here" starts one.
/// </summary>
public static class BoardPages
{
    public const string Letter = "letter";

    // Half an inch of margin at 96 pixels to the inch; the board's gap and row height.
    private const int Margin = 48;
    private const int Gap = 12;
    private const int RowHeight = 32;
    private const int Columns = 12;
    private const int DefaultWidth = 6;
    private const int DefaultHeight = 10;

    public static readonly IReadOnlyDictionary<string, BoardPaper> Papers = new Dictionary<string, BoardPaper>
    {
        [Letter] = new("Letter", 816, 1056, "8.5in 11in"),
        ["landscape"] = new("Letter landscape", 1056, 816, "11in 8.5in"),
    };

    public static BoardPaper PaperOf(string key) => Papers.TryGetValue(key, out var paper) ? paper : Papers[Letter];

    /// <summary>The cards on pages: each page's cards in order.</summary>
    public static IReadOnlyList<IReadOnlyList<BoardCard>> Pages(IReadOnlyList<BoardCard> cards, BoardPaper paper)
    {
        var room = paper.Height - 2 * Margin;
        var pages = new List<List<BoardCard>> { new() };
        var (used, rowWidth, rowTall) = (0, 0, 0);
        foreach (var card in cards)
        {
            var (w, h) = SizeOf(card);
            var tall = h * RowHeight + (h - 1) * Gap;
            var wraps = rowWidth + w > Columns;
            var usedIfPlaced = wraps ? used + rowTall + Gap : used;
            var rowIfPlaced = wraps ? tall : Math.Max(rowTall, tall);
            if (pages[^1].Count > 0 && (card.NewPage || usedIfPlaced + rowIfPlaced > room))
            {
                pages.Add([]);
                (used, rowWidth, rowTall) = (0, w, tall);
            }
            else
            {
                (used, rowWidth, rowTall) = (usedIfPlaced, wraps ? w : rowWidth + w, rowIfPlaced);
            }
            pages[^1].Add(card);
        }
        return pages;
    }

    private static (int W, int H) SizeOf(BoardCard card) =>
        card.Size is { ValueKind: JsonValueKind.Object } size
            ? (Read(size, "w", DefaultWidth), Read(size, "h", DefaultHeight))
            : (DefaultWidth, DefaultHeight);

    private static int Read(JsonElement size, string name, int fallback) =>
        size.TryGetProperty(name, out var value) && value.TryGetInt32(out var n) ? n : fallback;
}
