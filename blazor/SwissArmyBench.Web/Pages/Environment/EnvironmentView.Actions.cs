using System.Text.Json;

using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Environment;
using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Environment;

/// <summary>What a row does (the classic environmentPage.ts actionsOf): open it where it lives, insert it as code,
/// copy its name, rename, keep, make a sandbox variant, send it to the agent, remove; a setting's Change and Show;
/// a library's Update, Pin and Install; Clear…; following a use to its place.</summary>
public partial class EnvironmentView
{
    private EnvironmentItem? _renaming;
    private EnvironmentItem? _removing;
    private ClearChoices? _clearing;
    private bool _installing;
    private string? _setting;
    private string? _variantOf;
    private (string Title, IReadOnlyList<MenuEntry> Entries, double X, double Y)? _menu;

    /// <summary>A row's actions, as its menu and the viewer list them (the first, primary, opens it).</summary>
    private IReadOnlyList<EnvAction> ActionsOf(EnvironmentItem item)
    {
        var insert = new EnvAction(item.Kind == Library ? "Insert import" : item.Kind == Setting ? $"Insert {_passwordWords.Replace("NAME", item.Name, StringComparison.Ordinal)}" : "Insert into code", () => InsertAsync(item));
        var copy = new EnvAction("Copy name", () => CopyAsync(item.Name, "Copied its name."));
        var rename = new EnvAction("Rename…", () => Ask(() => _renaming = item));
        var remove = new EnvAction("Remove…", () => Ask(() => _removing = item), Icon: "trash");
        var agent = new EnvAction("Send to the agent", () => SendToAgentAsync(item), Icon: "agent");
        var open = item.Open?.ValueKind is JsonValueKind.True or JsonValueKind.String;
        return item.Kind switch
        {
            Table => [
                new EnvAction("Open in Tables", () => OpenItemAsync(item), Primary: true),
                insert,
                copy,
                .. open ? [rename, Keeping(item)] : Array.Empty<EnvAction>(),
                .. open && item.Grids is { Count: > 0 } ? [new EnvAction("Make a sandbox variant…", () => Ask(() => _variantOf = item.Name))] : Array.Empty<EnvAction>(),
                agent,
                remove,
            ],
            Structure => [new EnvAction("Open in Structures", () => OpenItemAsync(item), Primary: true), insert, copy, .. open ? [rename] : Array.Empty<EnvAction>(), agent, remove],
            Library => [
                .. item.Latest is { } latest ? [new EnvAction($"Update to {latest}", () => UpdateAsync(item), Primary: true)] : Array.Empty<EnvAction>(),
                item.Installed ? new EnvAction(item.Pinned ? "Unpin" : $"Pin at {item.Version}", () => PinAsync(item, !item.Pinned)) : new EnvAction("Install", () => InstallAsync(item.Name), Primary: true),
                insert,
                remove,
            ],
            Setting => [
                .. item.Editable ? [new EnvAction("Change…", () => Ask(() => _setting = item.Name), Primary: true)] : Array.Empty<EnvAction>(),
                .. item.Showable ? [new EnvAction(_revealed.ContainsKey(item.Id) ? "Hide" : "Show", () => RevealAsync(item), Icon: "eye")] : Array.Empty<EnvAction>(),
                insert,
                copy,
                .. item.Renamable ? [rename, remove] : Array.Empty<EnvAction>(),
            ],
            _ => [insert, copy, rename, agent, remove],
        };
    }

    private EnvAction Keeping(EnvironmentItem item)
    {
        var kept = (item.Tags ?? []).Contains("Keep");
        return new EnvAction(kept ? "Stop keeping with the project" : "Keep with the project", () => KeepAsync(item, !kept));
    }

    private static Task Ask(Action open)
    {
        open();
        return Task.CompletedTask;
    }

    private void RowMenu(EnvironmentItem item, double x, double y)
    {
        Select(item.Id);
        _menu = ($"Actions for {item.Name}", ActionsOf(item).Select(a => new MenuEntry(a.Label, a.Icon ?? string.Empty, a.Run)).ToList(), x, y);
    }

    /// <summary>Columns: each of the tab's columns ticked or not (kept per tab in this browser).</summary>
    private void ColumnsMenu(double x, double y) => _menu = ("Columns", EnvColumn.Of[_tab]
        .Select(c => new MenuEntry(c.Head, _hidden.Contains(c.Head) ? string.Empty : "check", () => ToggleColumnAsync(c.Head)))
        .ToList(), x, y);

    private async Task ToggleColumnAsync(string head)
    {
        if (!_hidden.Remove(head))
        {
            _hidden.Add(head);
        }
        await Js.InvokeVoidAsync("sab.remember", $"env.hidden.{_tab}", string.Join("|", _hidden));
    }

    private async Task CopyAsync(string words, string said)
    {
        if (await Js.InvokeAsync<bool>("sab.copy", words))
        {
            _ = Notes.SayAsync(said);
        }
        else
        {
            _error = new ApiException(0, new Refusal("The clipboard is not available here."), string.Empty);
        }
    }

    private Task InsertAsync(EnvironmentItem item) => GuardAsync(async () =>
    {
        var code = await Environment.InsertAsync(item.Kind, item.Name);
        var words = code.Text ?? code.Python ?? code.Sql ?? item.Name;
        await CopyAsync(words, $"Copied: {words}");
    });

    /// <summary>A row opened where it lives: a table's grid (or its Python session sends it), a structure's tab.</summary>
    private Task OpenItemAsync(EnvironmentItem item) => GuardAsync(async () =>
    {
        if (item.Kind == Structure)
        {
            Nav.NavigateTo(item.Path is { } path ? $"structures?path={Uri.EscapeDataString(path)}" : "structures");
            return;
        }
        if (item.Kind != Table)
        {
            Select(item.Id, true);
            return;
        }
        var got = await Environment.OpenAsync(item.Kind, item.Name);
        if (got.Link?.To == "python")
        {
            _ = Notes.SayAsync($"Opening {item.Name} from Python…"); // its session sends it: the grid arrives by itself
            return;
        }
        if (got.Link?.Grid is { } grid)
        {
            Nav.NavigateTo($"tables?grid={Uri.EscapeDataString(grid)}");
        }
    });

    /// <summary>A use followed to its place: a table's row here, a grid, a document's cell, a connection, an area.</summary>
    private Task FollowAsync(EnvironmentUse used)
    {
        var link = used.Link ?? new EnvironmentUseLink();
        switch (link.To)
        {
            case "table" when link.Name is { } name:
                Select($"table:{name}", true);
                break;
            case "grid" when link.Grid is { } grid:
                Nav.NavigateTo($"tables?grid={Uri.EscapeDataString(grid)}");
                break;
            case "document" when link.Path is { } path:
                Nav.NavigateTo($"{(path.EndsWith(".py", StringComparison.OrdinalIgnoreCase) ? "scripts" : "notebooks")}?path={Uri.EscapeDataString(path)}");
                break;
            case "connection" when link.Name is { } connection:
                Nav.NavigateTo($"connections?name={Uri.EscapeDataString(connection)}");
                break;
            case "analyze" or "erd" or "canvas":
                Nav.NavigateTo(link.To);
                break;
            default:
                break;
        }
        return Task.CompletedTask;
    }

    private Task SendToAgentAsync(EnvironmentItem item) => GuardAsync(async () =>
    {
        var lines = new[] { $"{_tabWords[item.Kind]}: {item.Name} ({item.Type}{(item.Size.Length > 0 ? $", {item.Size}" : string.Empty)})", item.From.Length > 0 ? $"From: {item.From}" : string.Empty }
            .Concat((item.Used ?? []).Select(u => $"Used in: {u.Words}"))
            .Concat(KidsOf(item).Select(k => $"  {k.ElementAtOrDefault(0)}: {k.ElementAtOrDefault(1)}"))
            .Where(l => l.Length > 0);
        await Environment.SendToAgentAsync($"Environment · {item.Name}", string.Join("\n", lines));
        _ = Notes.SayAsync("Sent to the agent");
    });

    private Task KeepAsync(EnvironmentItem item, bool to) => GuardAsync(async () =>
    {
        await Environment.KeepAsync(item.Name, to);
        _ = Notes.SayAsync(to ? $"{item.Name} is kept with the project." : $"{item.Name} is no longer kept with the project.");
        await LoadAsync();
    });

    private Task RevealAsync(EnvironmentItem item) => GuardAsync(async () =>
    {
        if (!_revealed.Remove(item.Id))
        {
            _revealed[item.Id] = await Environment.RevealAsync(item.Name);
        }
    });

    private Task PinAsync(EnvironmentItem item, bool to) => GuardAsync(async () =>
    {
        await Environment.PinAsync(item.Name, to);
        await LoadAsync();
    });

    private Task UpdateAsync(EnvironmentItem item) => GuardAsync(async () =>
    {
        await Environment.UpdateAsync(item.Name);
        await LoadAsync();
    });

    private Task UpdateAllAsync(IReadOnlyList<EnvironmentItem> outdated) => GuardAsync(async () =>
    {
        await Environment.UpdateAllAsync();
        _ = Notes.SayAsync($"Updated {outdated.Count} not pinned.");
        await LoadAsync();
    });

    private Task InstallAsync(string name) => GuardAsync(async () =>
    {
        await Environment.InstallAsync(name);
        await LoadAsync();
    });

    private async Task InstallTypedAsync(string? name)
    {
        _installing = false;
        if (name is { Length: > 0 })
        {
            await InstallAsync(name);
        }
    }

    private Task MakePythonAsync() => GuardAsync(async () =>
    {
        await Environment.MakePythonAsync();
        await LoadAsync();
    });

    private Task AnswerOfferAsync(PythonOffer offer, bool add) => GuardAsync(async () =>
    {
        await Environment.AnswerOfferAsync(offer.Document, add);
        await LoadAsync();
    });

    private async Task VariantClosedAsync(bool made)
    {
        _variantOf = null;
        if (made)
        {
            await LoadAsync();
        }
    }

    private void AddSetting(string name) => _setting = name;

    private async Task SettingAddedAsync()
    {
        _setting = null;
        await LoadAsync();
    }

    private Task ClearAsync() => GuardAsync(async () => _clearing = await Environment.ClearPlanAsync());

    private async Task ClearedAsync(bool done)
    {
        _clearing = null;
        if (done)
        {
            await LoadAsync();
        }
    }

    private async Task RenamedAsync(string? to)
    {
        if (to is not null && _renaming is { } item)
        {
            _selected = $"{item.Kind}:{to}";
            await LoadAsync();
        }
        _renaming = null;
    }

    private async Task RemovedAsync(bool done)
    {
        _removing = null;
        if (done)
        {
            await LoadAsync();
        }
    }

    private async Task GuardAsync(Func<Task> work)
    {
        try
        {
            await work();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }
}
