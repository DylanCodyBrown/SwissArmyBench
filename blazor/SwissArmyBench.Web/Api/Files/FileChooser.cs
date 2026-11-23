using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Api.Files;

/// <summary>
/// Picks a real path (the classic fileChooser.ts): the system's own file dialog first (routes_file_dialogs.py: it
/// opens on the user's screen), else the path typed in the app's own box. The classic page's own folder picker is
/// not in this front end yet.
/// </summary>
public sealed class FileChooser
{
    private readonly ApiClient _api;
    private readonly Dialogs _dialogs;

    public FileChooser(ApiClient api, Dialogs dialogs)
    {
        _api = api;
        _dialogs = dialogs;
    }

    /// <param name="mode">open, save or folder.</param>
    /// <param name="title">The dialog's heading.</param>
    /// <param name="start">The folder it opens in.</param>
    /// <param name="kind">The kind of pick, so its recent folders are its own (project, table, notebook...).</param>
    /// <param name="name">A save's file name offered (the classic chooseFile's name).</param>
    /// <returns>The path, or null when the user cancelled.</returns>
    public async Task<string?> ChooseAsync(string mode, string title, string? start = null, string kind = "file", string? name = null)
    {
        var body = new Dictionary<string, object?> { ["mode"] = mode, ["title"] = title, ["start"] = start, ["kind"] = kind };
        if (name is not null)
        {
            body["name"] = name; // the server takes a name or none, never null
        }
        var answer = await _api.PostAsync<ChooseAnswer>("/dialogs/choose", body);
        if (answer.Path is not null || answer.Cancelled || answer.Busy)
        {
            return answer.Path;
        }
        var words = mode == "folder" ? "The folder's full path." : "The file's full path.";
        var offered = name is null ? start ?? string.Empty : System.IO.Path.Combine(start ?? string.Empty, name);
        var typed = await _dialogs.AskTextAsync(title, words, "Path", offered, "Choose");
        return string.IsNullOrWhiteSpace(typed) ? null : typed.Trim();
    }
}
