namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A library New environment offers: its pip name, words, group, the import a notebook gets, a note.</summary>
public sealed record OfferedLibrary(string Pip, string Label, string Group, string Imports, string Note);
