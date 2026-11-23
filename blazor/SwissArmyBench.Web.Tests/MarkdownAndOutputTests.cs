using System.Text.Json;

using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.Pages.Workbench;

using Xunit;

namespace SwissArmyBench.Web.Tests;

public sealed class MarkdownAndOutputTests
{
    [Fact]
    public void MarkdownNeverBecomesMarkup()
    {
        var html = MarkdownText.ToHtml("# Made-up <b>title</b>\n\nA *note* with <script>alert(1)</script> and `code`.");

        Assert.Contains("<h1>Made-up &lt;b&gt;title&lt;/b&gt;</h1>", html);
        Assert.Contains("<em>note</em>", html);
        Assert.Contains("<code>code</code>", html);
        Assert.DoesNotContain("<script>", html);
    }

    [Fact]
    public void MarkdownDrawsListsTablesAndLinks()
    {
        var html = MarkdownText.ToHtml("- one\n- two\n\n| name | total |\n|---|---|\n| made up | 12 |\n\n[site](https://example.com)");

        Assert.Contains("<ul><li>one</li><li>two</li></ul>", html);
        Assert.Contains("<td class=\"align-right\">12</td>", html);
        Assert.Contains("href=\"https://example.com\"", html);
        Assert.Contains("rel=\"noopener noreferrer\"", html);
    }

    [Fact]
    public void AStreamsTextJoinsTheStreamBeforeIt()
    {
        var outputs = new List<JsonElement>();
        OutputReader.Add(outputs, Record("""{"output_type": "stream", "name": "stdout", "text": "made "}"""));
        OutputReader.Add(outputs, Record("""{"output_type": "stream", "name": "stdout", "text": "up\n"}"""));
        OutputReader.Add(outputs, Record("""{"output_type": "stream", "name": "stderr", "text": "warned\n"}"""));

        Assert.Equal(2, outputs.Count);
        Assert.Equal("made up\n", OutputReader.Text(outputs[0], "text"));
    }

    [Fact]
    public void ATracebacksColoursAreTakenOut()
    {
        var error = Record("""{"output_type": "error", "ename": "ZeroDivisionError", "evalue": "division by zero", "traceback": ["\u001b[31mZeroDivisionError\u001b[39m: division by zero"]}""");

        Assert.Equal("ZeroDivisionError: division by zero", OutputReader.Traceback(error));
    }

    private static JsonElement Record(string json) => JsonDocument.Parse(json).RootElement.Clone();
}
