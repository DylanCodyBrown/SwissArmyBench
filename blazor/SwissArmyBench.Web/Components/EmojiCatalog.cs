using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

namespace SwissArmyBench.Web.Components;

/// <summary>
/// Every emoji, from wwwroot/data/emoji.json (made by tools/emoji_data.py from Unicode's own emoji-test.txt; no
/// package): read once when first wanted. The composer's `:` finds them by name; the reaction picker shows them by
/// group with search. Each person's recent reactions are kept in this browser (sab.remember, which never throws).
/// </summary>
public sealed class EmojiCatalog
{
    public const int MostFound = 8;
    private const int MostRecent = 8;
    private const string RecentKey = "collab.recentEmoji";
    private const string SkinTone = "skin tone";

    private readonly HttpClient _http;
    private readonly NavigationManager _navigation;
    private readonly IJSRuntime _js;
    private Task<IReadOnlyList<EmojiEntry>>? _loading;

    public EmojiCatalog(HttpClient http, NavigationManager navigation, IJSRuntime js)
    {
        _http = http;
        _navigation = navigation;
        _js = js;
    }

    /// <summary>The groups in Unicode's order, each with its emoji (a skin tone's variant left to search).</summary>
    public IReadOnlyList<string> Groups { get; private set; } = [];

    public Task<IReadOnlyList<EmojiEntry>> AllAsync() => _loading ??= LoadAsync();

    /// <summary>The emoji whose name starts with the words, then those holding them (`:tada` finds 🎉).</summary>
    public async Task<IReadOnlyList<EmojiEntry>> MatchingAsync(string typed, int most = MostFound)
    {
        var words = typed.Replace('_', ' ').Trim().ToLowerInvariant();
        var all = await AllAsync();
        return all
            .Where(e => words.Length == 0 || e.Name.Contains(words, StringComparison.Ordinal))
            .OrderBy(e => e.Name.StartsWith(words, StringComparison.Ordinal) ? 0 : 1)
            .ThenBy(e => e.Name.Contains(SkinTone, StringComparison.Ordinal) ? 1 : 0)
            .Take(most)
            .ToList();
    }

    /// <summary>A group's emoji for the grid (no skin tone variants: search finds them).</summary>
    public async Task<IReadOnlyList<EmojiEntry>> GroupAsync(string group) =>
        (await AllAsync()).Where(e => e.Group == group && !e.Name.Contains(SkinTone, StringComparison.Ordinal)).ToList();

    /// <summary>This person's recent reactions, newest first (none when storage is blocked).</summary>
    public async Task<IReadOnlyList<string>> RecentAsync()
    {
        var kept = await _js.InvokeAsync<string?>("sab.recall", RecentKey);
        try
        {
            return kept is { Length: > 0 } ? JsonSerializer.Deserialize<List<string>>(kept) ?? [] : [];
        }
        catch (JsonException)
        {
            return [];
        }
    }

    public async Task UsedAsync(string emoji)
    {
        var recent = (await RecentAsync()).Where(e => e != emoji).Prepend(emoji).Take(MostRecent).ToList();
        await _js.InvokeVoidAsync("sab.remember", RecentKey, JsonSerializer.Serialize(recent));
    }

    private async Task<IReadOnlyList<EmojiEntry>> LoadAsync()
    {
        try
        {
            using var file = JsonDocument.Parse(await _http.GetStringAsync(new Uri(new Uri(_navigation.BaseUri), "data/emoji.json")));
            var groups = file.RootElement.GetProperty("groups").EnumerateArray().Select(g => g.GetString() ?? string.Empty).ToList();
            var all = file.RootElement.GetProperty("emoji").EnumerateArray()
                .Select(row => new EmojiEntry(row[0].GetString() ?? string.Empty, row[1].GetString() ?? string.Empty, groups[row[2].GetInt32()]))
                .ToList();
            Groups = groups.Where(g => all.Any(e => e.Group == g)).ToList();
            return all;
        }
        catch (Exception error) when (error is HttpRequestException or JsonException or KeyNotFoundException or InvalidOperationException)
        {
            _loading = null; // asked again next time
            return [];
        }
    }
}
