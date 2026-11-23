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
    private string _lineEnding = "windows";
    private string _blank = string.Empty;
    private bool _quoteAll;
    private bool _cutLong;
    private string _compression = "snappy";
    private bool _busy;
    private bool _saving;
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

    /// <summary>How many rows the selection covers (its option's words: "Selection (12 rows × 2 columns)").</summary>
    [Parameter]
    public long SelectedRows { get; set; }

    private string SelectionLabel =>
        $"Selection ({SelectedRows:N0} rows{(Selection?.Columns is { } columns ? $" × {columns.Count} columns" : string.Empty)})";

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
            ["quote_all"] = _quoteAll ? "1" : "0",
            ["line_ending"] = _lineEnding,
            ["blank"] = _blank,
            ["allow_cell_truncation"] = _cutLong ? "1" : "0",
            ["compression"] = _compression,
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

    /// <summary>Download: the browser fetches the server's file (it never passes through C#); a refusal is said here.</summary>
    private async Task DownloadAsync()
    {
        _busy = true;
        _saving = false;
        try
        {
            var message = await Js.InvokeAsync<string>("sab.fetchDownload", GridsClient.ExportAddress(Info.Grid, Options()));
            if (message.Length > 0)
            {
                _ = Notes.SayAsync(message);
            }
            await OnClose.InvokeAsync();
        }
        catch (JSException error)
        {
            _error = new ApiException(0, new Refusal(error.Message.Split('\n')[0]), error.Message);
        }
        _busy = false;
    }

    private async Task SaveAsync()
    {
        _busy = true;
        _saving = true;
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
        _busy = false;
    }

    private void SetAll(bool on)
    {
        _columns.Clear();
        if (on)
        {
            _columns.UnionWith(Info.Columns.Select(c => c.Name));
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
