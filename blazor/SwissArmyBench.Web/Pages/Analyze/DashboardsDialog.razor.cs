using System.Globalization;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Analyze;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Analyze;

public partial class DashboardsDialog
{
    private string _name = string.Empty;
    private DashboardList? _list;
    private DashboardHistory? _history;
    private Exception? _error;

    [Inject]
    private BoardClient Board { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    /// <summary>How many cards the board shows now (Open asks before replacing them; Save needs one).</summary>
    [Parameter]
    public int CardsNow { get; set; }

    [Parameter]
    public EventCallback OnClose { get; set; }

    /// <summary>A dashboard opened: the board reads its cards again.</summary>
    [Parameter]
    public EventCallback OnOpened { get; set; }

    protected override Task OnInitializedAsync() => GuardAsync(RefreshAsync);

    private async Task RefreshAsync() => _list = await Board.DashboardsAsync();

    private static string CardWords(int count) => count == 1 ? "1 card" : $"{count} cards";

    private static string When(string saved) =>
        DateTimeOffset.TryParse(saved, CultureInfo.InvariantCulture, DateTimeStyles.None, out var at) ? at.ToLocalTime().ToString("g", CultureInfo.CurrentCulture) : saved;

    private Task NameKeyAsync(KeyboardEventArgs e) => e.Key == "Enter" ? SaveAsync() : Task.CompletedTask;

    private Task SaveAsync() => GuardAsync(async () =>
    {
        var name = _name.Trim();
        var saved = await Board.SaveDashboardAsync(name);
        await Notes.SayAsync($"Saved {name}{(saved.Version > 1 ? $" (version {saved.Version})" : string.Empty)}: {CardWords(saved.Cards)}.");
        await RefreshAsync();
    });

    private async Task OpenAsync(string dashboard, int? version)
    {
        if (CardsNow > 0 && !await Dialogs.AskYesNoAsync("Dashboards", $"Replace the {CardWords(CardsNow)} on the Analyze board with {dashboard}?", "Replace"))
        {
            return;
        }
        await GuardAsync(async () =>
        {
            var opened = await Board.OpenDashboardAsync(dashboard, version);
            var asSaved = opened.AsSaved > 0 ? $", {opened.AsSaved} as saved until their tables are open" : string.Empty;
            await Notes.SayAsync($"Opened {dashboard}: {CardWords(opened.Cards)}{asSaved}.");
            await OnOpened.InvokeAsync();
            await OnClose.InvokeAsync();
        });
    }

    private Task HistoryAsync(string dashboard) => GuardAsync(async () =>
        _history = _history?.Name == dashboard ? null : await Board.HistoryAsync(dashboard));

    private async Task DeleteAsync(DashboardSummary d)
    {
        var versions = d.Versions == 1 ? "1 version" : $"{d.Versions} versions";
        if (await Dialogs.AskYesNoAsync("Dashboards", $"Delete {d.Name} and its {versions}?", "Delete", danger: true))
        {
            await GuardAsync(async () =>
            {
                await Board.DeleteDashboardAsync(d.Name);
                await RefreshAsync();
            });
        }
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
