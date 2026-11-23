using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>A path's parts as the user's computer writes it, Windows' <c>\</c> included (the owner's screenshot,
/// 2026-11-23: a script's tab named with its whole Windows path).</summary>
public sealed class FilePathsTests
{
    [Theory]
    [InlineData(@"C:\Repos\financial-insights\SAB\Library\connections\edp.blade.py", "edp.blade.py")]
    [InlineData("/home/made-up/project/load.py", "load.py")]
    [InlineData(@"C:\Repos\project\", "project")]
    [InlineData("data.ipynb", "data.ipynb")]
    [InlineData(null, "")]
    public void TheNameIsTheLastPartWhicheverTheSeparator(string? path, string name) =>
        Assert.Equal(name, FilePaths.Name(path));

    [Theory]
    [InlineData(@"C:\Repos\project\data.ipynb", @"C:\Repos\project")]
    [InlineData(@"C:\data.ipynb", @"C:\")]
    [InlineData("/home/made-up/load.py", "/home/made-up")]
    [InlineData("/load.py", "/")]
    [InlineData("load.py", null)]
    public void TheFolderKeepsADrivesRoot(string path, string? folder) =>
        Assert.Equal(folder, FilePaths.Folder(path));

    [Theory]
    [InlineData(@"C:\Repos\orders.csv", "orders")]
    [InlineData("/made-up/edp.blade.py", "edp.blade")]
    [InlineData(".gitignore", ".gitignore")]
    public void TheStemDropsTheLastExtension(string path, string stem) =>
        Assert.Equal(stem, FilePaths.Stem(path));
}
