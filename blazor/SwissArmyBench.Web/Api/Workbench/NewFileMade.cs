namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /scripts/files/new: the new file's whole path, its path inside the project, its type, how its tab
/// is drawn and the page it opens on (Address: the page's own address for it, when its type opens somewhere of its
/// own); Made false for the dialog's check (nothing written).</summary>
public sealed record NewFileMade(string Path, string Relative, string Type, string Kind, string Page, bool Made, string? Address = null);
