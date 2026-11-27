using Bunit;

using SwissArmyBench.Web.Api.Connections;
using SwissArmyBench.Web.Pages.Connections;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>A connection card's short amber badge (the owner, 2026-11-27): "Only works on your machine" in view, the
/// whole sentence on hover and for screen readers. Made-up notes.</summary>
public sealed class LocalOnlyBadgeTests : AppTestContext
{
    private const string Disk = "Only works on your machine: it reads a file on this computer's disk. On a Function App or hosted Streamlit app use a storage account.";
    private const string Keyring = "Only works on your machine: its password is in this computer's keyring. On a Function App or hosted Streamlit app use a key vault.";

    private static LocalNote Note(string key, string words) => new(key, "made-up reason", "made-up alternative", words);

    [Fact]
    public void TheBadgeIsShortAndItsHoverSaysTheWholeSentence()
    {
        var badge = Render<LocalOnlyBadge>(p => p.Add(b => b.Notes, [Note("path", Disk)]));

        var chip = badge.Find(".local-only-badge");
        Assert.Equal("Only works on your machine", chip.QuerySelector("[aria-hidden=true]:not(svg)")!.TextContent);
        Assert.Equal(Disk, chip.GetAttribute("title"));
        Assert.NotNull(chip.QuerySelector("svg[data-icon=warning]"));
    }

    [Fact]
    public void AScreenReaderHearsTheWholeSentenceOnce()
    {
        var badge = Render<LocalOnlyBadge>(p => p.Add(b => b.Notes, [Note("path", Disk)]));

        Assert.Equal(Disk, badge.Find(".local-only-badge .sr-only").TextContent);
        Assert.Single(badge.FindAll(".local-only-badge > span:not([aria-hidden])"));
    }

    [Fact]
    public void SeveralReasonsAreAllInTheHover()
    {
        var badge = Render<LocalOnlyBadge>(p => p.Add(b => b.Notes, [Note("path", Disk), Note("keyring", Keyring)]));

        Assert.Equal($"{Disk}\n{Keyring}", badge.Find(".local-only-badge").GetAttribute("title"));
        Assert.Single(badge.FindAll(".local-only-badge"));
    }
}
