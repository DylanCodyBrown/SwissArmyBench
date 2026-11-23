using System.Globalization;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Files;

namespace SwissArmyBench.Web.Components;

public partial class FilePicker
{
    private const long Kilobyte = 1024;
    private const long Megabyte = 1024 * 1024;

    private static readonly Dictionary<string, string> _placeIcons = new()
    {
        ["home"] = "user",
        ["desktop"] = "desktop",
        ["documents"] = "file",
        ["downloads"] = "import",
        ["projects"] = "project",
        ["library"] = "book",
        ["recent"] = "clock",
        ["drive"] = "data",
    };

    private FolderListing? _shown;
    private IReadOnlyList<FolderPlace> _places = [];
    private bool _placesRead;
    private bool _hidden;
    private int _selected = -1;
    private string _filter = string.Empty;
    private string _where = string.Empty;
    private string _saveName = string.Empty;
    private string _status = string.Empty;
    private string? _missing;
    private bool _reading;
    private string _readingWords = "Reading the folder…";
    private int _asked;
    private bool _naming;
    private string _newName = "New folder";
    private bool _focusList;
    private ElementReference _list;
    private ElementReference _filterBox;
    private ElementReference _saveBox;
    private ElementReference _newBox;

    [Inject]
    private ApiClient Api { get; set; } = default!;

    [Parameter, EditorRequired]
    public ChooseRequest Request { get; set; } = default!;

    /// <summary>The path picked, or null when the picker was closed without one.</summary>
    [Parameter]
    public EventCallback<string?> OnDone { get; set; }

    private sealed record Row(FolderEntry Entry, bool Folder);

    private List<Row> Drawn => _shown is null
        ? []
        : _shown.Folders.Where(Kept).Select(e => new Row(e, true))
            .Concat(_shown.Files.Where(Kept).Select(e => new Row(e, false)))
            .ToList();

    private IEnumerable<(string Heading, List<FolderPlace> Places)> PlaceGroups
    {
        get
        {
            var drives = (_shown?.Roots ?? [])
                .Where(root => root != _shown?.Home)
                .Select(root => new FolderPlace(root == "/" ? "Computer" : root, root, "drive"));
            var all = _places.Concat(drives).ToList();
            return new[]
            {
                ("Places", all.Where(p => p.Kind is not "recent" and not "drive").ToList()),
                ("Recent", all.Where(p => p.Kind == "recent").ToList()),
                ("Drives", all.Where(p => p.Kind == "drive").ToList()),
            }.Where(group => group.Item2.Count > 0);
        }
    }

    private string Status
    {
        get
        {
            if (_status.Length > 0 || _shown is null)
            {
                return _status;
            }
            var folders = _shown.Folders.Count(Kept);
            var files = _shown.Files.Count(Kept);
            var kinds = Request.Suffixes.Count > 0 ? $" ({string.Join(", ", Request.Suffixes)})" : string.Empty;
            var counted = $"{folders} folder{(folders == 1 ? string.Empty : "s")}, {files} file{(files == 1 ? string.Empty : "s")}{kinds}";
            return _filter.Trim().Length > 0 ? $"{counted} matching" : counted;
        }
    }

    protected override async Task OnInitializedAsync()
    {
        _saveName = Request.Name ?? string.Empty;
        await GoAsync(Request.Start);
    }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (firstRender)
        {
            await (Request.Mode == "save" ? _saveBox : _filterBox).FocusAsync();
        }
        if (_focusList)
        {
            _focusList = false;
            await _list.FocusAsync();
        }
    }

    private bool Kept(FolderEntry entry) => _filter.Trim().Length == 0 || entry.Name.Contains(_filter.Trim(), StringComparison.OrdinalIgnoreCase);

    private static string PlaceIcon(string kind) => _placeIcons.GetValueOrDefault(kind, "folder");

    private static string DateOf(FolderEntry entry) => entry.Modified is { } seconds
        ? DateTimeOffset.FromUnixTimeMilliseconds((long)(seconds * 1000)).LocalDateTime.ToString("d", CultureInfo.CurrentCulture)
        : string.Empty;

    private static string SizeOf(long bytes) => bytes switch
    {
        < Kilobyte => $"{bytes} B",
        < Megabyte => $"{Math.Round((double)bytes / Kilobyte):N0} KB",
        _ => $"{(double)bytes / Megabyte:0.0} MB",
    };

    // Only the newest listing is drawn: a path typed while the first folder is still being read would otherwise be
    // replaced by that first answer when it arrives late.
    private async Task GoAsync(string? path)
    {
        var query = new List<string>();
        if (!string.IsNullOrEmpty(path))
        {
            query.Add($"path={ApiClient.Part(path)}");
        }
        if (Request.Suffixes.Count > 0)
        {
            query.Add($"suffixes={ApiClient.Part(string.Join(',', Request.Suffixes))}");
        }
        if (!_placesRead)
        {
            query.Add($"kind={ApiClient.Part(Request.Kind)}");
        }
        if (_hidden)
        {
            query.Add("hidden=1");
        }
        _status = string.Empty;
        var mine = ++_asked;
        var typed = _where;
        _reading = true;
        _readingWords = string.IsNullOrEmpty(path) ? "Reading the folder…" : $"Reading {path}…";
        FolderListing found;
        try
        {
            found = await Api.GetAsync<FolderListing>($"/folders{(query.Count > 0 ? "?" + string.Join('&', query) : string.Empty)}");
        }
        catch (ApiException error)
        {
            if (mine != _asked)
            {
                return;
            }
            _reading = false;
            // The first folder asked for may not exist yet (a projects folder before its first project): the nearest
            // folder above it that does is shown instead, else home.
            if (_shown is null && !string.IsNullOrEmpty(path))
            {
                _missing ??= path;
                var above = Above(path);
                await GoAsync(above.Length > 0 && above != path && !(above.Length == 2 && above[1] == ':') ? above : null);
                return;
            }
            _status = error.Message;
            return;
        }
        if (mine != _asked)
        {
            return;
        }
        _reading = false;
        var changed = _shown?.Path != found.Path;
        _shown = found;
        if (found.Places is { } places)
        {
            _places = places;
            _placesRead = true;
        }
        // A path typed while this folder was being read is kept (its Enter goes on to open it).
        if (_where == typed || _where == path)
        {
            _where = found.Path;
        }
        if (changed)
        {
            _filter = string.Empty;
        }
        _selected = -1;
        _naming = false;
        if (_missing is not null)
        {
            _status = $"{_missing} does not exist yet: showing the nearest folder that does.";
            _missing = null;
        }
    }

    private static string Above(string path)
    {
        var trimmed = path.TrimEnd('\\', '/');
        var cut = trimmed.LastIndexOfAny(['\\', '/']);
        return cut <= 0 ? string.Empty : trimmed[..cut];
    }

    private Task UpAsync() => _shown?.Parent is { } parent ? GoAsync(parent) : Task.CompletedTask;

    private void Select(int index)
    {
        var drawn = Drawn;
        if (drawn.Count == 0)
        {
            return;
        }
        _selected = Math.Clamp(index, 0, drawn.Count - 1);
        _focusList = true;
        if (Request.Mode == "save" && !drawn[_selected].Folder)
        {
            _saveName = drawn[_selected].Entry.Name;
        }
    }

    /// <summary>A double-click or Enter on a row: a folder opens, a file is picked (Save: saved over, as named).</summary>
    private async Task ActivateAsync(int index)
    {
        var drawn = Drawn;
        if (index < 0 || index >= drawn.Count)
        {
            return;
        }
        var chosen = drawn[index];
        if (chosen.Folder)
        {
            await GoAsync(chosen.Entry.Path);
        }
        else if (Request.Mode == "file")
        {
            await FinishAsync(chosen.Entry.Path);
        }
        else if (Request.Mode == "save")
        {
            _saveName = chosen.Entry.Name;
            await PickAsync();
        }
    }

    private async Task PickAsync()
    {
        if (_shown is not { } shown)
        {
            return;
        }
        switch (Request.Mode)
        {
            case "folder":
                await FinishAsync(shown.Path);
                break;
            case "save":
                var name = _saveName.Trim();
                if (name.Length == 0 || name.IndexOfAny(['\\', '/']) >= 0)
                {
                    _status = "Type a file name (no slashes)";
                    await _saveBox.FocusAsync();
                    return;
                }
                await FinishAsync(Join(shown.Path, name));
                break;
            default:
                await ActivateAsync(_selected);
                break;
        }
    }

    private static string Join(string folder, string name)
    {
        var sep = folder.Contains('\\') && !folder.Contains('/') ? "\\" : "/";
        return $"{folder.TrimEnd('\\', '/')}{sep}{name}";
    }

    private async Task FinishAsync(string? path)
    {
        if (path is not null)
        {
            try
            {
                await Api.PostAsync("/dialogs/recent", new { kind = Request.Kind, path, mode = Request.Mode });
            }
            catch (ApiException)
            {
                // The recent folders are a convenience: the pick stands.
            }
        }
        await OnDone.InvokeAsync(path);
    }

    // Escape on the filter (with words in it) or on New folder's name is theirs, not the dialog's: their keys stop
    // there (the markup's stopPropagation; a flag bound to the filter's words did not hold in Blazor's dispatch).
    private Task CloseAsync() => FinishAsync(null);

    private async Task HiddenAsync(ChangeEventArgs e)
    {
        _hidden = e.Value is true;
        if (_shown is not null)
        {
            await GoAsync(_shown.Path);
        }
    }
}
