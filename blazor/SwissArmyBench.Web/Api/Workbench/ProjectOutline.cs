namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>Export outline's answer (POST /project/outline): ARCHITECTURE.md's name, where, whether it was written,
/// and its text (offered as a download). Edited: the file on disk was edited by hand since the app wrote it, so it
/// was kept (Said: the one sentence); Replace takes the new outline.</summary>
public sealed record ProjectOutline(
    string File,
    string Path,
    bool Written,
    string Text,
    bool Edited = false,
    string? Said = null);
