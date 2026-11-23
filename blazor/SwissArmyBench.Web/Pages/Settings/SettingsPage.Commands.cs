using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Settings;

// The Settings page's commands in the one palette (Ctrl+Shift+P): each theme, the front end, Follow the agent, and
// Copy the agent's prompt; the same actions as the page's own controls, applied as they are run.
public partial class SettingsPage : IDisposable
{
    [Inject]
    private Commands Palette { get; set; } = default!;

    protected override void OnInitialized() => Palette.SetPageCommands(PageCommands);

    private IReadOnlyList<PaletteCommand> PageCommands() =>
    [
        .. ThemeState.Choices.Select(c => new PaletteCommand($"settings.theme.{c.Value}", "Settings", $"Theme: {c.Label}", () => Redrawn(() => Theme.SetAsync(c.Value)),
            WhyNot: Theme.Choice == c.Value ? $"The theme is {c.Label}" : null)),
        new("settings.frontend.classic", "Settings", "Front end: Classic", () => Redrawn(() => SetFrontendAsync(Classic)), WhyNot: _frontend == Classic ? "The classic front end is chosen" : null),
        new("settings.frontend.blazor", "Settings", "Front end: Blazor (preview)", () => Redrawn(() => SetFrontendAsync(Blazor)), WhyNot: _frontend == Blazor ? "This front end is chosen" : null),
        new("settings.follow", "Settings", _follow ? "Stop following the agent" : "Follow the agent", () => Redrawn(() => FollowAsync(new ChangeEventArgs { Value = !_follow }))),
        new("settings.agentPrompt", "Settings", "Copy the prompt that connects an agent", () => Redrawn(CopyPromptAsync)),
    ];

    private Task Redrawn(Func<Task> work) => InvokeAsync(async () =>
    {
        await work();
        StateHasChanged();
    });

    public void Dispose()
    {
        Palette.WithdrawPageCommands(PageCommands);
        GC.SuppressFinalize(this);
    }
}
