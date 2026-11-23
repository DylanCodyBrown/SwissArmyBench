namespace SwissArmyBench.Web.Api.Git;

/// <summary>The Source Control page (the Git extension's /git routes over GitHub's web API): the changes, the
/// history, a commit's files, a diff, the branches and repositories; stage, discard, commit, pull, push, sync,
/// checkout, clone, connect, disconnect; the sign-in (a token, or GitHub's device flow).</summary>
public sealed class GitClient
{
    private readonly ApiClient _api;

    public GitClient(ApiClient api)
    {
        _api = api;
    }

    public Task<ScmChanges> ChangesAsync() => _api.GetAsync<ScmChanges>("/git/changes");

    /// <summary>The state; remote: GitHub asked too (Fetch).</summary>
    public Task<ScmStatus> StatusAsync(bool remote = false) => _api.GetAsync<ScmStatus>(remote ? "/git?remote=1" : "/git");

    public Task<ScmHistory> HistoryAsync(string which, int page) => _api.GetAsync<ScmHistory>($"/git/history?which={ApiClient.Part(which)}&page={page}");

    public Task<ScmCommitFiles> CommitFilesAsync(string which, string commit) =>
        _api.GetAsync<ScmCommitFiles>($"/git/commit-files?which={ApiClient.Part(which)}&commit={ApiClient.Part(commit)}");

    public Task<ScmDiff> DiffAsync(string which, string path, string? commit, bool conflict)
    {
        var query = $"which={ApiClient.Part(which)}&path={ApiClient.Part(path)}{(commit is null ? string.Empty : $"&commit={ApiClient.Part(commit)}")}{(conflict ? "&conflict=1" : string.Empty)}";
        return _api.GetAsync<ScmDiff>($"/git/diff?{query}");
    }

    public Task<ScmBranches> BranchesAsync(string which) => _api.GetAsync<ScmBranches>($"/git/branches?which={ApiClient.Part(which)}");

    public Task<ScmRepositories> RepositoriesAsync() => _api.GetAsync<ScmRepositories>("/git/repositories");

    public Task StageAsync(string which, IReadOnlyList<string> paths, bool unstage) => _api.PostAsync("/git/stage", new { which, paths, unstage });

    public Task DiscardAsync(string which, IReadOnlyList<string> paths) => _api.PostAsync("/git/discard", new { which, paths });

    public Task<ScmWords> CommitAsync(string which, string message, IReadOnlyList<string> paths, bool sync) =>
        _api.PostAsync<ScmWords>("/git/commit", new { which, message, paths, sync });

    public Task<ScmWords> PullAsync(string which) => _api.PostAsync<ScmWords>("/git/pull", new { which });

    public Task<ScmWords> PushAsync(string which) => _api.PostAsync<ScmWords>("/git/push", new { which });

    public Task<ScmWords> SyncAsync(string which) => _api.PostAsync<ScmWords>("/git/sync", new { which });

    public Task<ScmWords> CheckoutAsync(string which, string branch, bool create) => _api.PostAsync<ScmWords>("/git/checkout", new { which, branch, create });

    public Task<ScmWords> CloneAsync(string which, string repository, string folder) => _api.PostAsync<ScmWords>("/git/clone", new { which, repository, folder });

    public Task<ScmWords> ConnectAsync(string which, string repository) => _api.PostAsync<ScmWords>("/git/connect", new { which, repository });

    public Task DisconnectAsync(string which) => _api.PostAsync("/git/disconnect", new { which });

    public Task SignInWithTokenAsync(string token) => _api.PostAsync("/git/sign-in/token", new { token });

    public Task<DeviceFlow> StartDeviceFlowAsync() => _api.PostAsync<DeviceFlow>("/git/sign-in/device");

    public Task<DevicePoll> PollDeviceFlowAsync() => _api.PostAsync<DevicePoll>("/git/sign-in/device/poll");
}
