using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api.PowerApps;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.CodeApp;

public partial class CodeAppProjectTab
{
    private CodeAppTreeNode? _tree;
    private CodeAppDataTs? _dataTs;
    private bool _everyFile;
    private bool _adding;
    private string _table = string.Empty;
    private string? _opening;
    private bool? _loadedFor;

    [Inject]
    private CodeAppClient CodeApps { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Parameter, EditorRequired]
    public CodeAppProject Project { get; set; } = new();

    [Parameter, EditorRequired]
    public CodeAppPage Host { get; set; } = default!;

    protected override async Task OnParametersSetAsync()
    {
        if (Project.Open && _loadedFor != true)
        {
            _loadedFor = true;
            await TreeAsync();
        }
        else if (!Project.Open)
        {
            _loadedFor = false;
        }
    }

    private static string LastPart(string path) => path.Split('/', '\\')[^1];

    private static string KindWords(CodeAppSource s) => s.Kind switch
    {
        "dataverse" => "Dataverse table",
        "table" => $"{s.DisplayName ?? s.Connector} table",
        _ => s.DisplayName ?? s.Connector,
    };

    private static string DataTsWords(CodeAppDataTs got) => string.Join(", ", new[]
    {
        $"{got.Cells.Count} cell{(got.Cells.Count == 1 ? string.Empty : "s")} exported",
        got.Types.Count > 0 ? $"{got.Types.Count} typed result{(got.Types.Count == 1 ? string.Empty : "s")}" : string.Empty,
        got.Left.Count > 0 ? $"{got.Left.Count} kept in the notebook" : string.Empty,
    }.Where(w => w.Length > 0));

    private async Task TreeAsync()
    {
        if (await Host.CallAsync(() => CodeApps.FilesAsync(_everyFile)) is { } got)
        {
            _tree = got.Tree;
        }
    }

    private async Task EveryFileAsync(ChangeEventArgs e)
    {
        _everyFile = e.Value is true;
        await TreeAsync();
    }

    private async Task NewPageAsync()
    {
        var name = await Dialogs.AskTextAsync("New page: its name", string.Empty, "New page: its name", "Orders");
        if (string.IsNullOrWhiteSpace(name))
        {
            return;
        }
        if (await Host.CallAsync(() => CodeApps.NewPageAsync(name.Trim())) is { Open: { } open })
        {
            await TreeAsync();
            await Host.OpenInWorkbenchAsync(open);
        }
    }

    private async Task NotebookAsync()
    {
        if (await Host.CallAsync(CodeApps.OpenNotebookAsync) is { Path: { } path })
        {
            await Host.OpenInWorkbenchAsync(path, notebook: true);
        }
    }

    private async Task UseInAppAsync() => _dataTs = await Host.CallAsync(CodeApps.UseInAppAsync) ?? _dataTs;

    private async Task GridAsync(CodeAppSource source)
    {
        _opening = source.Name;
        var got = await Host.CallAsync(() => CodeApps.DataverseGridAsync(source.Name));
        _opening = null;
        if (got is { Opened: true })
        {
            await Notes.SayAsync($"{got.Dataset ?? source.Name} is open on the Tables page.");
        }
        else if (got is not null)
        {
            Notes.Error(new InvalidOperationException(got.Message ?? $"{source.Name} did not open."));
        }
    }

    private async Task RemoveAsync(CodeAppSource source)
    {
        var words = $"Remove {source.Name} from the app? Its generated model and service go too.";
        if (await Dialogs.AskYesNoAsync(words, string.Empty, "Remove", danger: true) && await Host.CallAsync(() => CodeApps.RemoveSourceAsync(source.Name, source.Connector)) is not null)
        {
            await Host.LoadAsync();
        }
    }

    private async Task AddTableAsync()
    {
        var body = new Dictionary<string, object?> { ["kind"] = "dataverse", ["table"] = _table };
        if (await Host.CallAsync(() => CodeApps.AddSourceAsync(body)) is not null)
        {
            _adding = false;
            await Notes.SayAsync($"Added {_table}.");
            await Host.LoadAsync();
        }
    }
}
