namespace SwissArmyBench.Web.Components;

/// <summary>Where a review comment stands now in its editor (codeEditor.js commentPlaces): its lines and columns
/// as the edits moved them, and the code there.</summary>
public sealed record ReviewPlace(int Id, int Line, int Column, int End, int EndColumn, string Code);
