using System.Text.Json;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Connections;

namespace SwissArmyBench.Web.State;

/// <summary>Every connection's colour (the classic connectionColours.ts), as the current theme shows it: read once,
/// again on a connection_colours_changed notice (which carries the listing), a saved connection or an opened project.
/// What names a connection wears its colour (a card's border and tint, its detail's swatch).</summary>
public sealed class ConnectionColours : IDisposable
{
    private readonly ConnectionsClient _connections;
    private readonly LiveUpdates _live;
    private readonly ThemeState _theme;
    private Task? _loading;

    public ConnectionColours(ConnectionsClient connections, LiveUpdates live, ThemeState theme)
    {
        _connections = connections;
        _live = live;
        _theme = theme;
        _live.NoticeArrived += OnNotice;
        _theme.Changed += OnTheme;
    }

    public event Action? Changed;

    public ColourListing Listing { get; private set; } = new([], []);

    /// <summary>The listing, read the first time it is asked for (later calls share the read).</summary>
    public Task LoadAsync() => _loading ??= RefreshAsync();

    /// <summary>A connection's colour in the current theme (null: no colour for it).</summary>
    public string? Of(string? name)
    {
        var found = Listing.Connections.FirstOrDefault(c => string.Equals(c.Name, name, StringComparison.OrdinalIgnoreCase));
        return found is null ? null : found.Themes.GetValueOrDefault(_theme.Effective) ?? found.Colour;
    }

    public ConnectionColour? Find(string name) =>
        Listing.Connections.FirstOrDefault(c => string.Equals(c.Name, name, StringComparison.OrdinalIgnoreCase));

    /// <summary>A palette colour as the current theme shows it.</summary>
    public string Shown(PaletteColour colour) => colour.Themes.GetValueOrDefault(_theme.Effective) ?? colour.Colour;

    /// <summary>Choose a connection's colour (null: the next free one); refused with the server's words.</summary>
    public async Task SetAsync(string name, string? colour) => Take(await _connections.SetColourAsync(name, colour));

    private async Task RefreshAsync()
    {
        try
        {
            Take(await _connections.ColoursAsync());
        }
        catch (ApiException)
        {
            // an older server: no colours
        }
    }

    private void Take(ColourListing listing)
    {
        Listing = listing;
        Changed?.Invoke();
    }

    private void OnNotice(Notice notice)
    {
        if (notice.Type == "connection_colours_changed")
        {
            var listing = notice.Body.Deserialize<ColourListing>(ApiClient.Json);
            if (listing is not null)
            {
                Take(listing with { Connections = listing.Connections ?? [], Palette = listing.Palette ?? [] });
            }
        }
        else if (notice.Type is "blades_changed" or "project_changed")
        {
            _ = RefreshAsync();
        }
    }

    private void OnTheme() => Changed?.Invoke();

    public void Dispose()
    {
        _live.NoticeArrived -= OnNotice;
        _theme.Changed -= OnTheme;
    }
}
