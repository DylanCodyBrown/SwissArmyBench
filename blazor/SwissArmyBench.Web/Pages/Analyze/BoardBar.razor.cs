using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Forms;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Analyze;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Analyze;

public partial class BoardBar
{
    // A theme file is small (its colour tokens): a larger one is not a theme.
    private const long MaxThemeBytes = 256 * 1024;

    private BoardThemes? _themes;
    private Exception? _error;

    [Inject]
    private BoardClient Board { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Parameter]
    public bool PageView { get; set; }

    [Parameter]
    public string Paper { get; set; } = BoardPages.Letter;

    [Parameter]
    public EventCallback OnAddNote { get; set; }

    [Parameter]
    public EventCallback OnAddChart { get; set; }

    [Parameter]
    public EventCallback<bool> OnPageView { get; set; }

    [Parameter]
    public EventCallback<string> OnPaper { get; set; }

    [Parameter]
    public EventCallback OnPrint { get; set; }

    [Parameter]
    public EventCallback OnExportMarkdown { get; set; }

    [Parameter]
    public EventCallback OnDashboards { get; set; }

    /// <summary>The board's theme as it is now (null: it follows the app).</summary>
    [Parameter]
    public EventCallback<BoardTheme?> OnTheme { get; set; }

    private BoardTheme? Chosen => _themes?.Themes.FirstOrDefault(t => t.Id == _themes.Current);

    protected override Task OnInitializedAsync() => LoadAsync();

    private async Task LoadAsync()
    {
        await GuardAsync(async () => _themes = await Board.ThemesAsync());
        await OnTheme.InvokeAsync(Chosen);
    }

    private Task ChooseAsync(ChangeEventArgs e) => ChangedAsync(() => Board.SetThemeAsync(e.Value?.ToString() ?? "app"));

    private async Task ImportAsync(InputFileChangeEventArgs e)
    {
        try
        {
            using var stream = e.File.OpenReadStream(MaxThemeBytes);
            using var file = await JsonDocument.ParseAsync(stream);
            var added = await Board.AddThemeAsync(file.RootElement.Clone());
            await Board.SetThemeAsync(added.Id);
            await Notes.SayAsync($"Imported theme {added.Label}.");
            await LoadAsync();
        }
        catch (JsonException)
        {
            _error = new InvalidOperationException("That file is not JSON.");
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private static object ThemeFile(BoardTheme theme) => new
    {
        name = theme.Label,
        dark = theme.Dark,
        tokens = theme.Tokens.ToDictionary(t => t.Key, t => (object)t.Value).Append(new KeyValuePair<string, object>("cat", theme.Cat)).ToDictionary(),
    };

    private async Task ExportAsync(BoardTheme theme)
    {
        var text = JsonSerializer.Serialize(ThemeFile(theme), new JsonSerializerOptions { WriteIndented = true });
        var board = await Js.InvokeAsync<IJSObjectReference>("import", "./js/board.js");
        await board.InvokeVoidAsync("save", text, $"{theme.Id}.theme.json", "application/json");
    }

    private Task KeepAsync(BoardTheme theme) => ChangedAsync(async () =>
    {
        await Board.AddThemeAsync(JsonSerializer.SerializeToElement(ThemeFile(theme)));
        await Notes.SayAsync($"Kept {theme.Label}.");
    });

    private async Task RemoveAsync(BoardTheme theme)
    {
        if (await Dialogs.AskYesNoAsync("Board theme", $"Remove the theme {theme.Label}? Analyze goes back to following the app.", "Remove", danger: true))
        {
            await ChangedAsync(() => Board.RemoveThemeAsync(theme.Id));
        }
    }

    private async Task ChangedAsync(Func<Task> action)
    {
        await GuardAsync(action);
        await LoadAsync();
    }

    private async Task GuardAsync(Func<Task> action)
    {
        try
        {
            await action();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }
}
