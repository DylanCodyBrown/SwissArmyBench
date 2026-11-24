namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A fix the server offers (domain/errors.py): replace a text, add an import line, install a package, run
/// the cell that makes a name, add a cell, or a table open in Tables' cell.</summary>
public sealed record RunErrorFix(
    string Kind,
    string Title,
    string? Target = null,
    string? Text = null,
    string? Line = null,
    string? Package = null,
    string? Name = null);
