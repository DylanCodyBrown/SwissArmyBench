namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>Export outline's answer (POST /project/outline): ARCHITECTURE.md's name, where, whether it was written,
/// and its text (offered as a download).</summary>
public sealed record ProjectOutline(string File, string Path, bool Written, string Text);
