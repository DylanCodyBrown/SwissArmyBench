namespace SwissArmyBench.Web.Api.Files;

/// <summary>One pick of a path (the classic fileChooser.ts ChooseOptions).</summary>
/// <param name="Mode">file picks a file, folder the folder shown, save a new or existing file's path.</param>
/// <param name="Title">The dialog's heading.</param>
/// <param name="Start">Where it starts: a file's path starts in its folder.</param>
/// <param name="Kind">The kind of pick, for its recent folders.</param>
/// <param name="Suffixes">The file kinds shown (".csv", ".xlsx"); none: every file.</param>
/// <param name="Name">Save: the name it starts with.</param>
public sealed record ChooseRequest(
    string Mode,
    string Title,
    string? Start,
    string Kind,
    IReadOnlyList<string> Suffixes,
    string? Name);
