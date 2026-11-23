using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Forms;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Files;
using SwissArmyBench.Web.Api.PowerBi;

namespace SwissArmyBench.Web.Pages.PowerBi;

public partial class PowerBiExportDialog
{
    // A dropped report is read up to this size (a .pbix with its data can be large).
    private const long LargestReport = 512L * 1024 * 1024;

    private readonly HashSet<string> _ticked = [];
    private readonly HashSet<string> _rows = [];
    private readonly Dictionary<string, string?> _mapping = [];
    private PowerBiPlan? _plan;
    private PowerBiPlan? _made;
    private string _name = string.Empty;
    private (string? Path, string? Upload)? _report;
    private string? _busy;
    private Exception? _error;
    private bool _over;

    [Inject]
    private PowerBiClient PowerBi { get; set; } = default!;

    [Inject]
    private FileChooser Files { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    /// <summary>The page's context (the plug-in registry's parameter): the tables the ERD draws, as a list of
    /// names; anything else is no tables.</summary>
    [Parameter]
    public object? Context { get; set; }

    /// <summary>The Power BI page's Use another report's pages: the report part first.</summary>
    [Parameter]
    public bool ReportFirst { get; set; }

    [Parameter]
    public EventCallback OnClose { get; set; }

    /// <summary>The tables the ERD draws, read from the page's context.</summary>
    private IReadOnlyList<string> Tables { get; set; } = [];

    protected override async Task OnInitializedAsync()
    {
        Tables = Context is IEnumerable<string> names ? [.. names] : [];
        _ticked.UnionWith(Tables);
        await RefreshAsync();
    }

    private static string Words(PlannedRelationship r) => $"{r.From}.{string.Join(", ", r.FromColumns)} → {r.To}.{string.Join(", ", r.ToColumns)}";

    /// <summary>A field's choices: its current one, our tables' columns, and the measures as fields of its table.</summary>
    private static IEnumerable<string> Choices(ReportUse used, MappedField field, string current) =>
        (current.Length > 0 ? new[] { current } : [])
            .Concat(used.Ours.SelectMany(t => t.Value.Select(c => $"{t.Key}.{c}")))
            .Concat(used.Measures.Select(m => $"{field.To?.Table ?? field.Table}.{m}"))
            .Distinct();

    private Dictionary<string, object?> Body()
    {
        var body = new Dictionary<string, object?>
        {
            ["tables"] = Tables.Where(_ticked.Contains).ToList(),
            ["include_rows"] = _rows.Where(_ticked.Contains).ToList(),
        };
        if (_name.Trim().Length > 0)
        {
            body["name"] = _name.Trim();
        }
        if (_report is { } report)
        {
            body["report"] = report.Path is { } path ? new { path } : new { upload = report.Upload };
            body["mapping"] = _mapping;
        }
        return body;
    }

    private async Task RefreshAsync()
    {
        await WorkAsync("Reading the tables…", async () =>
        {
            _plan = await PowerBi.PlanAsync(Body());
            if (_name.Length == 0)
            {
                _name = _plan.Name;
            }
        });
    }

    private async Task WorkAsync(string words, Func<Task> work)
    {
        _busy = words;
        try
        {
            await work();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        finally
        {
            _busy = null;
        }
    }

    private Task TickAsync(HashSet<string> set, string table, bool on)
    {
        if (on)
        {
            set.Add(table);
        }
        else
        {
            set.Remove(table);
        }
        return RefreshAsync();
    }

    private Task MapAsync(string key, string? picked)
    {
        _mapping[key] = string.IsNullOrEmpty(picked) ? null : picked;
        return RefreshAsync();
    }

    private Task RemoveReportAsync()
    {
        _report = null;
        _mapping.Clear();
        return RefreshAsync();
    }

    private async Task ChooseAsync()
    {
        if (await Files.ChooseAsync("file", "A Power BI report", null, "powerbi-report") is { } path)
        {
            _report = (path, null);
            await RefreshAsync();
        }
    }

    private async Task DroppedAsync(InputFileChangeEventArgs e)
    {
        _over = false;
        var file = e.File;
        await WorkAsync($"Reading {file.Name}…", async () =>
        {
            await using var data = file.OpenReadStream(LargestReport);
            var kept = await PowerBi.UploadAsync(data, file.Name);
            _report = (null, kept.Upload);
        });
        await RefreshAsync();
    }

    private async Task ExportAsync()
    {
        if (_plan is null)
        {
            return;
        }
        if (_plan.Download)
        {
            await WorkAsync("Exporting…", async () =>
            {
                var (bytes, name) = await PowerBi.DownloadAsync(Body());
                var module = await Js.InvokeAsync<IJSObjectReference>("import", "./js/files.js");
                await module.InvokeVoidAsync("save", name, bytes);
            });
            if (_error is null)
            {
                await OnClose.InvokeAsync();
            }
            return;
        }
        await WorkAsync("Exporting…", async () => _made = await PowerBi.ExportAsync(Body()));
    }

    private Task OpenItAsync() => WorkAsync(string.Empty, () => PowerBi.OpenAsync(_made?.Where ?? string.Empty));
}
