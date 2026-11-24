namespace SwissArmyBench.Web.Api.Projects;

/// <summary>The open project as Home's summary heads it: its name, type and the type's words, Local or Shared
/// (<see cref="Where"/>), its folder, unsaved, Autosave.</summary>
public sealed record SummaryProject(
    string Name,
    string Path,
    string Type,
    string TypeName,
    string Where,
    bool Dirty,
    bool Autosave,
    string? AutosaveError = null,
    string? ReadOnly = null,
    bool Private = false);
