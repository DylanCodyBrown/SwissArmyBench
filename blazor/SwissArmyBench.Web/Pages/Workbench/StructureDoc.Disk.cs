using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Files;
using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Workbench;

// A structure tab's text and its file (the classic structureDoc.ts): the text kept as typed (the server's parse is its
// realtime linter, the tree following), Format, Save (only when its bytes change; a text that does not parse saved
// with a warning; never over a file changed on disk since: Reload or Keep mine), Save as…, Cancel (the file's own text
// again), and a file_changed notice for its file (taken at once with nothing unsaved, else the bar; a gone file:
// Save as…, Close).
public partial class StructureDoc
{
    private static readonly Dictionary<string, string> _suffixes = new() { ["json"] = ".json", ["yaml"] = ".yaml", ["xml"] = ".xml", ["toml"] = ".toml" };

    private string _editorText = string.Empty; // what the editor is given (the file's text, or an edit's new one)
    private string _current = string.Empty; // what the editor holds now
    private string _savedText = string.Empty;
    private string _sent = string.Empty; // the text the server holds
    private string? _hash;
    private bool _extraDirty; // Keep mine: what is on disk is not this text, so Save writes
    private bool _saving;
    private string? _heard; // a file_changed notice heard while saving
    private bool _heardAny;
    private bool _wasDirty;
    private (string Kind, string Words)? _note;

    [Inject]
    private FileChooser Files { get; set; } = default!;

    public bool Dirty => _current != _savedText || _extraDirty;

    private async Task TellDirtyAsync()
    {
        if (Dirty != _wasDirty)
        {
            _wasDirty = Dirty;
            await OnDirty.InvokeAsync(Dirty);
        }
    }

    /// <summary>The text typed: sent for its parse (the tree follows once it parses).</summary>
    private Task TextChangedAsync(string text) => DoAsync(async () =>
    {
        _current = text;
        await TellDirtyAsync();
        if (_shown is null || text == _sent)
        {
            return;
        }
        var done = await Structures.SetTextAsync(_shown.Id, text, _through);
        _sent = text;
        Took(done, false);
    });

    private Task EditorKeyAsync(EditorKey key) => key.Name switch
    {
        "save" => SaveAsync(),
        "saveAs" => SaveAsAsync(),
        _ => Task.CompletedTask,
    };

    private string Current => _current;

    public async Task<bool> SaveAsync()
    {
        if (_shown is not { } shown)
        {
            return false;
        }
        if (shown.Path is null)
        {
            return await SaveAsAsync();
        }
        var text = Current;
        _saving = true;
        try
        {
            var done = await Structures.SaveAsync(shown.Id, text, _hash);
            Took(done with { Text = text });
            (_savedText, _extraDirty, _note) = (text, false, null);
            if (done.Warning is { } warning)
            {
                _note = ("sd-warning", warning);
            }
            else
            {
                _ = Notes.SayAsync(done.Written is not null ? $"Saved {shown.Name}." : $"{shown.Name} is saved already.");
            }
            return true;
        }
        catch (ApiException error) when (error.Status == 409)
        {
            _note = ("sd-elsewhere", $"{shown.Name} changed on disk since it was read: nothing was written.");
            return false;
        }
        catch (ApiException error)
        {
            _error = error;
            return false;
        }
        finally
        {
            _saving = false;
            await TellDirtyAsync();
            if (_heardAny)
            {
                _heardAny = false;
                await ChangedOnDiskAsync(_heard);
            }
        }
    }

    public async Task<bool> SaveAsAsync()
    {
        if (_shown is not { } shown)
        {
            return false;
        }
        var name = $"{shown.Name}{_suffixes.GetValueOrDefault(shown.Format, ".json")}";
        if (await Files.ChooseAsync("save", $"Save {shown.Name} as", shown.Path, "file", name: name) is not { } chosen)
        {
            return false;
        }
        var saved = false;
        await DoAsync(async () =>
        {
            await Structures.SetTextAsync(shown.Id, Current, false);
            var done = await Structures.SaveAsAsync(shown.Id, chosen);
            Took(done, false);
            (_savedText, _extraDirty, _note) = (Current, false, null);
            await TellDirtyAsync();
            await OnRenamed.InvokeAsync(done.Path ?? chosen);
            _ = Notes.SayAsync($"Saved {done.Path ?? chosen}");
            saved = true;
        });
        return saved;
    }

    /// <summary>Cancel: the file's own text again.</summary>
    private Task CancelAsync() => ReloadNowAsync();

    private Task ReloadNowAsync() => DoAsync(async () =>
    {
        if (_shown is null)
        {
            return;
        }
        var again = await Structures.ReloadAsync(_shown.Id);
        Took(again);
        _editorText = _savedText = _current = again.Text ?? string.Empty;
        (_extraDirty, _note) = (false, null);
        await TellDirtyAsync();
    });

    private Task KeepMineAsync() => DoAsync(async () =>
    {
        if (_shown is null)
        {
            return;
        }
        var kept = await Structures.KeepMineAsync(_shown.Id);
        _hash = kept.Hash;
        (_note, _extraDirty) = (null, true);
        await TellDirtyAsync();
    });

    /// <summary>A file_changed notice for its file (hash null: it is gone).</summary>
    public async Task ChangedOnDiskAsync(string? hash)
    {
        if (_saving)
        {
            (_heard, _heardAny) = (hash, true);
            return;
        }
        if (hash is not null && hash == _hash)
        {
            return; // its own Save, or the same text
        }
        if (hash is null)
        {
            _note = ("sd-gone", "This file is gone.");
        }
        else if (!Dirty)
        {
            await ReloadNowAsync();
        }
        else
        {
            _note = ("sd-elsewhere", $"{_shown?.Name} changed on disk.");
        }
        StateHasChanged();
    }

    /// <summary>Format: written again in its own format (JSON indented by 2, the keys in their order).</summary>
    public Task FormatAsync() => DoAsync(async () =>
    {
        if (_shown is null)
        {
            return;
        }
        await Structures.SetTextAsync(_shown.Id, Current, false);
        var done = await Structures.FormatAsync(_shown.Id);
        Took(done);
        _editorText = _current = done.Text ?? Current;
        await TellDirtyAsync();
    });
}
