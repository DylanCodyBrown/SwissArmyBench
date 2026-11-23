using System.Text.Json;

using Bunit;

using SwissArmyBench.Web.Pages.Analyze;
using SwissArmyBench.Web.Pages.Workbench;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The Notebooks and Scripts pages' small rules: a structure's search and paths, which files are a structure's
/// tab, a script's numbered and HTML cells, and the Tables group's line with its cell links.</summary>
public sealed class WorkbenchRulesTests : AppTestContext
{
    private static readonly JsonElement _orders = JsonDocument.Parse("""{"orders": [{"id": 1, "city": "Northby"}, {"id": 2, "city": "Southby"}], "order date": "x"}""").RootElement;

    [Fact]
    public void A_structures_search_finds_keys_and_values_in_the_documents_order()
    {
        Assert.Equal(["$.orders[0].city", "$.orders[1].city"], StructureFind.Matches(_orders, "BY"));
        Assert.Equal(["$.orders", "$[\"order date\"]"], StructureFind.Matches(_orders, "order")); // keys, not a list's items
    }

    [Fact]
    public void A_path_is_python_and_its_ancestors_unfold()
    {
        Assert.Equal("data[\"orders\"][1][\"city\"]", StructureFind.Code("$.orders[1].city"));
        Assert.Equal("data[\"order date\"]", StructureFind.Code("$[\"order date\"]"));
        Assert.Equal(["$", "$.orders", "$.orders[1]"], StructureFind.Ancestors("$.orders[1].city"));
        Assert.Equal("Southby", StructureFind.At(_orders, "$.orders[1].city")?.GetString());
        Assert.Null(StructureFind.At(_orders, "$.orders[5]"));
    }

    [Theory]
    [InlineData("C:\\made\\up\\orders.json", true)]
    [InlineData("/made/up/config.yml", true)]
    [InlineData("/made/up/app.canvas.json", false)]
    [InlineData("/made/up/.sab/project.json", false)]
    [InlineData("/made/up/.hidden.json", false)]
    [InlineData("/made/up/rates.py", false)]
    public void Which_files_open_as_a_structures_tab(string path, bool structure) =>
        Assert.Equal(structure, StructureFiles.IsStructure(path));

    [Fact]
    public void A_scripts_numbered_and_html_cells()
    {
        const string text = "a = 1\n# %% [3] made\nb = 2\nc = 3\n# %% [7] [html] height=200\n\"\"\"<p>{{ b }}</p>\"\"\"\n";
        Assert.Null(ScriptCells.CellAt(text, 1));
        Assert.Equal(3, ScriptCells.CellAt(text, 4));
        Assert.Equal(5, ScriptCells.LineOf(text, 7));
        var html = Assert.Single(ScriptHtml.Cells(text, new Dictionary<int, CellModel>()));
        Assert.Equal(("<p>{{ b }}</p>", 7, 200), (html.Source, html.Number, html.Height ?? 0));
    }

    [Fact]
    public void A_tables_line_links_its_cells()
    {
        var cell = new CellModel { Kind = "markdown", Role = "table", Table = "orders", Source = "## orders\n\norders is made at @cell7", Number = 4 };
        var line = Render<TableGroupBar>(p => p.Add(c => c.Cell, cell).Add(c => c.Runnable, true));
        Assert.Equal("@cell7", line.Find(".wb-cell-link").TextContent);
        Assert.Contains("Run", line.Find(".wb-run-table").TextContent, StringComparison.Ordinal);
    }

    [Fact]
    public void An_analyze_slot_is_a_chip_with_the_columns_that_do_not_fit()
    {
        var slot = new SwissArmyBench.Web.Api.Analyze.PlanSlot
        {
            Key = "column",
            Label = "Values",
            Many = true,
            Value = JsonDocument.Parse("""["amount"]""").RootElement,
            Offered = [new() { Name = "amount", Type = "DOUBLE" }, new() { Name = "tax", Type = "DOUBLE" }],
            Rejected = [new() { Name = "order_id", Why = "order_id is an identifier" }],
        };
        var chip = Render<AnalyzeSlot>(p => p.Add(c => c.Slot, slot));
        Assert.Equal("amount×", chip.Find(".chip[data-column=amount]").TextContent);
        Assert.Contains("order_id: is an identifier", chip.Find("optgroup").TextContent, StringComparison.Ordinal);
        Assert.Equal(2, chip.FindAll("select.chip-add option:not([disabled])").Count); // Add… and tax
    }
}
