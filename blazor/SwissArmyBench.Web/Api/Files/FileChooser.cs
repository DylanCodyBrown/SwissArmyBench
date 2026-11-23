using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Api.Files;

/// <summary>
/// Picks a real path (the classic fileChooser.ts): the system's own file dialog first (routes_file_dialogs.py: it
/// opens on the user's screen), else the page's own picker (FilePicks: places, recent folders, the breadcrumb, New
/// folder, Hidden files). Once the system's dialog could not open here, the page's own is used from then on.
/// </summary>
public sealed class FileChooser
{
    private readonly ApiClient _api;
    private readonly FilePicks _picks;
    private readonly Notes _notes;
    private bool _systemGone;

    public FileChooser(ApiClient api, FilePicks picks, Notes notes)
    {
        _api = api;
        _picks = picks;
        _notes = notes;
    }

    /// <param name="mode">file (or open), save or folder.</param>
    /// <param name="title">The dialog's heading.</param>
    /// <param name="start">The folder it opens in.</param>
    /// <param name="kind">The kind of pick, so its recent folders are its own (project, table, notebook...).</param>
    /// <param name="suffixes">The file kinds shown (".csv", ".xlsx"); none: every file.</param>
    /// <param name="name">Save: the file name it starts with.</param>
    /// <returns>The path, or null when the user cancelled.</returns>
    public async Task<string?> ChooseAsync(string mode, string title, string? start = null, string kind = "file", IReadOnlyList<string>? suffixes = null, string? name = null)
    {
        // The server's modes are file, folder and save; "open" is read as "file" (an open dialog picks a file).
        mode = mode == "open" ? "file" : mode;
        var request = new ChooseRequest(mode, title, start, kind, suffixes ?? [], mode == "save" ? name : null);
        if (!_systemGone)
        {
            try
            {
                var answer = await _api.PostAsync<ChooseAnswer>("/dialogs/choose", new
                {
                    mode,
                    title,
                    start,
                    kind,
                    suffixes = request.Suffixes.Count > 0 ? request.Suffixes : null,
                    name = request.Name,
                });
                if (answer.Path is not null || answer.Cancelled)
                {
                    return answer.Path;
                }
                if (answer.Busy)
                {
                    _ = _notes.SayAsync("A file dialog is already open");
                    return null;
                }
            }
            catch (ApiException)
            {
                // The page's own picker, below.
            }
            _systemGone = true;
        }
        return await _picks.ChooseAsync(request);
    }
}
