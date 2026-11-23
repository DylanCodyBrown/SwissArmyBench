using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Environment;

// The Environment page's commands in the one palette (Ctrl+Shift+P): each tab by its words, the search, Clear…, Add a
// setting… and Install a library…, Read again. The Workbench's pane is part of its page, whose own commands stand.
public partial class EnvironmentView
{
    [Inject]
    private Commands Palette { get; set; } = default!;

    private void OfferCommands()
    {
        if (!Compact)
        {
            Palette.SetPageCommands(PageCommands);
        }
    }

    private void WithdrawCommands()
    {
        if (!Compact)
        {
            Palette.WithdrawPageCommands(PageCommands);
        }
    }

    private IReadOnlyList<PaletteCommand> PageCommands() =>
    [
        .. _kinds.Select(kind => new PaletteCommand($"environment.tab.{kind}", "Environment", $"Show {_tabWords[kind]}", () => InvokeAsync(() => SetTabAsync(kind)),
            WhyNot: _tab == kind ? $"{_tabWords[kind]} is shown" : null)),
        new("environment.search", "Environment", "Search every tab", () => InvokeAsync(() => _searchBox.FocusAsync().AsTask()), "/"),
        new("environment.clear", "Environment", "Clear what is not kept…", () => InvokeAsync(ClearAsync)),
        new("environment.addSetting", "Environment", "Add a setting…", () => InvokeAsync(() =>
        {
            AddSetting(string.Empty);
            StateHasChanged();
        })),
        new("environment.install", "Environment", "Install a library…", () => InvokeAsync(() =>
        {
            _installing = true;
            StateHasChanged();
        })),
        new("environment.read", "Environment", "Read the Environment again", () => InvokeAsync(async () =>
        {
            await LoadAsync();
            StateHasChanged();
        })),
    ];
}
