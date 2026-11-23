using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Grids.Tools;

public partial class ExportDialog
{
    private readonly HashSet<string> _columns = [];
    private string _scope = "view";
    private string _format = "csv";
    private string _file = string.Empty;
    private string _delimiter = "comma";
    private bool _header = true;
    private bool _bom;
    private bool _neutralize = true;
    private string _sheet = "Data";
    private bool _provenance = true;
    private Exception? _error;

    [Inject]
    private GridsClient Grids { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Parameter, EditorRequired]
    public GridInfo Info { get; set; } = default!;

    /// <summary>The grid's selection, when there is one (Rows: Selection).</summary>
    [Parameter]
    public SelectionDescriptor? Selection { get; set; }

    [Parameter]
    public EventCallback OnClose { get; set; }

    protected override void OnInitialized()
    {
        _file = Info.Dataset;
        _columns.UnionWith(Info.Columns.Select(c => c.Name));
    }

    private Dictionary<string, string> Options()
    {
        var options = new Dictionary<string, string>
        {
            ["format"] = _format,
            ["scope"] = _scope,
            ["file"] = _file.Trim(),
            ["delimiter"] = _format == "txt" && _delimiter == "comma" ? "tab" : _delimiter,
            ["header"] = _header ? "1" : "0",
            ["encoding"] = _bom ? "utf-8-sig" : "utf-8",
            ["neutralize_formulas"] = _neutralize ? "1" : "0",
            ["sheet_name"] = _sheet,
            ["provenance"] = _provenance ? "1" : "0",
        };
        if (_scope == "selection" && Selection is not null)
        {
            options["selection"] = JsonSerializer.Serialize(Selection, ApiClient.Json);
        }
        if (_scope == "columns")
        {
            options["columns"] = string.Join(",", Info.Columns.Select(c => c.Name).Where(_columns.Contains));
        }
        return options;
    }

    private async Task DownloadAsync()
    {
        // The browser's own download of the server's answer: the file never passes through C#.
        await Js.InvokeVoidAsync("sab.download", GridsClient.ExportAddress(Info.Grid, Options()));
        await OnClose.InvokeAsync();
    }

    private async Task SaveAsync()
    {
        try
        {
            var saved = await Grids.SaveExportAsync(Info.Grid, Options());
            _ = Notes.SayAsync($"{saved.Message} (saved in {saved.Saved})");
            await OnClose.InvokeAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private void Pick(string name, bool on)
    {
        if (on)
        {
            _columns.Add(name);
        }
        else
        {
            _columns.Remove(name);
        }
    }
}
