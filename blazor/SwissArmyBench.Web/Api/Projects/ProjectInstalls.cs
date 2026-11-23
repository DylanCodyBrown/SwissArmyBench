namespace SwissArmyBench.Web.Api.Projects;

/// <summary>What the open project needs installed (GET /project/installs and the project_installs notice: the whole
/// state each time; services/project_python.py ProjectInstalls). <see cref="State"/> is checking, installing, done,
/// failed or none; <see cref="Share"/> how far the install is (0 to 1).</summary>
public sealed record ProjectInstalls(
    string State,
    string Project = "",
    int Total = 0,
    int Done = 0,
    string? Current = null,
    double Share = 0,
    IReadOnlyList<InstallPackage>? Packages = null,
    string Words = "",
    Refusal? Problem = null,
    IReadOnlyList<string>? Written = null,
    bool Restart = false,
    bool Own = true,
    string? Kernel = null);
