using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Blades;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench.Blades;

public partial class CatalogSection
{
    private readonly Dictionary<string, IReadOnlyList<CatalogTable>> _tables = [];
    private IReadOnlyList<CatalogInfo> _catalogs = [];
    private CatalogInfo? _current;
    private IReadOnlyList<CatalogSchema> _schemas = [];
    private CatalogSchema? _schema;
    private CatalogTable? _shown;
    private CatalogSearch? _found;
    private string _search = string.Empty;
    private ShownMenu? _menu;
    private Exception? _error;

    [Inject]
    private SwissArmyBench.Web.Api.Blades.CatalogClient Catalogs { get; set; } = default!;

    [Inject]
    private SwissArmyBench.Web.Api.Connections.ConnectionsClient Connections { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    private bool Dax => _current?.Dialect == "dax";

    private static string Label(CatalogTable t) => t.Schema.Length > 0 ? $"{t.Schema}.{t.Table}" : t.Table;

    protected override Task OnInitializedAsync() => GuardAsync(async () =>
    {
        _catalogs = (await Catalogs.ListAsync()).Catalogs;
        await ChooseAsync(_catalogs.FirstOrDefault()?.Name);
    });

    private Task ChooseAsync(string? name) => GuardAsync(async () =>
    {
        _current = _catalogs.FirstOrDefault(c => c.Name == name);
        (_schema, _shown, _found, _search) = (null, null, null, string.Empty);
        _tables.Clear();
        _schemas = _current is null ? [] : (await Catalogs.SchemasAsync(_current.Name)).Schemas;
    });

    private Task OpenSchemaAsync(CatalogSchema schema) => _current is null || _tables.ContainsKey(schema.Schema)
        ? Task.CompletedTask
        : GuardAsync(async () => _tables[schema.Schema] = (await Catalogs.TablesAsync(_current.Name, schema.Schema, schema.Database)).Tables);

    private Task SearchAsync() => _current is null || _search.Trim().Length == 0
        ? ClearSearchAsync()
        : GuardAsync(async () => _found = await Catalogs.SearchAsync(_current.Name, _search.Trim()));

    private Task ClearSearchAsync()
    {
        _found = null;
        return Task.CompletedTask;
    }

    private Task ShowAsync(CatalogTable table)
    {
        _shown = table;
        return Task.CompletedTask;
    }

    private Task MenuAsync(MouseEventArgs at, CatalogTable table)
    {
        List<MenuEntry> entries = [new("Open as grid", "rows", () => OpenAsync(table))];
        if (Dax)
        {
            entries.Add(new("Import its relationships", "import", () => ImportAsync(table.Schema)));
        }
        _menu = new ShownMenu("table", entries, at.ClientX, at.ClientY);
        return Task.CompletedTask;
    }

    private Task OpenAsync(CatalogTable table) => _current is null ? Task.CompletedTask : GuardAsync(async () =>
    {
        await Notes.SayAsync($"Opening {table.Table}…");
        var opened = await Catalogs.OpenAsync(_current.Name, table);
        var cut = opened.Total > opened.Shown && opened.Shown is not null;
        await Notes.SayAsync(cut ? $"{opened.Dataset}: the first {opened.Shown:N0} of {opened.Total:N0} rows open as a grid." : $"{opened.Dataset} is open as a grid.");
        Nav.NavigateTo("grids");
    });

    private Task ImportAsync(string dataset) => _current is null ? Task.CompletedTask : GuardAsync(() => Catalogs.ImportRelationshipsAsync(_current.Name, dataset));

    /// <summary>Refresh: the connection run again with its catalog command, the catalog loaded again.</summary>
    private Task RefreshAsync() => _current is null ? Task.CompletedTask : GuardAsync(async () =>
    {
        var name = _current.Name;
        await Notes.SayAsync($"Refreshing {name}...");
        await Connections.RefreshAsync(name);
        _catalogs = (await Catalogs.ListAsync()).Catalogs;
        if (_catalogs.FirstOrDefault(c => c.Name == name) is { } now)
        {
            await Notes.SayAsync($"{name}: {now.Tables:N0} tables, {now.Columns:N0} columns.");
        }
        await ChooseAsync(name);
    });

    private Task RemoveAsync() => _current is null ? Task.CompletedTask : GuardAsync(async () =>
    {
        await Catalogs.RemoveAsync(_current.Name);
        _catalogs = (await Catalogs.ListAsync()).Catalogs;
        await ChooseAsync(_catalogs.FirstOrDefault()?.Name);
    });

    private async Task GuardAsync(Func<Task> action)
    {
        try
        {
            await action();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }
}
