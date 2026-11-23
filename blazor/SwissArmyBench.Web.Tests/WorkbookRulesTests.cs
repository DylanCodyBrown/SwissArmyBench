using System.Text.Json;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Accounting;
using SwissArmyBench.Web.Pages.Accounting;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The Excel canvas's pure rules, as the classic excelPreview.ts and excelCanvas.ts have them: column
/// letters, a cell's place, a block's words, its column specs; a chart's picture never carries a cell's words as
/// markup.</summary>
public sealed class WorkbookRulesTests
{
    private static WorkbookBlock Block(string json) => JsonSerializer.Deserialize<WorkbookBlock>(json, ApiClient.Json)!;

    [Theory]
    [InlineData(1, "A")]
    [InlineData(26, "Z")]
    [InlineData(27, "AA")]
    [InlineData(703, "AAA")]
    public void Letters_count_as_Excel_does(int column, string letters)
    {
        Assert.Equal(letters, WorkbookRules.Letters(column));
        Assert.Equal(column, WorkbookRules.ColumnOf(letters));
    }

    [Fact]
    public void A_cell_is_its_row_and_column_and_anything_else_A1()
    {
        Assert.Equal((3, 2), WorkbookRules.CellAt("B3"));
        Assert.Equal((12, 28), WorkbookRules.CellAt("$ab$12"));
        Assert.Equal((1, 1), WorkbookRules.CellAt("Sheet!B3"));
    }

    [Fact]
    public void A_table_says_its_source_columns_and_total_row()
    {
        var block = Block("""{"id":"b2","kind":"table","cell":"A3","w":5,"h":12,"source":{"table":"orders"},"columns":["id",{"name":"amount","label":"Amount","format":"currency"}],"total_row":true}""");
        Assert.Equal("orders: id, Amount · total row", WorkbookRules.Words(block, [block]));
        Assert.Equal(["id", "amount"], WorkbookRules.Specs(block).Select(c => c.Name));
        Assert.Equal("currency", WorkbookRules.Specs(block)[1].Format);
    }

    [Fact]
    public void A_pivot_and_a_chart_say_their_shape()
    {
        var pivot = Block("""{"id":"p","kind":"pivot","cell":"H3","source":{"query":"SELECT 1"},"rows":["city"],"columns":[],"values":[{"agg":"sum","column":"amount"},{"agg":"count"}]}""");
        var chart = Block("""{"id":"c","kind":"chart","cell":"A20","chart":"line","from":"p","title":"By city"}""");
        Assert.Equal("query: city by —, sum amount, count", WorkbookRules.Words(pivot, [pivot, chart]));
        Assert.Equal("line chart of a query: By city", WorkbookRules.Words(chart, [pivot, chart]));
    }

    [Fact]
    public void A_design_keeps_the_fields_this_page_does_not_know()
    {
        var json = """{"format":1,"kind":"workbook","title":"T","sheets":[{"id":"s1","name":"S","blocks":[],"zoom":120}],"theme":"blue"}""";
        var design = JsonSerializer.Deserialize<WorkbookDesign>(json, ApiClient.Json)!;
        var back = JsonSerializer.Serialize(design, ApiClient.Json);
        Assert.Contains("\"theme\":\"blue\"", back, StringComparison.Ordinal);
        Assert.Contains("\"zoom\":120", back, StringComparison.Ordinal);
    }

    [Fact]
    public void A_chart_picture_escapes_its_words()
    {
        var chart = new PreviewChart
        {
            Kind = "column",
            Cell = "A1",
            Width = 8,
            Height = 5,
            Title = "<script>x</script>",
            Categories = ["<b>North</b>"],
            Series = [new ChartSeries { Name = "Amount & tax", Kind = "bar", Values = [3, null] }],
        };
        var svg = ChartSvg.Draw(chart);
        Assert.DoesNotContain("<script>", svg, StringComparison.Ordinal);
        Assert.DoesNotContain("<b>", svg, StringComparison.Ordinal);
        Assert.Contains("Amount &amp; tax", svg, StringComparison.Ordinal);
        Assert.Single(svg.Split("<rect").Skip(1), r => r.Contains("fill=\"#1f3864\"", StringComparison.Ordinal) && !r.Contains("width=\"10\"", StringComparison.Ordinal));
    }

    [Fact]
    public void A_rule_value_is_a_number_when_it_reads_as_one()
    {
        Assert.Equal(1000.5, WorkbookRules.RuleValue("1000.5"));
        Assert.Equal("high", WorkbookRules.RuleValue("high"));
    }
}
