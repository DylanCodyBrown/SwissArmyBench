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
            var parts = new List<string>();
            AddCount(parts, Card.Counts.Notebooks, "notebook");
            AddCount(parts, Card.Counts.Scripts, "script");
            AddCount(parts, Card.Counts.Apps, "app");
            AddCount(parts, Card.Counts.Tables, "table");
            return parts.Count == 0 ? "Empty" : string.Join(" · ", parts);
        }
    }

    private static void AddCount(List<string> parts, int count, string word)
    {
        if (count > 0)
        {
            parts.Add($"{count} {word}{(count == 1 ? string.Empty : "s")}");
        }
    }

    /// <summary>A time the server gives as seconds since 1970, in this computer's own time; Never when there is none.</summary>
    private static string When(double? seconds) =>
        seconds is { } value ? DateTimeOffset.FromUnixTimeMilliseconds((long)(value * 1000)).ToLocalTime().ToString("d MMM yyyy, HH:mm") : "Never";

    private async Task OpenAsync()
    {
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

    private Task ShareAsync() => RunAsync(() => Projects.ShareAsync(Card.Path));

    private Task CopyLocalAsync() => RunAsync(() => Projects.CopyLocalAsync(Card.Path));

    private Task RemoveAsync() => RunAsync(() => Projects.RemoveAsync(Card.Path));

    private Task MoveAsync(int by) => RunAsync(() => Projects.MoveAsync(Card.Path, by));

    private async Task RenameAsync()
    {
        var name = await Dialogs.AskTextAsync("Rename", "The project's folder takes the new name.", "Name", Card.Name, "Rename");
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
        var words = $"Its folder goes to the system's trash. Type {Card.Name} to delete it.";
        var typed = await Dialogs.AskTextAsync($"Delete {Card.Name}?", words, "Name", string.Empty, "Delete");
        if (typed is not null)
        {
            await RunAsync(() => Projects.DeleteAsync(Card.Path, typed));
        }
    }

    private async Task RunAsync<T>(Func<Task<T>> work)
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
