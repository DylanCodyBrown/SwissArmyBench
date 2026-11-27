using System.Text.Json;

using Bunit;

using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Api.Projects;
using SwissArmyBench.Web.Pages.Home;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>New project's Create runs once however fast it is pressed.</summary>
public sealed class NewProjectDialogTests : AppTestContext
{
    private readonly HeldServer _server = new("""{"project": null}""");

    public NewProjectDialogTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
    }

    [Fact]
    public async Task EnterPressedTwiceMakesOneProjectAsync()
    {
        using var make = JsonDocument.Parse("""{"type": "bi"}""");
        var type = new ProjectType("bi", "Analysis", "Analysis", "For anyone", "Explore", "Example", "A notebook", make.RootElement.Clone());
        var listing = new ExplorerAnswer("/made-up/projects", null, "/made-up/projects", [], new ExplorerSort("opened", true), [type], true);
        var dialog = Render<NewProjectDialog>(p => p.Add(d => d.Listing, listing));
        var name = dialog.Find("input.new-project-name");
        await name.InputAsync("made_up_twice");

        var first = dialog.Find("input.new-project-name").KeyDownAsync(new Microsoft.AspNetCore.Components.Web.KeyboardEventArgs { Key = "Enter" });
        var second = dialog.Find("input.new-project-name").KeyDownAsync(new Microsoft.AspNetCore.Components.Web.KeyboardEventArgs { Key = "Enter" });
        _server.Release();
        await Task.WhenAll(first, second);

        Assert.Single(_server.Asked, a => a == "POST /project/new");
    }
}
