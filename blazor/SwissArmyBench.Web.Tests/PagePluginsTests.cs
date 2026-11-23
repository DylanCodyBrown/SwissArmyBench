using Bunit;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Rendering;
using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Components;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The page plug-ins' registry and a base page's PageActions: a declared action whose plug-in is registered
/// is a button from its data; a click opens the plug-in with the page's context; one not registered draws nothing.</summary>
public sealed class PagePluginsTests : AppTestContext
{
    private const string Mode = """
        {"project": "Made up", "project_type": "powerbi", "mode": {"type": "powerbi", "name": "Power BI", "canvases": [],
         "page_actions": [
           {"page": "erd", "id": "made-up-export", "label": "Export to Made Up…", "icon": "export", "title": "Send the tables"},
           {"page": "erd", "id": "not-registered", "label": "Nothing here"},
           {"page": "grids", "id": "made-up-export", "label": "On another page"}]}}
        """;

    public PagePluginsTests()
    {
        var server = new CannedServer().Answer("GET /app/mode", Mode);
        Services.AddScoped(_ => new HttpClient(server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
        var plugins = new PagePlugins();
        plugins.Register<MadeUpExport>("made-up-export");
        Services.AddSingleton(plugins);
    }

    [Fact]
    public void TheRegistryFindsWhatIsRegistered()
    {
        var plugins = new PagePlugins();
        plugins.Register<MadeUpExport>("made-up-export");

        Assert.Equal(typeof(MadeUpExport), plugins.Find("made-up-export"));
        Assert.Null(plugins.Find("not-registered"));
    }

    [Fact]
    public void ADeclaredActionOpensItsPluginWithThePagesContext()
    {
        var page = Render<PageActions>(p => p.Add(a => a.Page, "erd").Add(a => a.Context, new[] { "orders", "customers" }));

        var button = page.WaitForElement("button.page-action");
        Assert.Single(page.FindAll("button.page-action"));
        Assert.Contains("Export to Made Up…", button.TextContent);
        Assert.Equal("Send the tables", button.GetAttribute("title"));

        button.Click();
        Assert.StartsWith("orders, customers", page.Find(".made-up-export").TextContent, StringComparison.Ordinal);
        page.Find(".made-up-export button").Click();
        Assert.Empty(page.FindAll(".made-up-export"));
    }

    /// <summary>A made-up plug-in: the context it was handed, and Close.</summary>
    private sealed class MadeUpExport : ComponentBase
    {
        [Parameter]
        public object? Context { get; set; }

        [Parameter]
        public EventCallback OnClose { get; set; }

        protected override void BuildRenderTree(RenderTreeBuilder builder)
        {
            builder.OpenElement(0, "div");
            builder.AddAttribute(1, "class", "made-up-export");
            builder.AddContent(2, string.Join(", ", Context as IEnumerable<string> ?? []));
            builder.OpenElement(3, "button");
            builder.AddAttribute(4, "onclick", EventCallback.Factory.Create(this, () => OnClose.InvokeAsync()));
            builder.AddContent(5, "Close");
            builder.CloseElement();
            builder.CloseElement();
        }
    }
}
