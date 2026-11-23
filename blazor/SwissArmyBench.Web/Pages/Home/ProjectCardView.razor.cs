using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Files;
using SwissArmyBench.Web.Api.Projects;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Home;

public partial class ProjectCardView
{
    private const int ConflictStatus = 409;

    private bool _menu;

    [Inject]
    private ProjectsClient Projects { get; set; } = default!;

    [Inject]
    private ProjectState Project { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private FileChooser Files { get; set; } = default!;

    [Inject]
    private ApiClient Api { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Parameter, EditorRequired]
    public ProjectCard Card { get; set; } = default!;

    [Parameter]
    public bool First { get; set; }

    [Parameter]
    public bool Last { get; set; }

    /// <summary>The cards are in the custom order: Move left and Move right are offered.</summary>
    [Parameter]
    public bool Custom { get; set; }

    [Parameter]
    public EventCallback OnChanged { get; set; }

    [Parameter]
    public EventCallback<Exception> OnError { get; set; }

    /// <summary>"2 notebooks · 1 script · 3 tables", or Empty.</summary>
    private string Counts
    {
        get
        {
            (int Count, string Word)[] counts =
            [
                (Card.Counts.Notebooks, "notebook"),
                (Card.Counts.Scripts, "script"),
                (Card.Counts.Apps, "app"),
                (Card.Counts.Tables, "table"),
            ];
            var parts = counts
                .Where(c => c.Count > 0)
                .Select(c => $"{c.Count} {c.Word}{(c.Count == 1 ? string.Empty : "s")}")
                .ToList();
            return parts.Count == 0 ? "Empty" : string.Join(" · ", parts);
        }
    }

    /// <summary>A time the server gives as seconds since 1970, in this computer's own time; Never when there is none.</summary>
    private static string When(double? seconds) =>
        seconds is { } value ? DateTimeOffset.FromUnixTimeMilliseconds((long)(value * 1000)).ToLocalTime().ToString("d MMM yyyy, HH:mm") : "Never";

    private async Task OpenAsync()
    {
        _menu = false;
        try
        {
            await Projects.OpenAsync(Card.Path);
        }
        catch (ApiException error) when (error.Status == ConflictStatus)
        {
            if (await Dialogs.AskYesNoAsync("Open project", error.Refusal.Error, "Discard and open", danger: true))
            {
                await RunAsync(() => Projects.OpenAsync(Card.Path, discard: true));
            }
        }
        catch (ApiException error)
        {
            await OnError.InvokeAsync(error);
        }
        await Project.RefreshAsync();
        await OnChanged.InvokeAsync();
    }

    private Task ShowAsync() => RunAsync(() => Projects.ShowAsync(Card.Path));

    private Task ShareAsync() => CopyAsync("/projects/share", $"{Card.Name} is shared");

    private Task CopyLocalAsync() => CopyAsync("/projects/copy-local", $"A local copy of {Card.Name} is made");

    /// <summary>Share and Make a local copy (the classic copyTo): the copy made, then opened; a name taken asks for
    /// another.</summary>
    private Task CopyAsync(string path, string words) => RunAsync(async () =>
    {
        string? name = null;
        while (true)
        {
            try
            {
                var done = await Api.PostAsync<System.Text.Json.JsonElement>(path, name is null ? new { path = Card.Path } : new { path = Card.Path, name });
                var opened = done.TryGetProperty("opened", out var o) && o.ValueKind == System.Text.Json.JsonValueKind.True;
                var why = done.TryGetProperty("why", out var w) && w.ValueKind == System.Text.Json.JsonValueKind.String ? w.GetString() : string.Empty;
                _ = Notes.SayAsync(opened ? words : $"{words}. {why}".Trim());
                await Project.RefreshAsync();
                return;
            }
            catch (ApiException error) when (FreeName().Match(error.Message) is { Success: true } free)
            {
                name = (await Dialogs.AskTextAsync(error.Message, "Name the copy:", "Name", free.Groups[1].Value))?.Trim();
                if (string.IsNullOrEmpty(name))
                {
                    return;
                }
            }
        }
    });

    private Task CopyToAsync() => RunAsync(async () =>
    {
        if (await Files.ChooseAsync("save", $"Copy {Card.Name} to", null, "project") is not { } target)
        {
            return;
        }
        var data = await Dialogs.AskYesNoAsync("Copy the rows kept in .sab/data too?", "With them, or without (data is sensitive).", "With them");
        var done = await Api.PostAsync<System.Text.Json.JsonElement>("/project/copy", new { path = target, data, folder = Card.Path });
        _ = Notes.SayAsync($"Copied to {done.GetProperty("copied").GetString()}");
    });

    private Task InstallAsync(string extension) => RunAsync(async () =>
    {
        await Api.PostAsync("/extensions/install", new { id = extension });
        _ = Notes.SayAsync("Installing: the app restarts when it is done.");
    });

    /// <summary>A click on the card (not on a button) or Enter on it opens the project.</summary>
    private Task ClickAsync(Microsoft.AspNetCore.Components.Web.MouseEventArgs e) => Card.Missing || _menu ? Task.CompletedTask : OpenAsync();

    private Task KeyAsync(Microsoft.AspNetCore.Components.Web.KeyboardEventArgs e) => e.Key == "Enter" && !Card.Missing && !_menu ? OpenAsync() : Task.CompletedTask;

    private void MenuKey(Microsoft.AspNetCore.Components.Web.KeyboardEventArgs e)
    {
        if (e.Key == "Escape")
        {
            _menu = false;
        }
    }

    [System.Text.RegularExpressions.GeneratedRegex("\"([^\"]+)\" is free")]
    private static partial System.Text.RegularExpressions.Regex FreeName();

    private Task RemoveAsync() => RunAsync(() => Projects.RemoveAsync(Card.Path));

    private Task MoveAsync(int by) => RunAsync(() => Projects.MoveAsync(Card.Path, by));

    private async Task RenameAsync()
    {
        var name = await Dialogs.AskTextAsync($"Rename {Card.Name}", "The project's folder takes the new name.", "Name", Card.Name, "Rename");
        if (!string.IsNullOrWhiteSpace(name) && name != Card.Name)
        {
            await RunAsync(() => Projects.RenameAsync(Card.Path, name.Trim()));
        }
    }

    private async Task LocateAsync()
    {
        var to = await Files.ChooseAsync("folder", $"Where is {Card.Name} now?", null, "project");
        if (to is not null)
        {
            await RunAsync(() => Projects.LocateAsync(Card.Path, to));
        }
    }

    /// <summary>Delete: the folder to the system's trash, only on its typed name (the user's own: never the agent's).</summary>
    private async Task DeleteAsync()
    {
        var words = $"Type {Card.Name} to delete it.";
        var typed = await Dialogs.AskTextAsync($"Delete {Card.Name}: its folder goes to the trash", words, "Name", string.Empty, "Delete");
        if (typed is not null)
        {
            await RunAsync(async () =>
            {
                var done = await Api.PostAsync<System.Text.Json.JsonElement>("/projects/delete", new { path = Card.Path, confirm = typed });
                _ = Notes.SayAsync($"{Card.Name} is in {done.GetProperty("to").GetString()}");
            });
        }
    }

    private async Task RunAsync(Func<Task> work)
    {
        _menu = false;
        try
        {
            await work();
        }
        catch (ApiException error)
        {
            await OnError.InvokeAsync(error);
        }
        await OnChanged.InvokeAsync();
    }
}
