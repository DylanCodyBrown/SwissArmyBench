namespace SwissArmyBench.Web.Pages.Workbench;

// A structure's tab beside the code (the classic structureDoc.ts and workbenchPage.ts's structure tabs): a JSON, YAML,
// XML or TOML file opened from the Files pane, Open… or the palette is a tab on this page (either page: the one it
// was opened from), so it can sit in a split next to a script; the palette's Structure commands act on the one in
// front.
public partial class WorkbenchPage
{
    private const string NoStructure = "No structure is in front";

    private void OpenStructure(string path, string? at)
    {
        if (_documents.FirstOrDefault(d => d.IsStructure && string.Equals(d.Path, path, StringComparison.OrdinalIgnoreCase)) is { } open)
        {
            _layout.Show(open.Key);
            if (at is not null)
            {
                open.StructureDoc?.Select(at);
            }
            return;
        }
        AddDocument(new OpenDocument(++_nextKey, false) { IsStructure = true, Path = path, StructureAt = at });
    }

    private Task StructureRenamedAsync(OpenDocument doc, string path)
    {
        doc.Path = path;
        return FollowAddressAsync();
    }

    private StructureDoc? FrontStructure => Front?.StructureDoc;

    private List<WorkbenchCommand> StructureCommands()
    {
        var none = FrontStructure is null ? NoStructure : null;
        return
        [
            new("structure.open", "Structure", "Open a JSON, YAML, XML or TOML file beside the code…", OpenStructureFileAsync),
            new("structure.search", "Structure", "Search the structure in front", SearchStructureAsync, Disabled: none),
            new("structure.next", "Structure", "Next match", () => Toggle(() => FrontStructure?.Step(1)), "Enter", none),
            new("structure.select", "Structure", "Select a node by its path (its way unfolded)", SelectNodeAsync, Disabled: none),
            new("structure.view", "Structure", "Tree, Text or Both", StructureViewAsync, Disabled: none),
            new("structure.format", "Structure", "Format the structure in front", () => FrontStructure?.FormatAsync() ?? Task.CompletedTask, Disabled: none),
            new("structure.state", "Structure", "The structure in front: its view, selection, search and problems",
                () => ShowHelp("The structure in front", System.Text.Json.JsonSerializer.Serialize(FrontStructure?.State(), _indented)), Disabled: none),
        ];
    }

    private static readonly System.Text.Json.JsonSerializerOptions _indented = new() { WriteIndented = true };

    private async Task OpenStructureFileAsync()
    {
        var home = await Workbench.HomeAsync();
        if (await Files.ChooseAsync("file", "Open a JSON, YAML, XML or TOML file", home.Folder, "structure") is { } path)
        {
            if (!StructureFiles.IsStructure(path))
            {
                _error = new InvalidOperationException($"{System.IO.Path.GetFileName(path)} is not a JSON, YAML, XML or TOML file.");
                return;
            }
            OpenStructure(path, null);
            await FollowAddressAsync();
        }
    }

    private async Task SearchStructureAsync()
    {
        if (await Dialogs.AskTextAsync("Search the structure", "Keys and values that hold these words, in any case.", "Words", string.Empty, "Search") is { } words)
        {
            FrontStructure?.Search(words);
        }
    }

    private async Task SelectNodeAsync()
    {
        if (await Dialogs.AskTextAsync("Select a node", "Its path, such as $.orders[3].lines.", "Path", "$", "Select") is { Length: > 0 } at)
        {
            FrontStructure?.Select(at.Trim());
        }
    }

    private async Task StructureViewAsync()
    {
        if (await Dialogs.AskTextAsync("Tree, Text or Both", "The structure's view: tree, text or both.", "View", "tree", "Show") is { } typed
            && typed.Trim().ToLowerInvariant() is ("tree" or "text" or "both") and var view)
        {
            await (FrontStructure?.SetViewAsync(view) ?? Task.CompletedTask);
        }
    }
}
