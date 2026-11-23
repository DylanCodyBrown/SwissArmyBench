using System.Globalization;
using System.Text;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api.Analyze;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Analyze;

// The board's own moves (the classic aiPanel.ts renderCards, sandboxPages.ts and sandboxExport.ts): a card's place
// before or after its neighbours, a note added or edited, Page view and its paper, Print to PDF, the board as one
// markdown file, and the board's theme as its tokens.
public partial class AnalyzePage
{
    private ElementReference _board;
    private (bool Open, BoardCard? Card)? _note;
    private bool _dashboards;
    private bool _pageView;
    private string _paper = BoardPages.Letter;
    private BoardTheme? _theme;

    [Inject]
    private Notes Notes { get; set; } = default!;

    private BoardPaper Paper => BoardPages.PaperOf(_paper);

    private string PageStyle => string.Create(CultureInfo.InvariantCulture, $"width: {Paper.Width}px; min-height: {Paper.Height}px;");

    /// <summary>The board's own theme as its tokens on the board (null: the app's colours).</summary>
    private string? ThemeStyle => _theme is { } theme
        ? string.Concat(theme.Tokens.Select(t => $"--{t.Key}: {t.Value}; ")
            .Concat(theme.Cat.Select((c, i) => $"--cat-{i + 1}: {c}; "))
            .Append($"color-scheme: {(theme.Dark ? "dark" : "light")};"))
        : null;

    private string? PreviousOf(BoardCard card) => _cards.TakeWhile(c => c.Id != card.Id).LastOrDefault()?.Id;

    private (bool Any, string? Before) LaterOf(BoardCard card)
    {
        var after = _cards.SkipWhile(c => c.Id != card.Id).Skip(1).ToList();
        return (after.Count > 0, after.Skip(1).FirstOrDefault()?.Id);
    }

    private async Task NoteSavedAsync()
    {
        _note = null;
        await LoadCardsAsync();
    }

    private async Task SetPageViewAsync(bool on)
    {
        _pageView = on;
        await Js.InvokeVoidAsync("sab.remember", "sandbox.pages", on ? "1" : "0");
    }

    private async Task SetPaperAsync(string paper)
    {
        _paper = paper;
        await Js.InvokeVoidAsync("sab.remember", "sandbox.paper", paper);
    }

    private async Task RecallBoardAsync()
    {
        _pageView = await Js.InvokeAsync<string?>("sab.recall", "sandbox.pages") == "1";
        _paper = await Js.InvokeAsync<string?>("sab.recall", "sandbox.paper") is { } paper && BoardPages.Papers.ContainsKey(paper) ? paper : BoardPages.Letter;
    }

    /// <summary>Print to PDF: the board in Page view on its paper; the browser's dialog saves the PDF.</summary>
    private async Task PrintAsync()
    {
        var was = _pageView;
        _pageView = true;
        StateHasChanged();
        await Task.Yield();
        var board = await Js.InvokeAsync<IJSObjectReference>("import", "./js/board.js");
        await board.InvokeVoidAsync("print", Paper.Css);
        _pageView = was;
    }

    /// <summary>All of Analyze as one markdown file, every drawing a picture (the classic sandboxExport.ts).</summary>
    private async Task ExportMarkdownAsync()
    {
        var board = await Js.InvokeAsync<IJSObjectReference>("import", "./js/board.js");
        var pictures = await board.InvokeAsync<Dictionary<string, string?>>("pictures", _board);
        var text = Markdown(_cards, pictures, DateTime.Now);
        await board.InvokeVoidAsync("save", text, $"sandbox-{DateTime.Now:yyyy-MM-dd}.md", "text/markdown");
        await Notes.SayAsync($"Exported {_cards.Count} card{(_cards.Count == 1 ? string.Empty : "s")} as markdown.");
    }

    public static string Markdown(IReadOnlyList<BoardCard> cards, IReadOnlyDictionary<string, string?> pictures, DateTime when)
    {
        string from(BoardCard c) => c.Dataset is { } d ? $"the grid `{d}`" : c.Origin.Length > 0 ? c.Origin : "Analyze";
        var tables = cards.Select(c => c.Dataset ?? (c.Origin.Length > 0 ? c.Origin : "Analyze")).Distinct().Select(t => $"`{t}`");
        var text = new StringBuilder()
            .AppendLine("# Analyze").AppendLine()
            .AppendLine(CultureInfo.InvariantCulture, $"Exported on {when.ToString(CultureInfo.CurrentCulture)}. {cards.Count} card{(cards.Count == 1 ? string.Empty : "s")}, from {string.Join(", ", tables)}.")
            .AppendLine("Each section below is one card, in the order they were arranged; charts are embedded as PNG images.");
        foreach (var card in cards)
        {
            var title = card.Title.Length > 0 ? card.Title : card.Kind;
            text.AppendLine().AppendLine("---").AppendLine().AppendLine(CultureInfo.InvariantCulture, $"## {title}").AppendLine()
                .AppendLine(CultureInfo.InvariantCulture, $"*From {from(card)} ({card.Kind}).*").AppendLine();
            text.AppendLine(card.Kind == "note"
                ? Demoted(card.Body ?? string.Empty)
                : pictures.GetValueOrDefault(card.Id) is { } picture
                    ? $"![{title.Replace("[", string.Empty).Replace("]", string.Empty)}]({picture})"
                    : "> (This drawing was not on screen to capture; open Analyze and export again.)");
        }
        return text.ToString();
    }

    // A note's own headings (one to four #) sit two levels under, at most six, as the classic export writes them.
    private static string Demoted(string body) =>
        System.Text.RegularExpressions.Regex.Replace(body, @"^(#{1,4})\s", m => $"{new string('#', Math.Min(6, m.Groups[1].Length + 2))} ", System.Text.RegularExpressions.RegexOptions.Multiline);
}
