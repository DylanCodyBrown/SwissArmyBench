using System.Text.Json;

namespace SwissArmyBench.Web.Api.Analyze;

/// <summary>
/// The Analyze board itself (routes_cards.py): a card's pin, size, place and new page, a note added or edited; the
/// saved dashboards (save a version, its history, open one, delete); and the board's themes (choose, import, keep,
/// remove).
/// </summary>
public sealed class BoardClient
{
    private readonly ApiClient _api;

    public BoardClient(ApiClient api)
    {
        _api = api;
    }

    /// <summary>A card changed: title, body, pinned, new_page, size ({w, h}) or before (its place: before that card,
    /// or null for the end).</summary>
    public Task PatchAsync(string card, IReadOnlyDictionary<string, object?> change) =>
        _api.PatchAsync<JsonElement>($"/cards/{ApiClient.Part(card)}", change);

    public Task AddNoteAsync(string title, string body) => _api.PostAsync("/cards", new { kind = "note", title, body });

    public Task<DashboardList> DashboardsAsync() => _api.GetAsync<DashboardList>("/dashboards");

    public Task<DashboardHistory> HistoryAsync(string name) => _api.GetAsync<DashboardHistory>($"/dashboards/{ApiClient.Part(name)}");

    public Task<DashboardSaved> SaveDashboardAsync(string name) => _api.PostAsync<DashboardSaved>("/dashboards", new { name });

    public Task<DashboardOpened> OpenDashboardAsync(string name, int? version) =>
        _api.PostAsync<DashboardOpened>($"/dashboards/{ApiClient.Part(name)}/open", version is { } v ? new { version = v } : new { });

    public Task DeleteDashboardAsync(string name) => _api.DeleteAsync($"/dashboards/{ApiClient.Part(name)}");

    public Task<BoardThemes> ThemesAsync() => _api.GetAsync<BoardThemes>("/analyze/themes");

    public Task SetThemeAsync(string theme) => _api.PutAsync("/analyze/theme", new { theme });

    /// <summary>A theme file added ({name, dark, tokens}), its answer the theme as kept.</summary>
    public Task<BoardTheme> AddThemeAsync(JsonElement file) => _api.PostAsync<BoardTheme>("/analyze/themes", file);

    public Task RemoveThemeAsync(string theme) => _api.DeleteAsync($"/analyze/themes/{ApiClient.Part(theme)}");
}
